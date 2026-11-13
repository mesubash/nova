import subprocess

import pytest

from nova.speech import Speaker, SpeechError, to_speakable


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
