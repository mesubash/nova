import threading

import pytest
from PySide6.QtCore import Qt

from nova.actions import CANCELLED, ActionPolicy, ActionRequest, ActionResult, OpenApp
from nova.ai import AIError
from nova.speech import RecordingError, SpeechError
from nova.transcription import TranscriptionError
from nova.ui.window import MainWindow, State


class FakeConversation:
    def __init__(self, answers=(), gate=None):
        self.answers = list(answers)
        self.asked = []
        self.gate = gate
        self.completed = []

    def ask(self, text):
        if self.gate:
            self.gate.wait(2)
        self.asked.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def complete_action(self, outcome):
        self.completed.append(outcome)


class FakeSpeaker:
    def __init__(self, error=None):
        self.error = error
        self.spoken = []
        self.stops = 0
        self.speaking = False

    @property
    def is_speaking(self):
        return self.speaking

    def speak(self, text):
        if self.error:
            raise self.error
        self.spoken.append(text)
        self.speaking = True

    def stop(self):
        self.stops += 1
        self.speaking = False


class FakeRecorder:
    def __init__(self, result=b"wav"):
        self.result = result
        self.calls = 0

    def record(self, wait_for_stop):
        self.calls += 1
        wait_for_stop(5.0)  # blocks until the talk button is released
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeTranscriber:
    def __init__(self, heard="hello"):
        self.heard = heard
        self.received = []

    def __call__(self, wav):
        self.received.append(wav)
        if isinstance(self.heard, BaseException):
            raise self.heard
        return self.heard


@pytest.fixture
def make_window(qtbot):
    windows = []

    def make(
        answers=(),
        *,
        conversation=None,
        speaker=None,
        recorder=None,
        transcriber=None,
        gate=None,
        min_hold_seconds=0.0,
        policy=None,
        confirm=None,
        execute_action=None,
    ):
        window = MainWindow(
            conversation or FakeConversation(answers, gate),
            speaker or FakeSpeaker(),
            recorder or FakeRecorder(),
            transcriber or FakeTranscriber(),
            policy or ActionPolicy(("Safari",), None),
            min_hold_seconds=min_hold_seconds,
            confirm=confirm,
            execute_action=execute_action,
        )
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.runner.shutdown()


SETTLED = (State.READY, State.SPEAKING, State.ERROR)


def ask(qtbot, window, text):
    window.input.setText(text)
    window.send_button.click()
    qtbot.waitUntil(lambda: window.state in SETTLED, timeout=2000)


def talk(qtbot, window):
    window.talk_button.pressed.emit()
    window.talk_button.released.emit()
    qtbot.waitUntil(lambda: window.state in SETTLED, timeout=3000)


def text_of(window):
    return window.transcript.toPlainText()


# Typed questions


def test_window_starts_ready(make_window):
    window = make_window()
    assert window.status.text() == "Ready"
    assert window.transcript.isReadOnly()
    assert window.send_button.isEnabled()
    assert window.talk_button.isEnabled()
    assert not window.stop_button.isEnabled()


def test_typed_question_shows_answer_and_speaks(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(["Kathmandu"], speaker=speaker)
    ask(qtbot, window, "Capital of Nepal?")
    assert "You: Capital of Nepal?" in text_of(window)
    assert "NOVA: Kathmandu" in text_of(window)
    assert speaker.spoken == ["Kathmandu"]
    assert window.state == State.SPEAKING
    assert window.input.text() == ""


def test_enter_key_submits(qtbot, make_window):
    window = make_window(["ok"])
    window.input.setText("hello")
    qtbot.keyClick(window.input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.state in SETTLED, timeout=2000)
    assert "NOVA: ok" in text_of(window)


def test_controls_are_disabled_while_thinking(qtbot, make_window):
    gate = threading.Event()
    recorder = FakeRecorder()
    window = make_window(["done"], gate=gate, recorder=recorder)
    window.input.setText("slow question")
    window.send_button.click()

    assert window.status.text() == "Thinking…"
    assert not window.send_button.isEnabled()
    assert not window.input.isEnabled()
    assert not window.talk_button.isEnabled()

    window.talk_button.pressed.emit()  # even a forced press is ignored while busy
    assert recorder.calls == 0

    gate.set()
    qtbot.waitUntil(lambda: window.state in SETTLED, timeout=2000)
    assert window.send_button.isEnabled()


def test_empty_input_does_nothing(make_window):
    window = make_window()
    window.send_button.click()
    assert window.state == State.READY
    assert text_of(window) == ""


def test_ai_error_is_shown_and_window_recovers(qtbot, make_window):
    window = make_window([AIError("Gemini is busy"), "ok"])
    ask(qtbot, window, "first")
    assert "Gemini is busy" in text_of(window)
    assert window.state == State.ERROR
    assert window.send_button.isEnabled()

    ask(qtbot, window, "second")
    assert "NOVA: ok" in text_of(window)


def test_unexpected_error_is_labelled(qtbot, make_window):
    window = make_window([RuntimeError("bug")])
    ask(qtbot, window, "q")
    assert "Unexpected error" in text_of(window)


def test_speech_failure_keeps_answer_visible(qtbot, make_window):
    window = make_window(["Kathmandu"], speaker=FakeSpeaker(SpeechError("no say")))
    ask(qtbot, window, "q")
    assert "NOVA: Kathmandu" in text_of(window)
    assert "Speech unavailable: no say" in text_of(window)
    assert window.state == State.READY


def test_html_in_text_is_shown_literally(qtbot, make_window):
    window = make_window(["<i>answer</i>"])
    ask(qtbot, window, "<b>question</b>")
    assert "<b>question</b>" in text_of(window)
    assert "<i>answer</i>" in text_of(window)


# Speaking state


def test_stop_button_stops_speech(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(["answer"], speaker=speaker)
    ask(qtbot, window, "q")
    assert window.stop_button.isEnabled()

    window.stop_button.click()
    assert not speaker.speaking
    assert window.state == State.READY
    assert not window.stop_button.isEnabled()


def test_escape_shortcut_stops_speech(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(["answer"], speaker=speaker)
    ask(qtbot, window, "q")
    window.stop_shortcut.activated.emit()
    assert window.state == State.READY


def test_returns_to_ready_when_speech_finishes(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(["answer"], speaker=speaker)
    ask(qtbot, window, "q")
    speaker.speaking = False  # playback ends on its own
    qtbot.waitUntil(lambda: window.state == State.READY, timeout=2000)


def test_can_ask_again_while_speaking(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(["first", "second"], speaker=speaker)
    ask(qtbot, window, "q1")
    assert window.input.isEnabled()
    ask(qtbot, window, "q2")
    assert "NOVA: second" in text_of(window)


# Voice questions


def test_hold_to_talk_records_until_release_then_answers(qtbot, make_window):
    transcriber = FakeTranscriber("what time is it")
    window = make_window(["It is noon"], transcriber=transcriber)

    window.talk_button.pressed.emit()
    assert window.state == State.LISTENING
    assert window.talk_button.isEnabled()
    qtbot.wait(100)
    assert window.state == State.LISTENING  # still recording while held

    window.talk_button.released.emit()
    qtbot.waitUntil(lambda: window.state in SETTLED, timeout=3000)
    assert transcriber.received == [b"wav"]
    assert "You (voice): what time is it" in text_of(window)
    assert "NOVA: It is noon" in text_of(window)


def test_talking_stops_speech_before_recording(make_window):
    speaker = FakeSpeaker()
    window = make_window(speaker=speaker)
    window.talk_button.pressed.emit()
    assert speaker.stops == 1
    window.talk_button.released.emit()


def test_quick_tap_is_ignored_with_a_hint(qtbot, make_window):
    transcriber = FakeTranscriber()
    window = make_window(transcriber=transcriber, min_hold_seconds=0.3)
    window.talk_button.pressed.emit()
    window.talk_button.released.emit()

    assert window.state == State.READY
    assert "Hold the button while you speak" in text_of(window)
    qtbot.wait(200)  # let the cancelled recording finish in the background
    assert transcriber.received == []


def test_no_speech_returns_to_ready_without_asking(qtbot, make_window):
    conversation = FakeConversation()
    window = make_window(conversation=conversation, transcriber=FakeTranscriber(""))
    talk(qtbot, window)
    assert "No speech detected" in text_of(window)
    assert conversation.asked == []
    assert window.state == State.READY


@pytest.mark.parametrize(
    ("recorder", "transcriber", "message"),
    [
        (FakeRecorder(RecordingError("mic denied")), FakeTranscriber(), "mic denied"),
        (FakeRecorder(), FakeTranscriber(AIError("offline")), "offline"),
    ],
)
def test_voice_errors_are_shown_and_window_recovers(
    qtbot, make_window, recorder, transcriber, message
):
    window = make_window(recorder=recorder, transcriber=transcriber)
    talk(qtbot, window)
    assert message in text_of(window)
    assert "Unexpected" not in text_of(window)
    assert window.state == State.ERROR
    assert window.talk_button.isEnabled()


# Shutdown


def test_closing_while_recording_stops_everything(qtbot, make_window):
    speaker = FakeSpeaker()
    transcriber = FakeTranscriber()
    window = make_window(speaker=speaker, transcriber=transcriber)
    window.talk_button.pressed.emit()

    window.close()

    assert not window.runner.busy
    assert speaker.stops >= 2  # once before recording, once on close
    qtbot.wait(200)  # the recording is released and its late result dropped
    assert transcriber.received == []


# Desktop actions


class FakeExecute:
    def __init__(self, result=None):
        self.result = result or ActionResult(True, "Done.")
        self.actions = []

    def __call__(self, action):
        self.actions.append(action)
        return self.result


def test_confirmed_action_runs_and_is_reported(qtbot, make_window):
    execute_action = FakeExecute(ActionResult(True, "Opened Safari."))
    conversation = FakeConversation([ActionRequest("open_app", {"app": "safari"})])
    speaker = FakeSpeaker()
    window = make_window(
        conversation=conversation,
        speaker=speaker,
        confirm=lambda action: True,
        execute_action=execute_action,
    )
    ask(qtbot, window, "open safari")
    assert execute_action.actions == [OpenApp("Safari")]
    assert "NOVA: Opened Safari." in text_of(window)
    assert conversation.completed == ["Opened Safari."]
    assert speaker.spoken == ["Opened Safari."]


def test_declined_action_executes_nothing(qtbot, make_window):
    execute_action = FakeExecute()
    conversation = FakeConversation([ActionRequest("open_app", {"app": "Safari"})])
    window = make_window(
        conversation=conversation,
        confirm=lambda action: False,
        execute_action=execute_action,
    )
    ask(qtbot, window, "open safari")
    assert execute_action.actions == []
    assert CANCELLED.message in text_of(window)
    assert conversation.completed == [CANCELLED.message]


def test_disallowed_app_is_rejected_without_asking(qtbot, make_window):
    asked = []
    execute_action = FakeExecute()
    window = make_window(
        conversation=FakeConversation([ActionRequest("open_app", {"app": "Terminal"})]),
        confirm=lambda action: asked.append(action) or True,
        execute_action=execute_action,
    )
    ask(qtbot, window, "open terminal")
    assert asked == []
    assert execute_action.actions == []
    assert "can't do that" in text_of(window)


def test_search_runs_without_confirmation_and_lists_results(qtbot, make_window, tmp_path):
    asked = []
    execute_action = FakeExecute(ActionResult(True, "Found 1 file.", ("notes/plan.txt",)))
    window = make_window(
        conversation=FakeConversation([ActionRequest("search_files", {"query": "plan"})]),
        policy=ActionPolicy((), tmp_path),
        confirm=lambda action: asked.append(action) or True,
        execute_action=execute_action,
    )
    ask(qtbot, window, "find my plan")
    assert asked == []
    assert "• notes/plan.txt" in text_of(window)


def test_local_transcription_error_is_shown_as_expected(qtbot, make_window):
    window = make_window(transcriber=FakeTranscriber(TranscriptionError("model missing")))
    talk(qtbot, window)
    assert "model missing" in text_of(window)
    assert "Unexpected" not in text_of(window)
    assert window.state == State.ERROR
