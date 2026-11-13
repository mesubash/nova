"""Launch the NOVA desktop window."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from nova.ai import GeminiClient
from nova.config import ConfigError, load_config
from nova.conversation import Conversation
from nova.speech import Recorder, Speaker
from nova.ui.window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    try:
        config = load_config()
    except ConfigError as exc:
        QMessageBox.critical(None, "NOVA configuration error", str(exc))
        return 1

    client = GeminiClient(config)
    speaker = Speaker()
    recorder = Recorder(config.max_recording_seconds)
    conversation = Conversation(client, config.max_history_turns)
    window = MainWindow(conversation, speaker, recorder, client.transcribe)
    window.show()
    try:
        return app.exec()
    finally:
        window.runner.shutdown()
        speaker.stop()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
