"""Session history and turn handling. No network code lives here."""

from collections.abc import Sequence
from typing import Protocol

from nova.ai import Message


class Responder(Protocol):
    def reply(self, messages: Sequence[Message]) -> str: ...


class Conversation:
    def __init__(self, responder: Responder, max_turns: int) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be greater than 0")
        self._responder = responder
        self._max_messages = max_turns * 2
        self._history: list[Message] = []

    @property
    def history(self) -> tuple[Message, ...]:
        return tuple(self._history)

    def ask(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")

        user_message = Message("user", text)
        reply = self._responder.reply([*self._history, user_message])

        self._history += [user_message, Message("assistant", reply)]
        del self._history[: -self._max_messages]
        return reply
