"""Main NOVA window."""

import threading
from collections.abc import Callable
from enum import StrEnum
from html import escape

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nova import __version__
from nova.ai import AIError
from nova.conversation import Conversation
from nova.speech import Recorder, RecordingError, Speaker, SpeechError
from nova.ui.tasks import TaskRunner

_EXPECTED_ERRORS = (AIError, RecordingError)


class State(StrEnum):
    READY = "Ready"
    LISTENING = "Listening… release to send"
    TRANSCRIBING = "Transcribing…"
    THINKING = "Thinking…"
    ERROR = "Error"


class MainWindow(QMainWindow):
    def __init__(
        self,
        conversation: Conversation,
        speaker: Speaker,
        recorder: Recorder,
        transcribe: Callable[[bytes], str],
        runner: TaskRunner | None = None,
    ) -> None:
        super().__init__()
        self._conversation = conversation
        self._speaker = speaker
        self._recorder = recorder
        self._transcribe = transcribe
        self._stop_recording: threading.Event | None = None
        self.runner = runner or TaskRunner(self)

        self.setWindowTitle(f"NOVA {__version__}")
        self.resize(560, 640)

        self.transcript = QTextBrowser()
        self.status = QLabel()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a question and press Enter")
        self.send_button = QPushButton("Send")
        self.talk_button = QPushButton("Hold to talk")
        self.stop_button = QPushButton("Stop speaking")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)

        controls = QHBoxLayout()
        controls.addWidget(self.talk_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        controls.addWidget(self.status)

        layout = QVBoxLayout()
        layout.addWidget(self.transcript)
        layout.addLayout(input_row)
        layout.addLayout(controls)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.input.returnPressed.connect(self.submit_text)
        self.send_button.clicked.connect(self.submit_text)
        self.talk_button.pressed.connect(self.start_listening)
        self.talk_button.released.connect(self.stop_listening)
        self.runner.failed.connect(self._on_failure)

        self.set_state(State.READY)

    def set_state(self, state: State) -> None:
        """Update the status label and enable only the controls valid in this state."""
        self.state = state
        self.status.setText(state.value)
        idle = state in (State.READY, State.ERROR)
        self.input.setEnabled(idle)
        self.send_button.setEnabled(idle)
        # The talk button stays enabled while held, so releasing it is always received.
        self.talk_button.setEnabled(idle or state == State.LISTENING)
        if idle:
            self.input.setFocus()

    # Typed questions

    def submit_text(self) -> None:
        text = self.input.text().strip()
        if not text or self.runner.busy:
            return
        self.input.clear()
        self._add_line("You", text)
        self._ask(text)

    # Voice questions

    def start_listening(self) -> None:
        if self.runner.busy:
            return
        stop = threading.Event()
        self._stop_recording = stop
        self._speaker.stop()
        self.set_state(State.LISTENING)
        self.runner.start(lambda: self._recorder.record(stop.wait), on_success=self._on_recorded)

    def stop_listening(self) -> None:
        if self._stop_recording is not None:
            self._stop_recording.set()
            self._stop_recording = None

    def _on_recorded(self, wav: bytes) -> None:
        self.set_state(State.TRANSCRIBING)
        self.runner.start(lambda: self._transcribe(wav), on_success=self._on_transcribed)

    def _on_transcribed(self, text: str) -> None:
        if not text:
            self._add_notice("No speech detected. Hold the button while you speak.")
            self.set_state(State.READY)
            return
        self._add_line("You (voice)", text)
        self._ask(text)

    # Shared

    def _ask(self, text: str) -> None:
        self._speaker.stop()
        self.set_state(State.THINKING)
        self.runner.start(lambda: self._conversation.ask(text), on_success=self._on_answer)

    def _on_answer(self, answer: str) -> None:
        self._add_line("NOVA", answer)
        self.set_state(State.READY)
        try:
            self._speaker.speak(answer)
        except SpeechError as exc:
            self._add_error(f"Speech unavailable: {exc}")

    def _on_failure(self, error: Exception) -> None:
        self._stop_recording = None
        if isinstance(error, _EXPECTED_ERRORS):
            message = str(error)
        else:
            message = f"Unexpected error: {error!r}"
        self._add_error(message)
        self.set_state(State.ERROR)

    def _add_line(self, who: str, text: str) -> None:
        self.transcript.append(f"<p><b>{who}:</b> {escape(text)}</p>")

    def _add_notice(self, message: str) -> None:
        self.transcript.append(f'<p style="color:#7f8c8d">{escape(message)}</p>')

    def _add_error(self, message: str) -> None:
        self.transcript.append(f'<p style="color:#c0392b">{escape(message)}</p>')
