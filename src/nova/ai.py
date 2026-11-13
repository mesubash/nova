"""The only module that talks to the Gemini API."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx2
from google import genai
from google.genai import errors, types

from nova.config import Config

Role = Literal["user", "assistant"]

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_GEMINI_ROLES = {"user": "user", "assistant": "model"}


@dataclass(frozen=True)
class Message:
    role: Role
    text: str


class AIError(Exception):
    """A model request failed. The message is safe to show the user."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class GeminiClient:
    def __init__(
        self,
        config: Config,
        client: genai.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._model = config.model
        self._sleep = sleep
        self._client = client or genai.Client(
            api_key=config.api_key,
            http_options=types.HttpOptions(timeout=int(config.request_timeout_seconds * 1000)),
        )

    def reply(self, messages: Sequence[Message]) -> str:
        if not messages:
            raise ValueError("messages must not be empty")

        contents = [_to_content(message) for message in messages]
        attempt = 1
        while True:
            try:
                return self._request_once(contents)
            except AIError as exc:
                if not exc.retryable or attempt >= MAX_ATTEMPTS:
                    raise
            self._sleep(RETRY_DELAY_SECONDS * attempt)
            attempt += 1

    def close(self) -> None:
        self._client.close()

    def _request_once(self, contents: list[types.Content]) -> str:
        try:
            response = self._client.models.generate_content(model=self._model, contents=contents)
        except httpx2.TimeoutException as exc:
            raise AIError("The request timed out. Please try again.") from exc
        except httpx2.TransportError as exc:
            raise AIError("Could not reach Gemini. Check your internet connection.") from exc
        except errors.ClientError as exc:
            raise AIError(f"Gemini rejected the request ({exc.code}): {exc.message}") from exc
        except errors.APIError as exc:
            raise AIError(
                f"Gemini returned an error ({exc.code}): {exc.message} Try again shortly.",
                retryable=exc.code in _RETRYABLE_STATUS_CODES,
            ) from exc

        text = (response.text or "").strip()
        if not text:
            raise AIError("Gemini returned an empty response.")
        return text


def _to_content(message: Message) -> types.Content:
    return types.Content(
        role=_GEMINI_ROLES[message.role],
        parts=[types.Part(text=message.text)],
    )
