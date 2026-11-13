from unittest.mock import Mock

import pytest

from nova import __main__ as app
from nova.actions import CANCELLED, ActionPolicy, ActionRequest, ActionResult, OpenApp
from nova.ai import AIError
from nova.config import Config, ConfigError
from nova.speech import RecordingError, SpeechError
from nova.storage import StorageError
from nova.transcription import TranscriptionError


class FakeConversation:
    def __init__(self, answers=(), events=None):
        self.answers = list(answers)
        self.completed = []
        self.asked = []
        self.events = events if events is not None else []

    def ask(self, text):
        self.events.append(f"ask:{text}")
        self.asked.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def complete_action(self, outcome):
        self.completed.append(outcome)


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


def run(lines, answers=(), speaker=None, events=None, heard=(), execute_action=None):
    conversation = FakeConversation(answers, events)
    speaker = speaker or FakeSpeaker(events=events)
    listener = FakeListener(heard, events)
    output = []
    app.run_loop(
        conversation,
        speaker,
        listener,
        POLICY,
        read=scripted(lines),
        write=output.append,
        execute_action=execute_action or FakeExecute(),
    )
    return conversation, speaker, output, listener


def test_answers_question_then_exits():
    conversation, _, output, _ = run(["hi", "/exit"], answers=["hello"])
    assert conversation.asked == ["hi"]
    assert "nova> hello" in output
    assert output[-1] == "Goodbye."


def test_answer_is_spoken():
    _, speaker, _, _ = run(["hi", "/exit"], answers=["hello"])
    assert speaker.spoken == ["hello"]


def test_speech_failure_keeps_text_and_loop_running():
    speaker = FakeSpeaker(error=SpeechError("no say"))
    conversation, _, output, _ = run(["q1", "q2", "/exit"], answers=["a1", "a2"], speaker=speaker)
    assert "nova> a1" in output
    assert "[speech unavailable] no say" in output
    assert conversation.asked == ["q1", "q2"]


@pytest.mark.parametrize("line", ["/stop", "/STOP"])
def test_stop_command_stops_speech_without_asking_or_listening(line):
    conversation, speaker, _, listener = run([line, "/exit"])
    assert conversation.asked == []
    assert listener.calls == 0
    assert "stop" in speaker.events


def test_new_question_stops_previous_speech_first():
    events = []
    run(["q1", "q2", "/exit"], answers=["a1", "a2"], events=events)
    second_ask = events.index("ask:q2")
    assert events[second_ask - 1] == "stop"


def test_exit_stops_speech():
    _, speaker, _, _ = run(["/exit"])
    assert speaker.events == ["stop"]


def test_exit_command_is_case_insensitive():
    conversation, _, output, _ = run(["/EXIT"])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ai_error_is_shown_and_loop_continues():
    _, _, output, _ = run(["q1", "q2", "/exit"], answers=[AIError("busy"), "ok"])
    assert "[error] busy" in output
    assert "nova> ok" in output


def test_end_of_input_exits_cleanly():
    _, _, output, _ = run([])
    assert output[-1] == "Goodbye."


def test_ctrl_c_at_prompt_exits():
    conversation, _, output, _ = run([KeyboardInterrupt()])
    assert conversation.asked == []
    assert output[-1] == "Goodbye."


def test_ctrl_c_during_request_cancels_only_that_turn():
    _, _, output, _ = run(["q", "/exit"], answers=[KeyboardInterrupt()])
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

    def crashing_loop(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(app, "run_loop", crashing_loop)
    with pytest.raises(RuntimeError):
        app.main()
    fake_client.close.assert_called_once()
    fake_speaker.stop.assert_called_once()


class FakeListener:
    def __init__(self, results=(), events=None):
        self.results = list(results)
        self.calls = 0
        self.events = events if events is not None else []

    def __call__(self):
        self.events.append("listen")
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.mark.parametrize("line", ["", "   "])
def test_empty_enter_listens_and_answers_transcript(line):
    conversation, _, output, _ = run([line, "/exit"], answers=["It is noon"], heard=["what time"])
    assert conversation.asked == ["what time"]
    assert "you (voice)> what time" in output
    assert "nova> It is noon" in output


def test_speech_stops_before_listening():
    events = []
    run(["", "/exit"], answers=["ok"], events=events, heard=["hi"])
    assert events[events.index("listen") - 1] == "stop"


def test_no_speech_returns_to_prompt_without_asking():
    conversation, _, output, _ = run(["", "/exit"], heard=[""])
    assert conversation.asked == []
    assert any("[no speech detected]" in line for line in output)


@pytest.mark.parametrize("error", [RecordingError("mic denied"), AIError("transcription failed")])
def test_voice_errors_allow_retry(error):
    conversation, _, output, _ = run(["", "", "/exit"], answers=["ok"], heard=[error, "retry"])
    assert f"[error] {error}" in output
    assert conversation.asked == ["retry"]


def test_ctrl_c_while_listening_cancels():
    conversation, _, output, _ = run(["", "/exit"], heard=[KeyboardInterrupt()])
    assert "[cancelled]" in output
    assert conversation.asked == []


def test_typing_still_works_without_listening():
    conversation, _, _, listener = run(["typed question", "/exit"], answers=["ok"])
    assert conversation.asked == ["typed question"]
    assert listener.calls == 0


POLICY = ActionPolicy(("Safari",), None)


class FakeExecute:
    def __init__(self, result=None):
        self.result = result or ActionResult(True, "Done.")
        self.actions = []

    def __call__(self, action):
        self.actions.append(action)
        return self.result


def test_confirmed_action_runs_and_is_spoken():
    execute_action = FakeExecute(ActionResult(True, "Opened Safari."))
    conversation, speaker, output, _ = run(
        ["open safari", "y", "/exit"],
        answers=[ActionRequest("open_app", {"app": "safari"})],
        execute_action=execute_action,
    )
    assert execute_action.actions == [OpenApp("Safari")]
    assert "nova> Opened Safari." in output
    assert conversation.completed == ["Opened Safari."]
    assert speaker.spoken == ["Opened Safari."]


@pytest.mark.parametrize("reply", ["n", "", "no", "maybe"])
def test_anything_but_yes_executes_nothing(reply):
    execute_action = FakeExecute()
    conversation, _, output, _ = run(
        ["open safari", reply, "/exit"],
        answers=[ActionRequest("open_app", {"app": "Safari"})],
        execute_action=execute_action,
    )
    assert execute_action.actions == []
    assert f"nova> {CANCELLED.message}" in output
    assert conversation.completed == [CANCELLED.message]


def test_disallowed_app_is_rejected_and_reported():
    execute_action = FakeExecute()
    _, _, output, _ = run(
        ["open terminal", "/exit"],
        answers=[ActionRequest("open_app", {"app": "Terminal"})],
        execute_action=execute_action,
    )
    assert execute_action.actions == []
    assert any("can't do that" in line for line in output)
    assert output[-1] == "Goodbye."


def test_unavailable_notes_do_not_stop_startup(monkeypatch, capsys, tmp_path):
    def broken_store(path):
        raise StorageError("disk full")

    monkeypatch.setattr(app, "NoteStore", broken_store)
    config = Config(api_key="k", model="m", data_dir=tmp_path)
    assert app._open_notes(config) is None
    assert "disk full" in capsys.readouterr().err


def test_local_transcription_error_allows_retry():
    conversation, _, output, _ = run(
        ["", "", "/exit"], answers=["ok"], heard=[TranscriptionError("model missing"), "retry"]
    )
    assert "[error] model missing" in output
    assert conversation.asked == ["retry"]
