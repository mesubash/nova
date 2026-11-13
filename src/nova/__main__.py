"""Entry point for `python -m nova` and the `nova` command."""

import sys
from collections.abc import Callable

from nova import __version__
from nova.ai import AIError, GeminiClient
from nova.config import ConfigError, load_config
from nova.conversation import Conversation

EXIT_COMMAND = "/exit"


def run_loop(
    conversation: Conversation,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    write(f"NOVA {__version__}. Type {EXIT_COMMAND} to quit.")
    while True:
        try:
            text = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            break

        if not text:
            continue
        if text.lower() == EXIT_COMMAND:
            break

        try:
            answer = conversation.ask(text)
        except AIError as exc:
            write(f"[error] {exc}")
            continue
        except KeyboardInterrupt:
            write("[cancelled]")
            continue

        write(f"nova> {answer}")

    write("Goodbye.")


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    client = GeminiClient(config)
    try:
        run_loop(Conversation(client, config.max_history_turns))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
