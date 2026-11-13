"""Launch the NOVA desktop window."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from nova.actions import ActionPolicy
from nova.ai import GeminiClient
from nova.config import Config, ConfigError, load_config
from nova.conversation import Conversation
from nova.speech import Recorder, Speaker
from nova.storage import NOTES_FILENAME, NoteStore, StorageError
from nova.ui.window import MainWindow


def _open_notes(config: Config) -> NoteStore | None:
    """Open the notes database; if that fails, keep running with notes disabled."""
    try:
        return NoteStore(config.data_dir / NOTES_FILENAME)
    except StorageError as exc:
        QMessageBox.warning(None, "NOVA notes unavailable", str(exc))
        return None


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
    policy = ActionPolicy(config.allowed_apps, config.search_folder, _open_notes(config))
    window = MainWindow(conversation, speaker, recorder, client.transcribe, policy)
    window.show()
    try:
        return app.exec()
    finally:
        window.runner.shutdown()
        speaker.stop()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
