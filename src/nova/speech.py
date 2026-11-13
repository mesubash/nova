"""Speech output through the macOS `say` command."""

import io
import re
import subprocess
import wave
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd

_MARKDOWN_SYMBOLS = re.compile(r"[*_#`>~]")
_DEVANAGARI = re.compile("[\u0900-\u097f]")
_VOICE_LINE = re.compile(r"^(.*?)\s+[a-z]{2,3}_[A-Z0-9]{2,3}\s+#")


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
        devanagari_voice: str | None = None,
        voices: Callable[[], set[str]] | None = None,
    ) -> None:
        self._command = command
        self._popen = popen
        self._devanagari_voice = devanagari_voice
        self._voices = voices or available_voices
        self._devanagari_voice_ok: bool | None = None  # checked once, on first use
        self._process: subprocess.Popen | None = None

    def speak(self, text: str) -> None:
        """Start speaking in the background. Stops any speech already playing."""
        self.stop()
        speakable = to_speakable(text)
        if not speakable:
            return

        command = [self._command]
        if self._devanagari_voice and _DEVANAGARI.search(speakable):
            command += ["-v", self._checked_devanagari_voice()]
        try:
            process = self._popen(
                command,
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

    @property
    def is_speaking(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _checked_devanagari_voice(self) -> str:
        voice = self._devanagari_voice
        assert voice is not None
        if self._devanagari_voice_ok is None:
            self._devanagari_voice_ok = voice in self._voices()
        if not self._devanagari_voice_ok:
            raise SpeechError(
                f'no installed voice can read Nepali text ("{voice}" was not found). Add a '
                "Hindi voice in System Settings > Accessibility > Spoken Content, or set "
                "NOVA_DEVANAGARI_VOICE."
            )
        return voice

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


SAMPLE_RATE = 16_000
SILENCE_PEAK = 0.005

_NO_SIGNAL_MESSAGE = (
    "The microphone returned no sound. Allow microphone access for your terminal app in "
    "System Settings > Privacy & Security > Microphone, then restart the terminal."
)


class RecordingError(Exception):
    """Audio could not be captured. The message is safe to show the user."""


def check_signal(samples: np.ndarray) -> None:
    """Reject recordings with no signal (likely no permission) or only silence."""
    if samples.size == 0 or not np.any(samples):
        raise RecordingError(_NO_SIGNAL_MESSAGE)
    if float(np.max(np.abs(samples))) < SILENCE_PEAK:
        raise RecordingError(
            "No speech detected. Press Enter and speak closer to the microphone, "
            "or type your question."
        )


def to_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode mono float samples (-1.0 to 1.0) as 16-bit PCM WAV bytes, in memory."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


class Recorder:
    def __init__(
        self,
        max_seconds: float,
        stream_factory: Callable[..., Any] = sd.InputStream,
    ) -> None:
        self._max_seconds = max_seconds
        self._stream_factory = stream_factory

    def record(self, wait_for_stop: Callable[[float], None]) -> bytes:
        """Record until `wait_for_stop` returns or the time limit is reached; return WAV bytes."""
        max_frames = int(self._max_seconds * SAMPLE_RATE)
        chunks: list[np.ndarray] = []
        frames = 0

        def on_audio(indata: np.ndarray, frame_count: int, time_info: Any, status: Any) -> None:
            nonlocal frames
            chunks.append(indata.copy())
            frames += frame_count
            if frames >= max_frames:
                raise sd.CallbackStop

        try:
            with self._stream_factory(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio
            ):
                wait_for_stop(self._max_seconds)
        except sd.PortAudioError as exc:
            raise RecordingError(f"Could not open the microphone: {exc}") from exc

        samples = np.concatenate(chunks)[:max_frames, 0] if chunks else np.zeros(0, np.float32)
        check_signal(samples)
        return to_wav(samples)


def available_voices(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> set[str]:
    """Names of the voices `say` can use, read from `say -v ?`. Empty if that fails."""
    try:
        listing = run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {
        match.group(1).strip()
        for line in listing.splitlines()
        if (match := _VOICE_LINE.match(line))
    }
