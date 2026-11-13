"""Session history and turn handling. No network code lives here."""

from collections.abc import Sequence
from typing import Protocol

from nova.actions import ActionRequest
from nova.ai import Message


class Responder(Protocol):
    def reply(self, messages: Sequence[Message]) -> str | ActionRequest: ...


class Conversation:
    def __init__(self, responder: Responder, max_turns: int) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be greater than 0")
        self._responder = responder
        self._max_messages = max_turns * 2
        self._history: list[Message] = []
        self._pending: Message | None = None

    @property
    def history(self) -> tuple[Message, ...]:
        return tuple(self._history)

    def ask(self, text: str) -> str | ActionRequest:
        """Return the model's answer, or an action it proposes.

        A proposed action is not added to history until complete_action()
        reports what actually happened.
        """
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")

        self._pending = None
        user_message = Message("user", text)
        reply = self._responder.reply([*self._history, user_message])
        if isinstance(reply, ActionRequest):
            self._pending = user_message
            return reply
        self._remember(user_message, reply)
        return reply

    def complete_action(self, outcome: str) -> None:
        """Record what happened to the action proposed by the last question."""
        if self._pending is None:
            return
        self._remember(self._pending, outcome)
        self._pending = None

    def _remember(self, user_message: Message, answer: str) -> None:
        self._history += [user_message, Message("assistant", answer)]
        del self._history[: -self._max_messages]
