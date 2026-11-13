"""Entry point for `python -m nova` and the `nova` command."""

import select
import sys
from collections.abc import Callable

from nova import __version__
from nova.actions import Action, ActionPolicy, ActionRequest, ActionResult, execute, run_action
from nova.ai import AIError, GeminiClient
from nova.config import ConfigError, load_config
from nova.conversation import Conversation
from nova.speech import Recorder, RecordingError, Speaker, SpeechError

EXIT_COMMAND = "/exit"
STOP_COMMAND = "/stop"

Read = Callable[[str], str]
Write = Callable[[str], None]
ExecuteAction = Callable[[Action], ActionResult]


def run_loop(
    conversation: Conversation,
    speaker: Speaker,
    listen: Callable[[], str],
    policy: ActionPolicy,
    read: Read = input,
    write: Write = print,
    execute_action: ExecuteAction = execute,
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
        _answer(conversation, speaker, text, policy, read, write, execute_action)

    speaker.stop()
    write("Goodbye.")


def _listen(listen: Callable[[], str], write: Write) -> str:
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
    conversation: Conversation,
    speaker: Speaker,
    text: str,
    policy: ActionPolicy,
    read: Read,
    write: Write,
    execute_action: ExecuteAction,
) -> None:
    write("[thinking]")
    try:
        reply = conversation.ask(text)
    except AIError as exc:
        write(f"[error] {exc}")
        return
    except KeyboardInterrupt:
        write("[cancelled]")
        return

    details: tuple[str, ...] = ()
    if isinstance(reply, ActionRequest):
        result = run_action(reply, policy, lambda action: _confirm(action, read), execute_action)
        conversation.complete_action(result.message)
        reply, details = result.message, result.details

    write(f"nova> {reply}")
    for item in details:
        write(f"  - {item}")
    try:
        speaker.speak(reply)
    except SpeechError as exc:
        write(f"[speech unavailable] {exc}")


def _confirm(action: Action, read: Read) -> bool:
    """Ask before an action with side effects. Anything but an explicit yes means no."""
    try:
        answer = read(f"{action.describe()}? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("y", "yes")


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
    policy = ActionPolicy(config.allowed_apps, config.search_folder)

    def listen() -> str:
        print(
            f"[listening] Speak, then press Enter "
            f"(stops by itself after {config.max_recording_seconds:g}s)."
        )
        wav = recorder.record(wait_for_enter)
        print("[transcribing]")
        return client.transcribe(wav)

    try:
        run_loop(Conversation(client, config.max_history_turns), speaker, listen, policy)
    finally:
        speaker.stop()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
