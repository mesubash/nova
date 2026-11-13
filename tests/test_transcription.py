import sys
from unittest.mock import Mock

import numpy as np
import pytest

from nova.config import Config
from nova.speech import to_wav
from nova.transcription import (
    INSTALL_HINT,
    LocalTranscriber,
    TranscriptionError,
    make_transcriber,
    spoken_text,
    wav_to_samples,
)


def tone(seconds=0.5, amplitude=0.5):
    t = np.arange(int(seconds * 16_000)) / 16_000
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


class FakeWhisper:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else {"text": " hello ", "segments": []}
        self.error = error
        self.calls = []

    def __call__(self, samples, **kwargs):
        self.calls.append((samples, kwargs))
        if self.error:
            raise self.error
        return self.result


def test_samples_round_trip_through_wav():
    samples = tone()
    decoded = wav_to_samples(to_wav(samples))
    assert decoded.dtype == np.float32
    assert len(decoded) == len(samples)
    assert np.allclose(decoded, samples, atol=1e-3)


@pytest.mark.parametrize("sample_rate", [8_000, 44_100])
def test_wrong_sample_rate_is_rejected(sample_rate):
    with pytest.raises(TranscriptionError, match="16 kHz"):
        wav_to_samples(to_wav(tone(), sample_rate=sample_rate))


def test_unreadable_audio_is_rejected():
    with pytest.raises(TranscriptionError, match="could not be read"):
        wav_to_samples(b"not a wav file")


def test_local_transcriber_passes_samples_model_and_language():
    whisper = FakeWhisper({"text": " What time is it? ", "segments": []})
    transcribe = LocalTranscriber("some/model", whisper=whisper)
    assert transcribe(to_wav(tone())) == "What time is it?"
    samples, kwargs = whisper.calls[0]
    assert samples.dtype == np.float32
    assert kwargs["path_or_hf_repo"] == "some/model"
    assert kwargs["language"] == "en"
    assert kwargs["condition_on_previous_text"] is False


def test_segments_that_are_probably_not_speech_are_dropped():
    result = {
        "text": "Thank you. Open Safari.",
        "segments": [
            {"text": " Thank you.", "no_speech_prob": 0.9},
            {"text": " Open Safari.", "no_speech_prob": 0.05},
        ],
    }
    assert spoken_text(result) == "Open Safari."


def test_only_non_speech_segments_give_empty_text():
    result = {"text": " Thank you.", "segments": [{"text": " Thank you.", "no_speech_prob": 0.95}]}
    assert spoken_text(result) == ""


def test_model_failure_becomes_transcription_error():
    transcribe = LocalTranscriber("m", whisper=FakeWhisper(error=OSError("download failed")))
    with pytest.raises(TranscriptionError, match="download failed"):
        transcribe(to_wav(tone()))


def test_missing_package_explains_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlx_whisper", None)  # makes the import fail
    with pytest.raises(TranscriptionError) as error:
        LocalTranscriber("m")(to_wav(tone()))
    assert str(error.value) == INSTALL_HINT


def test_empty_audio_is_a_programming_error():
    with pytest.raises(ValueError):
        LocalTranscriber("m", whisper=FakeWhisper())(b"")


def test_make_transcriber_uses_gemini_by_default():
    client = Mock()
    transcribe = make_transcriber(Config(api_key="k", model="m"), client)
    assert transcribe is client.transcribe


def test_make_transcriber_uses_local_model_when_configured():
    config = Config(api_key="k", model="m", transcriber="local", local_model="some/model")
    assert isinstance(make_transcriber(config, Mock()), LocalTranscriber)


def test_local_transcriber_language_can_be_chosen():
    whisper = FakeWhisper({"text": "नमस्ते", "segments": []})
    LocalTranscriber("m", whisper=whisper, language="ne")(to_wav(tone()))
    assert whisper.calls[0][1]["language"] == "ne"
