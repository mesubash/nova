"""Speech output through the macOS `say` command."""

import re
import subprocess
from collections.abc import Callable

_MARKDOWN_SYMBOLS = re.compile(r"[*_#`>~]")


class SpeechError(Exception):
    """Speech could not be started. The text response is unaffected."""


def to_speakable(text: str) -> str:
    """Remove markdown symbols and collapse whitespace so `say` reads cleanly."""
    return " ".join(_MARKDOWN_SYMBOLS.sub("", text).split())


class Speaker:
    def __init__(
        self,
        command: str = "say",
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self._command = command
        self._popen = popen
        self._process: subprocess.Popen | None = None

    def speak(self, text: str) -> None:
        """Start speaking in the background. Stops any speech already playing."""
        self.stop()
        speakable = to_speakable(text)
        if not speakable:
            return

        try:
            process = self._popen(
                [self._command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise SpeechError(f"could not start '{self._command}': {exc}") from exc

        self._process = process
        try:
            process.stdin.write(speakable.encode())
            process.stdin.close()
        except OSError as exc:
            self.stop()
            raise SpeechError(f"could not send text to '{self._command}': {exc}") from exc

    def stop(self) -> None:
        """Stop speech if it is playing. Safe to call at any time."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
