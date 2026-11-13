"""Main NOVA window."""

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
from nova.speech import Speaker, SpeechError
from nova.ui.tasks import TaskRunner


class State(StrEnum):
    READY = "Ready"
    THINKING = "Thinking…"
    ERROR = "Error"


class MainWindow(QMainWindow):
    def __init__(
        self,
        conversation: Conversation,
        speaker: Speaker,
        runner: TaskRunner | None = None,
    ) -> None:
        super().__init__()
        self._conversation = conversation
        self._speaker = speaker
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
        self.runner.succeeded.connect(self._on_answer)
        self.runner.failed.connect(self._on_failure)

        self.set_state(State.READY)

    def set_state(self, state: State) -> None:
        """Update the status label and enable only the controls valid in this state."""
        self.state = state
        self.status.setText(state.value)
        idle = state in (State.READY, State.ERROR)
        for widget in (self.input, self.send_button, self.talk_button):
            widget.setEnabled(idle)
        if idle:
            self.input.setFocus()

    def submit_text(self) -> None:
        text = self.input.text().strip()
        if not text or self.runner.busy:
            return
        self.input.clear()
        self._speaker.stop()
        self._add_line("You", text)
        self.set_state(State.THINKING)
        self.runner.start(lambda: self._conversation.ask(text))

    def _on_answer(self, answer: str) -> None:
        self._add_line("NOVA", answer)
        self.set_state(State.READY)
        try:
            self._speaker.speak(answer)
        except SpeechError as exc:
            self._add_error(f"Speech unavailable: {exc}")

    def _on_failure(self, error: Exception) -> None:
        if isinstance(error, AIError):
            message = str(error)
        else:
            message = f"Unexpected error: {error!r}"
        self._add_error(message)
        self.set_state(State.ERROR)

    def _add_line(self, who: str, text: str) -> None:
        self.transcript.append(f"<p><b>{who}:</b> {escape(text)}</p>")

    def _add_error(self, message: str) -> None:
        self.transcript.append(f'<p style="color:#c0392b">{escape(message)}</p>')
