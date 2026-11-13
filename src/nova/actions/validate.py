"""Turn an untrusted action proposal into a validated action, or reject it."""

import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

from nova.storage import MAX_NOTE_LENGTH, NoteStore, StorageError

MAX_APP_NAME_LENGTH = 100
MAX_URL_LENGTH = 2048
MAX_QUERY_LENGTH = 100
PREVIEW_LENGTH = 80
MAX_NOTE_ID = 2**63 - 1  # the largest integer SQLite can store


class ActionRejected(Exception):
    """The proposed action is not allowed. The message is safe to show the user."""


@dataclass(frozen=True)
class ActionRequest:
    """An action exactly as the model proposed it. Nothing in here is trusted."""

    name: str
    args: Any


@dataclass(frozen=True)
class ActionPolicy:
    allowed_apps: tuple[str, ...]
    search_folder: Path | None
    notes: NoteStore | None = None


# Desktop actions


@dataclass(frozen=True)
class OpenApp:
    app: str
    requires_confirmation: ClassVar[bool] = True

    def describe(self) -> str:
        return f"Open the app {self.app}"


@dataclass(frozen=True)
class OpenUrl:
    url: str
    requires_confirmation: ClassVar[bool] = True

    def describe(self) -> str:
        return f"Open {self.url} in your browser"


@dataclass(frozen=True)
class SearchFiles:
    query: str
    folder: Path
    requires_confirmation: ClassVar[bool] = False

    def describe(self) -> str:
        return f'Search for files named like "{self.query}" in {self.folder}'


# Note actions. Each carries the store it was validated against.


@dataclass(frozen=True)
class SaveNote:
    text: str
    store: NoteStore = field(repr=False, compare=False)
    requires_confirmation: ClassVar[bool] = True

    def describe(self) -> str:
        return f'Save a note: "{_preview(self.text)}"'


@dataclass(frozen=True)
class ListNotes:
    store: NoteStore = field(repr=False, compare=False)
    requires_confirmation: ClassVar[bool] = False

    def describe(self) -> str:
        return "Show your recent notes"


@dataclass(frozen=True)
class SearchNotes:
    query: str
    store: NoteStore = field(repr=False, compare=False)
    requires_confirmation: ClassVar[bool] = False

    def describe(self) -> str:
        return f'Find notes containing "{self.query}"'


@dataclass(frozen=True)
class EditNote:
    note_id: int
    text: str
    current: str
    store: NoteStore = field(repr=False, compare=False)
    requires_confirmation: ClassVar[bool] = True

    def describe(self) -> str:
        return (
            f'Change note #{self.note_id} from "{_preview(self.current)}" '
            f'to "{_preview(self.text)}"'
        )


@dataclass(frozen=True)
class DeleteNote:
    note_id: int
    current: str
    store: NoteStore = field(repr=False, compare=False)
    requires_confirmation: ClassVar[bool] = True

    def describe(self) -> str:
        return f'Delete note #{self.note_id}: "{_preview(self.current)}"'


Action = (
    OpenApp | OpenUrl | SearchFiles | SaveNote | ListNotes | SearchNotes | EditNote | DeleteNote
)

_Validator = Callable[[Mapping[str, Any], ActionPolicy], Action]


def validate(request: ActionRequest, policy: ActionPolicy) -> Action:
    """Return a validated action or raise ActionRejected. Never executes anything."""
    validators: dict[str, _Validator] = {
        "open_app": _open_app,
        "open_url": _open_url,
        "search_files": _search_files,
        "save_note": _save_note,
        "list_notes": _list_notes,
        "search_notes": _search_notes,
        "edit_note": _edit_note,
        "delete_note": _delete_note,
    }
    validator = validators.get(request.name)
    if validator is None:
        raise ActionRejected(f"Unknown action: {request.name!r}.")
    if not isinstance(request.args, Mapping):
        raise ActionRejected("The action's arguments are malformed.")
    return validator(request.args, policy)


# Argument checks


def _expect_keys(args: Mapping[str, Any], *keys: str) -> None:
    if set(args) != set(keys):
        if not keys:
            raise ActionRejected("This action takes no arguments.")
        names = ", ".join(repr(key) for key in keys)
        raise ActionRejected(f"Expected exactly these arguments: {names}.")


def _string(args: Mapping[str, Any], key: str, max_length: int) -> str:
    value = args[key]
    if not isinstance(value, str) or not value.strip():
        raise ActionRejected(f"{key!r} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ActionRejected(f"{key!r} is too long.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ActionRejected(f"{key!r} contains control characters.")
    return value


def _note_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ActionRejected("A note number must be a whole number.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif (
        isinstance(value, str)
        and (digits := value.strip().lstrip("#")).isascii()
        and digits.isdigit()
    ):
        number = int(digits)
    else:
        raise ActionRejected("A note number must be a whole number.")
    if number <= 0:
        raise ActionRejected("Note numbers start at 1.")
    if number > MAX_NOTE_ID:
        raise ActionRejected("That note number is too large.")
    return number


def _preview(text: str) -> str:
    return text if len(text) <= PREVIEW_LENGTH else text[: PREVIEW_LENGTH - 1] + "…"


# Desktop action validators


def _open_app(args: Mapping[str, Any], policy: ActionPolicy) -> OpenApp:
    _expect_keys(args, "app")
    name = _string(args, "app", MAX_APP_NAME_LENGTH)
    _reject_invisible(name, "app")
    for allowed in policy.allowed_apps:
        if allowed.casefold() == name.casefold():
            return OpenApp(allowed)
    raise ActionRejected(f"{name} is not in the list of apps NOVA may open.")


def _open_url(args: Mapping[str, Any], policy: ActionPolicy) -> OpenUrl:
    _expect_keys(args, "url")
    url = _string(args, "url", MAX_URL_LENGTH)
    _reject_invisible(url, "url")
    if "\\" in url:
        raise ActionRejected("Web addresses cannot contain backslashes.")
    if any(char.isspace() for char in url):
        raise ActionRejected("Web addresses cannot contain spaces.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise ActionRejected("That web address is malformed.") from None
    if parts.scheme.lower() not in ("http", "https") or not host:
        raise ActionRejected("Only http and https web addresses can be opened.")
    if parts.username is not None or parts.password is not None:
        raise ActionRejected("Web addresses with a user name or password are not allowed.")
    return OpenUrl(url)


def _search_files(args: Mapping[str, Any], policy: ActionPolicy) -> SearchFiles:
    _expect_keys(args, "query")
    query = _string(args, "query", MAX_QUERY_LENGTH)
    _reject_invisible(query, "query")
    if "/" in query or "\\" in query:
        raise ActionRejected("Search by file name only, without folder paths.")
    if policy.search_folder is None:
        raise ActionRejected("File search is off. Set NOVA_SEARCH_FOLDER in .env to enable it.")
    folder = policy.search_folder.resolve()
    if not folder.is_dir():
        raise ActionRejected(f"The search folder {folder} does not exist.")
    return SearchFiles(query, folder)


# Note validators


def _notes(policy: ActionPolicy) -> NoteStore:
    if policy.notes is None:
        raise ActionRejected("Notes are unavailable right now.")
    return policy.notes


def _current_text(store: NoteStore, note_id: int) -> str:
    try:
        return store.get(note_id).text
    except StorageError as exc:
        raise ActionRejected(str(exc)) from None


def _save_note(args: Mapping[str, Any], policy: ActionPolicy) -> SaveNote:
    store = _notes(policy)
    _expect_keys(args, "text")
    return SaveNote(_string(args, "text", MAX_NOTE_LENGTH), store)


def _list_notes(args: Mapping[str, Any], policy: ActionPolicy) -> ListNotes:
    store = _notes(policy)
    _expect_keys(args)
    return ListNotes(store)


def _search_notes(args: Mapping[str, Any], policy: ActionPolicy) -> SearchNotes:
    store = _notes(policy)
    _expect_keys(args, "query")
    return SearchNotes(_string(args, "query", MAX_QUERY_LENGTH), store)


def _edit_note(args: Mapping[str, Any], policy: ActionPolicy) -> EditNote:
    store = _notes(policy)
    _expect_keys(args, "id", "text")
    note_id = _note_id(args["id"])
    text = _string(args, "text", MAX_NOTE_LENGTH)
    return EditNote(note_id, text, _current_text(store, note_id), store)


def _delete_note(args: Mapping[str, Any], policy: ActionPolicy) -> DeleteNote:
    store = _notes(policy)
    _expect_keys(args, "id")
    note_id = _note_id(args["id"])
    return DeleteNote(note_id, _current_text(store, note_id), store)


def _reject_invisible(value: str, key: str) -> None:
    """Reject invisible formatting characters that can disguise names and addresses."""
    if any(unicodedata.category(char) == "Cf" for char in value):
        raise ActionRejected(f"{key!r} contains invisible formatting characters.")
