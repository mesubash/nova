"""Choose how voice questions are transcribed: Gemini (cloud) or Whisper on this Mac."""

import io
import wave
from collections.abc import Callable
from typing import Any

import numpy as np

from nova.ai import GeminiClient
from nova.config import Config

SAMPLE_RATE = 16_000
LANGUAGE = "en"
NO_SPEECH_THRESHOLD = 0.6  # starting value; tune with measurements

INSTALL_HINT = 'Local transcription needs mlx-whisper. Install it with: pip install -e ".[local]"'


class TranscriptionError(Exception):
    """Local transcription failed. The message is safe to show the user."""


def make_transcriber(config: Config, client: GeminiClient) -> Callable[[bytes], str]:
    """Return a function that turns WAV bytes into text, using the configured backend."""
    if config.transcriber == "local":
        return LocalTranscriber(config.local_model)
    return client.transcribe


class LocalTranscriber:
    """Transcribe on this Mac with Whisper on MLX. Audio never leaves the computer.

    The model is loaded on first use (downloaded once from Hugging Face if needed)
    and reused afterwards.
    """

    def __init__(self, model: str, whisper: Callable[..., dict] | None = None) -> None:
        self._model = model
        self._whisper = whisper

    def __call__(self, wav: bytes) -> str:
        if not wav:
            raise ValueError("wav must not be empty")
        samples = wav_to_samples(wav)
        whisper = self._load()
        try:
            result = whisper(
                samples,
                path_or_hf_repo=self._model,
                language=LANGUAGE,
                condition_on_previous_text=False,
            )
        except Exception as exc:  # download, load, and inference errors come in many types
            raise TranscriptionError(f"Local transcription failed: {exc}") from exc
        return spoken_text(result)

    def _load(self) -> Callable[..., dict]:
        if self._whisper is None:
            try:
                import mlx_whisper
            except ImportError as exc:
                raise TranscriptionError(INSTALL_HINT) from exc
            self._whisper = mlx_whisper.transcribe
        return self._whisper


def wav_to_samples(wav: bytes) -> np.ndarray:
    """Decode 16 kHz mono 16-bit WAV bytes into float samples between -1.0 and 1.0."""
    try:
        with wave.open(io.BytesIO(wav)) as reader:
            shape = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as exc:
        raise TranscriptionError(f"The recording could not be read: {exc}") from exc
    if shape != (1, 2, SAMPLE_RATE):
        raise TranscriptionError(f"Expected 16 kHz mono 16-bit audio, got {shape}.")
    return np.frombuffer(frames, "<i2").astype(np.float32) / 32768


def spoken_text(result: dict[str, Any]) -> str:
    """Keep only segments Whisper considers speech, so silence does not become text."""
    segments = result.get("segments") or []
    if not segments:
        return str(result.get("text", "")).strip()
    spoken = [s for s in segments if s.get("no_speech_prob", 0.0) < NO_SPEECH_THRESHOLD]
    return " ".join(str(s.get("text", "")).strip() for s in spoken).strip()
