"""Entry point for `python -m nova` and the `nova` command."""

import sys
from collections.abc import Callable

from nova import __version__
from nova.ai import AIError, GeminiClient
from nova.config import ConfigError, load_config
from nova.conversation import Conversation
from nova.speech import Speaker, SpeechError

EXIT_COMMAND = "/exit"
STOP_COMMAND = "/stop"


def run_loop(
    conversation: Conversation,
    speaker: Speaker,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    write(
        f"NOVA {__version__}. Press Enter or type {STOP_COMMAND} to stop speaking, "
        f"{EXIT_COMMAND} to quit."
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
        if not text or command == STOP_COMMAND:
            speaker.stop()
            continue

        speaker.stop()
        try:
            answer = conversation.ask(text)
        except AIError as exc:
            write(f"[error] {exc}")
            continue
        except KeyboardInterrupt:
            write("[cancelled]")
            continue

        write(f"nova> {answer}")
        try:
            speaker.speak(answer)
        except SpeechError as exc:
            write(f"[speech unavailable] {exc}")

    speaker.stop()
    write("Goodbye.")


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    client = GeminiClient(config)
    speaker = Speaker()
    try:
        run_loop(Conversation(client, config.max_history_turns), speaker)
    finally:
        speaker.stop()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
