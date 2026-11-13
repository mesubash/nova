"""Load and validate NOVA's configuration from environment variables."""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_HISTORY_TURNS = 10
DEFAULT_MAX_RECORDING_SECONDS = 30.0
DEFAULT_ALLOWED_APPS = ("Safari", "Notes", "Calendar", "Music", "Calculator", "TextEdit", "Finder")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    api_key: str = field(repr=False)  # never shown when the object is printed
    model: str
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS
    max_recording_seconds: float = DEFAULT_MAX_RECORDING_SECONDS
    allowed_apps: tuple[str, ...] = DEFAULT_ALLOWED_APPS
    search_folder: Path | None = None


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a validated Config.

    With no argument, loads .env (searching upward from the current folder)
    and reads the process environment. Tests pass a plain dict instead.
    """
    if env is None:
        load_dotenv(find_dotenv(usecwd=True))
        env = os.environ

    return Config(
        api_key=_require(env, "GEMINI_API_KEY"),
        model=_require(env, "GEMINI_MODEL"),
        request_timeout_seconds=_positive_float(
            env, "NOVA_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS
        ),
        max_history_turns=_positive_int(env, "NOVA_MAX_HISTORY_TURNS", DEFAULT_MAX_HISTORY_TURNS),
        max_recording_seconds=_positive_float(
            env, "NOVA_MAX_RECORDING_SECONDS", DEFAULT_MAX_RECORDING_SECONDS
        ),
        allowed_apps=_app_list(env, "NOVA_ALLOWED_APPS"),
        search_folder=_optional_folder(env, "NOVA_SEARCH_FOLDER"),
    )


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and set {name}.")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number of seconds, got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be a positive number, got {raw!r}.")
    return value


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}.") from None
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0, got {raw!r}.")
    return value


def _app_list(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = env.get(name, "").strip()
    if not raw:
        return DEFAULT_ALLOWED_APPS
    return tuple(app.strip() for app in raw.split(",") if app.strip())


def _optional_folder(env: Mapping[str, str], name: str) -> Path | None:
    raw = env.get(name, "").strip()
    if not raw:
        return None
    folder = Path(raw).expanduser()
    if not folder.is_dir():
        raise ConfigError(f"{name} must be an existing folder, got {raw!r}.")
    return folder.resolve()
