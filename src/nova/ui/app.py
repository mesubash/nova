"""Launch the NOVA desktop window."""

import subprocess
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from nova.actions import ActionPolicy
from nova.ai import GeminiClient
from nova.config import (
    Config,
    ConfigError,
    ensure_user_config,
    load_config,
    user_config_path,
)
from nova.conversation import Conversation
from nova.speech import Recorder, Speaker
from nova.storage import NOTES_FILENAME, NoteStore, StorageError
from nova.transcription import make_transcriber
from nova.ui.window import MainWindow


def _explain_config_error(exc: ConfigError) -> None:
    """Show what is missing and offer to open (and create) the settings file."""
    box = QMessageBox(
        QMessageBox.Icon.Critical,
        "NOVA needs setup",
        f"{exc}\n\nThe desktop app reads its settings from:\n{user_config_path()}",
    )
    open_button = box.addButton("Open settings file", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() is open_button:
        subprocess.run(["open", "-e", str(ensure_user_config())], check=False)


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
        _explain_config_error(exc)
        return 1

    client = GeminiClient(config)
    speaker = Speaker(devanagari_voice=config.devanagari_voice)
    recorder = Recorder(config.max_recording_seconds)
    conversation = Conversation(client, config.max_history_turns)
    policy = ActionPolicy(config.allowed_apps, config.search_folder, _open_notes(config))
    window = MainWindow(conversation, speaker, recorder, make_transcriber(config, client), policy)
    window.show()
    try:
        return app.exec()
    finally:
        window.runner.shutdown()
        speaker.stop()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
