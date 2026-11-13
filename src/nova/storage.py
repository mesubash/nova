"""Personal notes stored in SQLite. Every operation is explicit; nothing is saved implicitly."""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

NOTES_FILENAME = "notes.db"
MAX_NOTE_LENGTH = 2000
DEFAULT_LIST_LIMIT = 50
DEFAULT_SEARCH_LIMIT = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL CHECK (length(text) > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_COLUMNS = "id, text, created_at, updated_at"


class StorageError(Exception):
    """A notes operation failed. The message is safe to show the user."""


class NoteNotFound(StorageError):
    """No note has the requested ID."""


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    created_at: datetime
    updated_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class NoteStore:
    def __init__(self, path: Path, now: Callable[[], datetime] = _utc_now) -> None:
        self._path = path
        self._now = now
        with self._connect() as db:
            db.execute(_SCHEMA)
        try:
            self._path.chmod(0o600)  # readable and writable by your macOS user only
        except OSError as exc:
            raise StorageError(f"Could not secure the notes database: {exc}") from exc

    @property
    def path(self) -> Path:
        return self._path

    def add(self, text: str) -> Note:
        text = _clean(text)
        stamp = self._now()
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO notes (text, created_at, updated_at) VALUES (?, ?, ?)",
                (text, stamp.isoformat(), stamp.isoformat()),
            )
            note_id = cursor.lastrowid
        assert note_id is not None
        return Note(note_id, text, stamp, stamp)

    def get(self, note_id: int) -> Note:
        with self._connect() as db:
            row = db.execute(f"SELECT {_COLUMNS} FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NoteNotFound(f"There is no note #{note_id}.")
        return _to_note(row)

    def recent(self, limit: int = DEFAULT_LIST_LIMIT) -> list[Note]:
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {_COLUMNS} FROM notes ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_to_note(row) for row in rows]

    def search(self, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Note]:
        """Return notes containing every word of `query`, ignoring case."""
        words = query.split()
        if not words:
            return []
        conditions = " AND ".join("text LIKE ? ESCAPE '\\'" for _ in words)
        params = [f"%{_escape_like(word)}%" for word in words]
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {_COLUMNS} FROM notes WHERE {conditions} "
                "ORDER BY updated_at DESC, id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [_to_note(row) for row in rows]

    def update(self, note_id: int, text: str) -> Note:
        text = _clean(text)
        stamp = self._now().isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE notes SET text = ?, updated_at = ? WHERE id = ?",
                (text, stamp, note_id),
            )
            if cursor.rowcount == 0:
                raise NoteNotFound(f"There is no note #{note_id}.")
        return self.get(note_id)

    def delete(self, note_id: int) -> Note:
        """Delete a note and return what was deleted."""
        note = self.get(note_id)
        with self._connect() as db:
            cursor = db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            if cursor.rowcount == 0:
                raise NoteNotFound(f"There is no note #{note_id}.")
        return note

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for one operation, inside a transaction.

        The transaction commits if the block succeeds and rolls back if anything
        raises, so a failed operation never leaves partial changes behind.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(sqlite3.connect(self._path, timeout=5)) as db, db:
                yield db
        except sqlite3.Error as exc:
            raise StorageError(f"Could not access the notes database: {exc}") from exc
        except OSError as exc:
            raise StorageError(f"Could not create the notes folder: {exc}") from exc


def _clean(text: str) -> str:
    text = text.strip()
    if not text:
        raise StorageError("A note cannot be empty.")
    if len(text) > MAX_NOTE_LENGTH:
        raise StorageError(f"Notes are limited to {MAX_NOTE_LENGTH} characters.")
    return text


def _escape_like(word: str) -> str:
    """Make %, _ and the escape character match literally in a LIKE pattern."""
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_note(row: tuple) -> Note:
    note_id, text, created_at, updated_at = row
    return Note(
        note_id, text, datetime.fromisoformat(created_at), datetime.fromisoformat(updated_at)
    )
