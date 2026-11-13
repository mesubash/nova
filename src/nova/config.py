"""Load and validate NOVA's configuration from environment variables."""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_HISTORY_TURNS = 10
DEFAULT_MAX_RECORDING_SECONDS = 30.0
DEFAULT_DATA_DIR = Path("~/Library/Application Support/NOVA")
TRANSCRIBERS = ("gemini", "local")
DEFAULT_TRANSCRIBER = "gemini"
DEFAULT_LOCAL_MODEL = "mlx-community/whisper-large-v3-turbo"
SPEECH_LANGUAGES = ("en", "ne")
DEFAULT_SPEECH_LANGUAGE = "en"
DEFAULT_DEVANAGARI_VOICE = "Lekha"
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
    data_dir: Path = DEFAULT_DATA_DIR.expanduser()
    transcriber: str = DEFAULT_TRANSCRIBER
    local_model: str = DEFAULT_LOCAL_MODEL
    speech_language: str = DEFAULT_SPEECH_LANGUAGE
    devanagari_voice: str = DEFAULT_DEVANAGARI_VOICE


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a validated Config.

    With no argument, loads .env (searching upward from the current folder)
    and reads the process environment. Tests pass a plain dict instead.
    """
    if env is None:
        env = _environment()

    config = Config(
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
        data_dir=_data_dir(env, "NOVA_DATA_DIR"),
        transcriber=_choice(env, "NOVA_TRANSCRIBER", TRANSCRIBERS, DEFAULT_TRANSCRIBER),
        local_model=env.get("NOVA_LOCAL_MODEL", "").strip() or DEFAULT_LOCAL_MODEL,
        speech_language=_choice(
            env, "NOVA_SPEECH_LANGUAGE", SPEECH_LANGUAGES, DEFAULT_SPEECH_LANGUAGE
        ),
        devanagari_voice=env.get("NOVA_DEVANAGARI_VOICE", "").strip() or DEFAULT_DEVANAGARI_VOICE,
    )
    if config.speech_language == "ne" and config.transcriber == "local":
        raise ConfigError(
            "Local transcription does not handle Nepali well (86% word error rate measured). "
            "Use NOVA_TRANSCRIBER=gemini with NOVA_SPEECH_LANGUAGE=ne."
        )
    return config


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Add it to .env in the project folder, "
            f"or to {user_config_path()} for the desktop app."
        )
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


def _data_dir(env: Mapping[str, str], name: str) -> Path:
    raw = env.get(name, "").strip()
    folder = (Path(raw) if raw else DEFAULT_DATA_DIR).expanduser().resolve()
    if folder.exists() and not folder.is_dir():
        raise ConfigError(f"{name} must be a folder, got {raw!r}.")
    return folder


# Settings files

USER_CONFIG_FILENAME = "config.env"
USER_CONFIG_TEMPLATE = """\
# NOVA settings for the desktop app.
# Only your macOS user can read this file. Never share it or commit it.

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite

# Optional
# NOVA_ALLOWED_APPS=Safari,Notes,Calendar,Music,Calculator,TextEdit,Finder
# NOVA_SEARCH_FOLDER=~/Documents
# NOVA_TRANSCRIBER=local
# NOVA_SPEECH_LANGUAGE=ne
"""


def user_config_path() -> Path:
    """The settings file used by the packaged app, next to the notes database."""
    return DEFAULT_DATA_DIR.expanduser() / USER_CONFIG_FILENAME


def ensure_user_config(path: Path | None = None) -> Path:
    """Create a private settings template if none exists. Never overwrites."""
    path = path or user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(descriptor, "w") as file:
        file.write(USER_CONFIG_TEMPLATE)
    return path


def _environment(environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Merge settings. Precedence: process environment > project .env > user config file."""
    merged: dict[str, str] = {}
    user_file = user_config_path()
    if user_file.is_file():
        _make_private(user_file)
        merged.update(_values(user_file))
    project_file = find_dotenv(usecwd=True)
    if project_file:
        merged.update(_values(Path(project_file)))
    merged.update(environ)
    return merged


def _values(path: Path) -> dict[str, str]:
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def _make_private(path: Path) -> None:
    """Ensure a file holding secrets is readable only by its owner."""
    if path.stat().st_mode & 0o077:
        try:
            path.chmod(0o600)
        except OSError as exc:
            raise ConfigError(f"Could not restrict permissions on {path}: {exc}") from exc


def _choice(env: Mapping[str, str], name: str, choices: tuple[str, ...], default: str) -> str:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in choices:
        raise ConfigError(f"{name} must be one of {', '.join(choices)}, got {raw!r}.")
    return raw
