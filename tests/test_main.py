from unittest.mock import Mock

import pytest

from nova import __main__ as app
from nova.ai import AIError
from nova.config import Config, ConfigError
from nova.speech import SpeechError


class FakeConversation:
    def __init__(self, answers=(), events=None):
        self.answers = list(answers)
        self.asked = []
        self.events = events if events is not None else []

    def ask(self, text):
        self.events.append(f"ask:{text}")
        self.asked.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class FakeSpeaker:
    def __init__(self, error=None, events=None):
        self.error = error
        self.spoken = []
        self.events = events if events is not None else []

    def speak(self, text):
        if self.error:
            raise self.error
        self.events.append(f"speak:{text}")
        self.spoken.append(text)

    def stop(self):
        self.events.append("stop")


def scripted(lines):
    """Return a fake input() that yields lines, raising exceptions or EOF at the end."""
    items = iter(lines)

    def read(prompt):
        try:
            item = next(items)
        except StopIteration:
            raise EOFError from None
        if isinstance(item, BaseException):
            raise item
        return item

    return read


def run(lines, answers=(), speaker=None, events=None):
    conversation = FakeConversation(answers, events)
    speaker = speaker or FakeSpeaker(events=events)
    output = []
    app.run_loop(conversation, speaker, read=scripted(lines), write=output.append)
    return conversation, speaker, output


def test_answers_question_then_exits():
    conversation, _, output = run(["hi", "/exit"], answers=["hello"])
    assert conversation.asked == ["hi"]
    assert "nova> hello" in output
    assert output[-1] == "Goodbye."


def test_answer_is_spoken():
    _, speaker, _ = run(["hi", "/exit"], answers=["hello"])
    assert speaker.spoken == ["hello"]


def test_speech_failure_keeps_text_and_loop_running():
    speaker = FakeSpeaker(error=SpeechError("no say"))
    conversation, _, output = run(["q1", "q2", "/exit"], answers=["a1", "a2"], speaker=speaker)
    assert "nova> a1" in output
    assert "[speech unavailable] no say" in output
    assert conversation.asked == ["q1", "q2"]


@pytest.mark.parametrize("line", ["", "   ", "/stop", "/STOP"])
def test_enter_or_stop_command_stops_speech_without_asking(line):
    conversation, speaker, _ = run([line, "/exit"])
    assert conversation.asked == []
    assert speaker.events.count("stop") >= 1


def test_new_question_stops_previous_speech_first():
    events = []
    run(["q1", "q2", "/exit"], answers=["a1", "a2"], events=events)
    second_ask = events.index("ask:q2")
    assert events[second_ask - 1] == "stop"


def test_exit_stops_speech():
    _, speaker, _ = run(["/exit"])
    assert speaker.events == ["stop"]


def test_exit_command_is_case_insensitive():
    conversation, _, output = run(["/EXIT"])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ai_error_is_shown_and_loop_continues():
    _, _, output = run(["q1", "q2", "/exit"], answers=[AIError("busy"), "ok"])
    assert "[error] busy" in output
    assert "nova> ok" in output


def test_end_of_input_exits_cleanly():
    _, _, output = run([])
    assert output[-1] == "Goodbye."


def test_ctrl_c_at_prompt_exits():
    conversation, _, output = run([KeyboardInterrupt()])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ctrl_c_during_request_cancels_only_that_turn():
    _, _, output = run(["q", "/exit"], answers=[KeyboardInterrupt()])
    assert "[cancelled]" in output
    assert output[-1] == "Goodbye."


def test_main_reports_config_error(monkeypatch, capsys):
    def broken_config():
        raise ConfigError("GEMINI_API_KEY is not set.")

    monkeypatch.setattr(app, "load_config", broken_config)
    assert app.main() == 1
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_main_cleans_up_even_if_loop_crashes(monkeypatch):
    fake_client = Mock()
    fake_speaker = Mock()
    monkeypatch.setattr(app, "load_config", lambda: Config(api_key="k", model="m"))
    monkeypatch.setattr(app, "GeminiClient", lambda config: fake_client)
    monkeypatch.setattr(app, "Speaker", lambda: fake_speaker)

    def crashing_loop(conversation, speaker):
        raise RuntimeError("bug")

    monkeypatch.setattr(app, "run_loop", crashing_loop)
    with pytest.raises(RuntimeError):
        app.main()
    fake_client.close.assert_called_once()
    fake_speaker.stop.assert_called_once()
