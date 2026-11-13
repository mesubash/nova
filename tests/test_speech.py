import io
import subprocess
import wave

import numpy as np
import pytest
import sounddevice as sd

from nova.speech import (
    SAMPLE_RATE,
    Recorder,
    RecordingError,
    Speaker,
    SpeechError,
    to_speakable,
    to_wav,
)


class FakeStdin:
    def __init__(self, error=None):
        self.data = b""
        self.closed = False
        self.error = error

    def write(self, data):
        if self.error:
            raise self.error
        self.data += data

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, args, stdin_error=None, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.stdin = FakeStdin(stdin_error)
        self.running = True
        self.ignores_terminate = False
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        if not self.ignores_terminate:
            self.running = False

    def kill(self):
        self.killed = True
        self.running = False

    def wait(self, timeout=None):
        if self.running:
            raise subprocess.TimeoutExpired("say", timeout)
        return 0


def make_speaker(stdin_error=None, popen_error=None):
    processes = []

    def fake_popen(args, **kwargs):
        if popen_error:
            raise popen_error
        process = FakeProcess(args, stdin_error=stdin_error, **kwargs)
        processes.append(process)
        return process

    return Speaker(popen=fake_popen), processes


def test_to_speakable_removes_markdown_and_extra_whitespace():
    assert to_speakable("**Kathmandu** is the\n\n# capital `city`") == (
        "Kathmandu is the capital city"
    )


def test_speak_sends_text_through_stdin_without_shell():
    speaker, processes = make_speaker()
    speaker.speak("Hello there")
    process = processes[0]
    assert process.args == ["say"]
    assert "shell" not in process.kwargs
    assert process.stdin.data == b"Hello there"
    assert process.stdin.closed


def test_text_starting_with_dash_is_never_an_argument():
    speaker, processes = make_speaker()
    speaker.speak("-v Alex hello")
    assert processes[0].args == ["say"]


@pytest.mark.parametrize("text", ["", "   ", "***"])
def test_nothing_speakable_starts_no_process(text):
    speaker, processes = make_speaker()
    speaker.speak(text)
    assert processes == []


def test_speak_stops_previous_speech():
    speaker, processes = make_speaker()
    speaker.speak("first")
    speaker.speak("second")
    assert processes[0].terminated
    assert processes[1].running


def test_stop_terminates_running_speech():
    speaker, processes = make_speaker()
    speaker.speak("hello")
    speaker.stop()
    assert processes[0].terminated
    assert not processes[0].killed


def test_stop_kills_if_terminate_is_ignored():
    speaker, processes = make_speaker()
    speaker.speak("hello")
    processes[0].ignores_terminate = True
    speaker.stop()
    assert processes[0].killed


def test_stop_does_nothing_if_speech_already_finished():
    speaker, processes = make_speaker()
    speaker.speak("hello")
    processes[0].running = False
    speaker.stop()
    assert not processes[0].terminated


def test_stop_is_safe_to_call_repeatedly():
    speaker, _ = make_speaker()
    speaker.stop()
    speaker.stop()


def test_missing_say_command_raises_speech_error():
    speaker, _ = make_speaker(popen_error=FileNotFoundError("say"))
    with pytest.raises(SpeechError, match="could not start"):
        speaker.speak("hello")


def test_broken_pipe_raises_speech_error_and_cleans_up():
    speaker, processes = make_speaker(stdin_error=BrokenPipeError())
    with pytest.raises(SpeechError, match="could not send"):
        speaker.speak("hello")
    assert processes[0].terminated


class FakeStream:
    """Feeds prepared audio chunks to the callback when the stream opens."""

    def __init__(self, chunks, **kwargs):
        self.chunks = chunks
        self.kwargs = kwargs

    def __enter__(self):
        callback = self.kwargs["callback"]
        for chunk in self.chunks:
            try:
                callback(chunk, len(chunk), None, None)
            except sd.CallbackStop:
                break
        return self

    def __exit__(self, *exc_info):
        return False


def tone(seconds, amplitude=0.3):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32).reshape(-1, 1)


def make_recorder(chunks, max_seconds=5.0, open_error=None):
    streams = []

    def factory(**kwargs):
        if open_error:
            raise open_error
        stream = FakeStream(chunks, **kwargs)
        streams.append(stream)
        return stream

    return Recorder(max_seconds, stream_factory=factory), streams


def wav_info(data):
    with wave.open(io.BytesIO(data)) as wav:
        return wav.getnchannels(), wav.getframerate(), wav.getnframes()


def test_record_returns_mono_16khz_wav():
    recorder, streams = make_recorder([tone(1.0)])
    waits = []
    data = recorder.record(waits.append)
    assert wav_info(data) == (1, SAMPLE_RATE, SAMPLE_RATE)
    assert waits == [5.0]
    assert streams[0].kwargs["channels"] == 1


def test_recording_is_cut_at_max_duration():
    recorder, _ = make_recorder([tone(1.0)] * 5, max_seconds=2.0)
    data = recorder.record(lambda timeout: None)
    assert wav_info(data)[2] == 2 * SAMPLE_RATE


def test_quiet_recording_raises_no_speech():
    recorder, _ = make_recorder([tone(1.0, amplitude=0.001)])
    with pytest.raises(RecordingError, match="No speech"):
        recorder.record(lambda timeout: None)


@pytest.mark.parametrize("chunks", [[], [np.zeros((SAMPLE_RATE, 1), np.float32)]])
def test_no_signal_points_to_microphone_permission(chunks):
    recorder, _ = make_recorder(chunks)
    with pytest.raises(RecordingError, match="Privacy & Security"):
        recorder.record(lambda timeout: None)


def test_microphone_open_failure_raises_recording_error():
    recorder, _ = make_recorder([], open_error=sd.PortAudioError("no input device"))
    with pytest.raises(RecordingError, match="Could not open"):
        recorder.record(lambda timeout: None)


def test_to_wav_clips_out_of_range_samples():
    data = to_wav(np.array([2.0, -2.0], np.float32))
    with wave.open(io.BytesIO(data)) as wav:
        frames = np.frombuffer(wav.readframes(2), "<i2")
    assert frames.tolist() == [32767, -32767]


def test_is_speaking_follows_process_state():
    speaker, processes = make_speaker()
    assert not speaker.is_speaking
    speaker.speak("hello")
    assert speaker.is_speaking
    processes[0].running = False
    assert not speaker.is_speaking
    speaker.speak("again")
    speaker.stop()
    assert not speaker.is_speaking
