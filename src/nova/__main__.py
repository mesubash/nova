"""Entry point for `python -m nova` and the `nova` command."""

import select
import sys
from collections.abc import Callable

from nova import __version__
from nova.ai import AIError, GeminiClient
from nova.config import ConfigError, load_config
from nova.conversation import Conversation
from nova.speech import Recorder, RecordingError, Speaker, SpeechError

EXIT_COMMAND = "/exit"
STOP_COMMAND = "/stop"


def run_loop(
    conversation: Conversation,
    speaker: Speaker,
    listen: Callable[[], str],
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    write(
        f"NOVA {__version__}. Type a question, or press Enter to speak. "
        f"{STOP_COMMAND} stops speech, {EXIT_COMMAND} quits."
    )
    while True:
        try:
            text = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            break

        command = text.lower()
        if command == EXIT_COMMAND:
            break
        speaker.stop()
        if command == STOP_COMMAND:
            continue
        if not text:
            text = _listen(listen, write)
            if not text:
                continue
        _answer(conversation, speaker, text, write)

    speaker.stop()
    write("Goodbye.")


def _listen(listen: Callable[[], str], write: Callable[[str], None]) -> str:
    """Capture and transcribe one spoken question. Returns "" if nothing usable."""
    try:
        text = listen()
    except (RecordingError, AIError) as exc:
        write(f"[error] {exc}")
        return ""
    except KeyboardInterrupt:
        write("[cancelled]")
        return ""

    if not text:
        write("[no speech detected] Press Enter to try again, or type your question.")
        return ""
    write(f"you (voice)> {text}")
    return text


def _answer(
    conversation: Conversation, speaker: Speaker, text: str, write: Callable[[str], None]
) -> None:
    write("[thinking]")
    try:
        answer = conversation.ask(text)
    except AIError as exc:
        write(f"[error] {exc}")
        return
    except KeyboardInterrupt:
        write("[cancelled]")
        return

    write(f"nova> {answer}")
    try:
        speaker.speak(answer)
    except SpeechError as exc:
        write(f"[speech unavailable] {exc}")


def wait_for_enter(timeout: float) -> None:
    """Block until the user presses Enter or `timeout` seconds pass."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        sys.stdin.readline()


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    client = GeminiClient(config)
    speaker = Speaker()
    recorder = Recorder(config.max_recording_seconds)

    def listen() -> str:
        print(
            f"[listening] Speak, then press Enter "
            f"(stops by itself after {config.max_recording_seconds:g}s)."
        )
        wav = recorder.record(wait_for_enter)
        print("[transcribing]")
        return client.transcribe(wav)

    try:
        run_loop(Conversation(client, config.max_history_turns), speaker, listen)
    finally:
        speaker.stop()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
