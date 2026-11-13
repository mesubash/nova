"""Main NOVA window."""

import threading
import time
from collections.abc import Callable
from enum import StrEnum
from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
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
MIN_HOLD_SECONDS = 0.3
SPEECH_POLL_MS = 200


class State(StrEnum):
    READY = "Ready"
    LISTENING = "Listening… release to send"
    TRANSCRIBING = "Transcribing…"
    THINKING = "Thinking…"
    SPEAKING = "Speaking…"
    ERROR = "Error"


_IDLE_STATES = (State.READY, State.SPEAKING, State.ERROR)


class MainWindow(QMainWindow):
    def __init__(
        self,
        conversation: Conversation,
        speaker: Speaker,
        recorder: Recorder,
        transcribe: Callable[[bytes], str],
        runner: TaskRunner | None = None,
        min_hold_seconds: float = MIN_HOLD_SECONDS,
    ) -> None:
        super().__init__()
        self._conversation = conversation
        self._speaker = speaker
        self._recorder = recorder
        self._transcribe = transcribe
        self._min_hold_seconds = min_hold_seconds
        self._stop_recording: threading.Event | None = None
        self._listen_started = 0.0
        self.runner = runner or TaskRunner(self)

        self.setWindowTitle(f"NOVA {__version__}")
        self.resize(560, 640)

        self.transcript = QTextBrowser()
        self.status = QLabel()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a question and press Enter")
        self.send_button = QPushButton("Send")
        self.talk_button = QPushButton("Hold to talk")
        self.stop_button = QPushButton("Stop speaking (Esc)")

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

        self._speech_timer = QTimer(self)
        self._speech_timer.setInterval(SPEECH_POLL_MS)
        self._speech_timer.timeout.connect(self._check_speech)

        self.stop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.stop_shortcut.activated.connect(self.stop_speaking)

        self.input.returnPressed.connect(self.submit_text)
        self.send_button.clicked.connect(self.submit_text)
        self.talk_button.pressed.connect(self.start_listening)
        self.talk_button.released.connect(self.stop_listening)
        self.stop_button.clicked.connect(self.stop_speaking)
        self.runner.failed.connect(self._on_failure)

        self.set_state(State.READY)

    def set_state(self, state: State) -> None:
        """Update the status label and enable only the controls valid in this state."""
        self.state = state
        self.status.setText(state.value)
        idle = state in _IDLE_STATES
        self.input.setEnabled(idle)
        self.send_button.setEnabled(idle)
        # The talk button stays enabled while held, so releasing it is always received.
        self.talk_button.setEnabled(idle or state == State.LISTENING)
        self.stop_button.setEnabled(state == State.SPEAKING)
        if state != State.SPEAKING:
            self._speech_timer.stop()
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
        self._listen_started = time.monotonic()
        self._speaker.stop()
        self.set_state(State.LISTENING)
        self.runner.start(lambda: self._recorder.record(stop.wait), on_success=self._on_recorded)

    def stop_listening(self) -> None:
        if self._stop_recording is None:
            return
        self._stop_recording.set()
        self._stop_recording = None
        if time.monotonic() - self._listen_started < self._min_hold_seconds:
            self.runner.cancel()  # the short recording's result will arrive late and be dropped
            self._add_notice("Hold the button while you speak, then release.")
            self.set_state(State.READY)

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

    # Speech output

    def stop_speaking(self) -> None:
        self._speaker.stop()
        if self.state == State.SPEAKING:
            self.set_state(State.READY)

    def _check_speech(self) -> None:
        if self.state == State.SPEAKING and not self._speaker.is_speaking:
            self.set_state(State.READY)

    # Shared

    def _ask(self, text: str) -> None:
        self._speaker.stop()
        self.set_state(State.THINKING)
        self.runner.start(lambda: self._conversation.ask(text), on_success=self._on_answer)

    def _on_answer(self, answer: str) -> None:
        self._add_line("NOVA", answer)
        try:
            self._speaker.speak(answer)
        except SpeechError as exc:
            self._add_error(f"Speech unavailable: {exc}")
            self.set_state(State.READY)
            return
        self.set_state(State.SPEAKING)
        self._speech_timer.start()

    def _on_failure(self, error: Exception) -> None:
        self._stop_recording = None
        if isinstance(error, _EXPECTED_ERRORS):
            message = str(error)
        else:
            message = f"Unexpected error: {error!r}"
        self._add_error(message)
        self.set_state(State.ERROR)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt's method name)
        """Stop recording, playback, and pending work before the window closes."""
        self.stop_listening()
        self.runner.shutdown()
        self._speech_timer.stop()
        self._speaker.stop()
        super().closeEvent(event)

    def _add_line(self, who: str, text: str) -> None:
        self.transcript.append(f"<p><b>{who}:</b> {escape(text)}</p>")

    def _add_notice(self, message: str) -> None:
        self.transcript.append(f'<p style="color:#7f8c8d">{escape(message)}</p>')

    def _add_error(self, message: str) -> None:
        self.transcript.append(f'<p style="color:#c0392b">{escape(message)}</p>')
