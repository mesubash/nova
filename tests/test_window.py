import threading

import pytest
from PySide6.QtCore import Qt

from nova.ai import AIError
from nova.speech import SpeechError
from nova.ui.window import MainWindow, State


class FakeConversation:
    def __init__(self, answers=(), gate=None):
        self.answers = list(answers)
        self.asked = []
        self.gate = gate

    def ask(self, text):
        if self.gate:
            self.gate.wait(2)
        self.asked.append(text)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class FakeSpeaker:
    def __init__(self, error=None):
        self.error = error
        self.spoken = []
        self.stops = 0

    def speak(self, text):
        if self.error:
            raise self.error
        self.spoken.append(text)

    def stop(self):
        self.stops += 1


@pytest.fixture
def make_window(qtbot):
    windows = []

    def make(answers=(), speaker=None, gate=None):
        window = MainWindow(FakeConversation(answers, gate), speaker or FakeSpeaker())
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield make
    for window in windows:
        window.runner.shutdown()


def ask(qtbot, window, text):
    window.input.setText(text)
    window.send_button.click()
    qtbot.waitUntil(lambda: window.state != State.THINKING, timeout=2000)


def text_of(window):
    return window.transcript.toPlainText()


def test_window_starts_ready(make_window):
    window = make_window()
    assert window.status.text() == "Ready"
    assert window.transcript.isReadOnly()
    assert window.send_button.isEnabled()


def test_typed_question_shows_answer_and_speaks(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(answers=["Kathmandu"], speaker=speaker)
    ask(qtbot, window, "Capital of Nepal?")
    assert "You: Capital of Nepal?" in text_of(window)
    assert "NOVA: Kathmandu" in text_of(window)
    assert speaker.spoken == ["Kathmandu"]
    assert window.state == State.READY
    assert window.input.text() == ""


def test_enter_key_submits(qtbot, make_window):
    window = make_window(answers=["ok"])
    window.input.setText("hello")
    qtbot.keyClick(window.input, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.state == State.READY, timeout=2000)
    assert "NOVA: ok" in text_of(window)


def test_controls_are_disabled_while_thinking(qtbot, make_window):
    gate = threading.Event()
    window = make_window(answers=["done"], gate=gate)
    window.input.setText("slow question")
    window.send_button.click()

    assert window.state == State.THINKING
    assert window.status.text() == "Thinking…"
    assert not window.send_button.isEnabled()
    assert not window.input.isEnabled()
    assert not window.talk_button.isEnabled()

    gate.set()
    qtbot.waitUntil(lambda: window.state == State.READY, timeout=2000)
    assert window.send_button.isEnabled()


def test_empty_input_does_nothing(make_window):
    window = make_window()
    window.send_button.click()
    assert window.state == State.READY
    assert text_of(window) == ""


def test_ai_error_is_shown_and_window_recovers(qtbot, make_window):
    window = make_window(answers=[AIError("Gemini is busy"), "ok"])
    ask(qtbot, window, "first")
    assert "Gemini is busy" in text_of(window)
    assert window.state == State.ERROR
    assert window.send_button.isEnabled()

    ask(qtbot, window, "second")
    assert "NOVA: ok" in text_of(window)
    assert window.state == State.READY


def test_unexpected_error_is_labelled(qtbot, make_window):
    window = make_window(answers=[RuntimeError("bug")])
    ask(qtbot, window, "q")
    assert "Unexpected error" in text_of(window)


def test_speech_failure_keeps_answer_visible(qtbot, make_window):
    window = make_window(answers=["Kathmandu"], speaker=FakeSpeaker(SpeechError("no say")))
    ask(qtbot, window, "q")
    assert "NOVA: Kathmandu" in text_of(window)
    assert "Speech unavailable: no say" in text_of(window)


def test_new_question_stops_current_speech(qtbot, make_window):
    speaker = FakeSpeaker()
    window = make_window(answers=["a"], speaker=speaker)
    ask(qtbot, window, "q")
    assert speaker.stops >= 1


def test_html_in_text_is_shown_literally(qtbot, make_window):
    window = make_window(answers=["<i>answer</i>"])
    ask(qtbot, window, "<b>question</b>")
    assert "<b>question</b>" in text_of(window)
    assert "<i>answer</i>" in text_of(window)
