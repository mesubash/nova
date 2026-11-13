from datetime import UTC, datetime, timedelta

import pytest

from nova.storage import MAX_NOTE_LENGTH, NoteNotFound, NoteStore, StorageError


class Clock:
    """A fake clock that moves forward one minute every time it is read."""

    def __init__(self):
        self.current = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)

    def __call__(self):
        self.current += timedelta(minutes=1)
        return self.current


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "data" / "notes.db"


@pytest.fixture
def store(db_path):
    return NoteStore(db_path, now=Clock())


def test_add_returns_note_with_id_and_timestamps(store):
    note = store.add("  Buy milk  ")
    assert note.id == 1
    assert note.text == "Buy milk"
    assert note.created_at == note.updated_at
    assert note.created_at.tzinfo is not None


def test_notes_survive_restart(db_path):
    NoteStore(db_path).add("Remember the dentist on Friday")
    reopened = NoteStore(db_path)
    assert [note.text for note in reopened.recent()] == ["Remember the dentist on Friday"]


def test_missing_folders_are_created_and_file_is_private(db_path):
    NoteStore(db_path)
    assert db_path.exists()
    assert db_path.stat().st_mode & 0o777 == 0o600


def test_recent_lists_newest_first_with_limit(store):
    for text in ["first", "second", "third"]:
        store.add(text)
    assert [note.text for note in store.recent()] == ["third", "second", "first"]
    assert [note.text for note in store.recent(limit=2)] == ["third", "second"]


def test_search_requires_every_word_ignoring_case(store):
    store.add("Buy milk and eggs")
    store.add("Call the dentist")
    store.add("Milk tea recipe")
    assert [note.text for note in store.search("MILK eggs")] == ["Buy milk and eggs"]
    assert {note.text for note in store.search("milk")} == {"Buy milk and eggs", "Milk tea recipe"}
    assert store.search("   ") == []


@pytest.mark.parametrize(
    ("query", "expected"),
    [("100%", "100% done"), ("file_name", "file_name.txt")],
)
def test_search_treats_wildcards_literally(store, query, expected):
    for text in ["100% done", "1000 done", "file_name.txt", "filexname.txt"]:
        store.add(text)
    assert [note.text for note in store.search(query)] == [expected]


def test_sql_in_note_text_is_stored_as_text(store):
    text = "x'); DROP TABLE notes; --"
    store.add(text)
    assert store.recent()[0].text == text


def test_update_changes_text_but_keeps_id_and_created_time(store):
    original = store.add("Call mum")
    updated = store.update(original.id, "Call mum on Sunday")
    assert updated.id == original.id
    assert updated.text == "Call mum on Sunday"
    assert updated.created_at == original.created_at
    assert updated.updated_at > original.updated_at


def test_delete_returns_note_and_ids_are_never_reused(store):
    store.add("a")
    second = store.add("b")
    deleted = store.delete(second.id)
    assert deleted.text == "b"
    with pytest.raises(NoteNotFound):
        store.get(second.id)
    assert store.add("c").id == 3


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_missing_note_raises_not_found(store, operation):
    method = getattr(store, operation)
    args = (99, "text") if operation == "update" else (99,)
    with pytest.raises(NoteNotFound, match="#99"):
        method(*args)


@pytest.mark.parametrize("text", ["", "   ", "x" * (MAX_NOTE_LENGTH + 1)])
def test_invalid_note_text_is_rejected_and_nothing_is_stored(store, text):
    with pytest.raises(StorageError):
        store.add(text)
    assert store.recent() == []


def test_failed_write_keeps_existing_notes(store, db_path):
    store.add("important")
    db_path.chmod(0o444)
    try:
        with pytest.raises(StorageError, match="notes database"):
            store.add("this write fails")
    finally:
        db_path.chmod(0o600)
    assert [note.text for note in store.recent()] == ["important"]


def test_corrupt_database_reports_storage_error(db_path):
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"this is not a sqlite database")
    with pytest.raises(StorageError):
        NoteStore(db_path)
