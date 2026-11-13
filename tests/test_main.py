from unittest.mock import Mock

import pytest

from nova import __main__ as app
from nova.ai import AIError
from nova.config import Config, ConfigError


class FakeConversation:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.asked = []

    def ask(self, text):
        self.asked.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


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


def run(lines, answers=()):
    conversation = FakeConversation(answers)
    output = []
    app.run_loop(conversation, read=scripted(lines), write=output.append)
    return conversation, output


def test_answers_question_then_exits():
    conversation, output = run(["hi", "/exit"], answers=["hello"])
    assert conversation.asked == ["hi"]
    assert "nova> hello" in output
    assert output[-1] == "Goodbye."


def test_exit_command_is_case_insensitive():
    conversation, output = run(["/EXIT"])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ai_error_is_shown_and_loop_continues():
    conversation, output = run(["q1", "q2", "/exit"], answers=[AIError("busy"), "ok"])
    assert "[error] busy" in output
    assert "nova> ok" in output


def test_empty_input_is_ignored():
    conversation, _ = run(["", "   ", "/exit"])
    assert conversation.asked == []


def test_end_of_input_exits_cleanly():
    _, output = run([])
    assert output[-1] == "Goodbye."


def test_ctrl_c_at_prompt_exits():
    conversation, output = run([KeyboardInterrupt()])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ctrl_c_during_request_cancels_only_that_turn():
    _, output = run(["q", "/exit"], answers=[KeyboardInterrupt()])
    assert "[cancelled]" in output
    assert output[-1] == "Goodbye."


def test_main_reports_config_error(monkeypatch, capsys):
    def broken_config():
        raise ConfigError("GEMINI_API_KEY is not set.")

    monkeypatch.setattr(app, "load_config", broken_config)
    assert app.main() == 1
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_main_closes_client_even_if_loop_crashes(monkeypatch):
    fake_client = Mock()
    monkeypatch.setattr(app, "load_config", lambda: Config(api_key="k", model="m"))
    monkeypatch.setattr(app, "GeminiClient", lambda config: fake_client)

    def crashing_loop(conversation):
        raise RuntimeError("bug")

    monkeypatch.setattr(app, "run_loop", crashing_loop)
    with pytest.raises(RuntimeError):
        app.main()
    fake_client.close.assert_called_once()
