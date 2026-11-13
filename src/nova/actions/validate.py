"""Turn an untrusted action proposal into a validated action, or reject it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

MAX_APP_NAME_LENGTH = 100
MAX_URL_LENGTH = 2048
MAX_QUERY_LENGTH = 100


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


Action = OpenApp | OpenUrl | SearchFiles


def validate(request: ActionRequest, policy: ActionPolicy) -> Action:
    """Return a validated action or raise ActionRejected. Never executes anything."""
    validators: dict[str, Callable[[Mapping[str, Any], ActionPolicy], Action]] = {
        "open_app": _open_app,
        "open_url": _open_url,
        "search_files": _search_files,
    }
    validator = validators.get(request.name)
    if validator is None:
        raise ActionRejected(f"Unknown action: {request.name!r}.")
    if not isinstance(request.args, Mapping):
        raise ActionRejected("The action's arguments are malformed.")
    return validator(request.args, policy)


def _single_string(args: Mapping[str, Any], key: str, max_length: int) -> str:
    if set(args) != {key}:
        raise ActionRejected(f"Expected exactly one argument named {key!r}.")
    value = args[key]
    if not isinstance(value, str) or not value.strip():
        raise ActionRejected(f"{key!r} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ActionRejected(f"{key!r} is too long.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ActionRejected(f"{key!r} contains control characters.")
    return value


def _open_app(args: Mapping[str, Any], policy: ActionPolicy) -> OpenApp:
    name = _single_string(args, "app", MAX_APP_NAME_LENGTH)
    for allowed in policy.allowed_apps:
        if allowed.casefold() == name.casefold():
            return OpenApp(allowed)
    raise ActionRejected(f"{name} is not in the list of apps NOVA may open.")


def _open_url(args: Mapping[str, Any], policy: ActionPolicy) -> OpenUrl:
    url = _single_string(args, "url", MAX_URL_LENGTH)
    if any(char.isspace() for char in url):
        raise ActionRejected("Web addresses cannot contain spaces.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise ActionRejected("That web address is malformed.") from None
    if parts.scheme.lower() not in ("http", "https") or not host:
        raise ActionRejected("Only http and https web addresses can be opened.")
    return OpenUrl(url)


def _search_files(args: Mapping[str, Any], policy: ActionPolicy) -> SearchFiles:
    query = _single_string(args, "query", MAX_QUERY_LENGTH)
    if "/" in query or "\\" in query:
        raise ActionRejected("Search by file name only, without folder paths.")
    if policy.search_folder is None:
        raise ActionRejected("File search is off. Set NOVA_SEARCH_FOLDER in .env to enable it.")
    folder = policy.search_folder.resolve()
    if not folder.is_dir():
        raise ActionRejected(f"The search folder {folder} does not exist.")
    return SearchFiles(query, folder)
