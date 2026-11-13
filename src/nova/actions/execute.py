"""Execute validated actions. Only validated Action objects reach this module."""

import os
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from nova.actions.validate import Action, OpenApp, OpenUrl, SearchFiles

OPEN_TIMEOUT_SECONDS = 10
MAX_RESULTS = 20
MAX_FILES_SCANNED = 20_000


@dataclass(frozen=True)
class ActionResult:
    """What actually happened. `message` is short enough to speak; `details` lists items."""

    ok: bool
    message: str
    details: tuple[str, ...] = ()


Runner = Callable[..., subprocess.CompletedProcess]


def execute(action: Action, run: Runner = subprocess.run) -> ActionResult:
    match action:
        case OpenApp(app=app):
            return _open(["open", "-a", app], f"Opened {app}.", run)
        case OpenUrl(url=url):
            return _open(["open", url], f"Opened {url}.", run)
        case SearchFiles():
            return search_files(action)
    raise TypeError(f"Not a validated action: {action!r}")


def _open(command: list[str], success: str, run: Runner) -> ActionResult:
    try:
        completed = run(command, capture_output=True, text=True, timeout=OPEN_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ActionResult(False, f"Could not run the open command: {exc}")
    if completed.returncode != 0:
        reason = completed.stderr.strip() or f"exit code {completed.returncode}"
        return ActionResult(False, f"That failed: {reason}")
    return ActionResult(True, success)


def search_files(
    action: SearchFiles,
    max_results: int = MAX_RESULTS,
    max_scanned: int = MAX_FILES_SCANNED,
) -> ActionResult:
    root = action.folder.resolve()
    query = action.query.casefold()
    matches: list[str] = []
    for path in _iter_files(root, max_scanned):
        if query not in path.name.casefold():
            continue
        if not path.resolve().is_relative_to(root):
            continue  # a symlink pointing outside the approved folder
        matches.append(str(path.relative_to(root)))
        if len(matches) >= max_results:
            break

    if not matches:
        return ActionResult(True, f'No files named like "{action.query}" in {root.name}.')
    count = f"{len(matches)}+" if len(matches) >= max_results else str(len(matches))
    noun = "file" if count == "1" else "files"
    examples = ", ".join(Path(match).name for match in matches[:3])
    return ActionResult(
        True,
        f'Found {count} {noun} matching "{action.query}", including {examples}.',
        tuple(matches),
    )


def _iter_files(root: Path, max_scanned: int) -> Iterator[Path]:
    """Yield non-hidden files under root, without following symlinked folders."""
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            scanned += 1
            if scanned > max_scanned:
                return
            yield Path(dirpath, name)
