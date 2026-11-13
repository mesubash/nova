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

SYSTEM_INSTRUCTION = (
    "You are NOVA, a personal voice assistant. Your replies are read aloud, so answer "
    "in short, natural spoken sentences, usually one to three. Do not use markdown, "
    "bullet points, tables, emoji, or code blocks unless the user asks for them."
)
TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio exactly as spoken. Reply with only the "
    "transcript. If there is no intelligible speech, reply with exactly: [no speech]"
)
NO_SPEECH = "[no speech]"


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
        self._chat_config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
        self._transcribe_config = types.GenerateContentConfig(temperature=0)
        self._client = client or genai.Client(
            api_key=config.api_key,
            http_options=types.HttpOptions(timeout=int(config.request_timeout_seconds * 1000)),
        )

    def reply(self, messages: Sequence[Message]) -> str:
        if not messages:
            raise ValueError("messages must not be empty")

        contents = [_to_content(message) for message in messages]
        text = self._with_retries(contents, self._chat_config)
        if not text:
            raise AIError("Gemini returned an empty response.")
        return text

    def transcribe(self, wav: bytes) -> str:
        """Return the transcript of WAV audio, or "" if it contains no speech."""
        if not wav:
            raise ValueError("wav must not be empty")

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=TRANSCRIBE_PROMPT),
                    types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                ],
            )
        ]
        text = self._with_retries(contents, self._transcribe_config)
        return "" if text.lower() == NO_SPEECH else text

    def close(self) -> None:
        self._client.close()

    def _with_retries(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> str:
        attempt = 1
        while True:
            try:
                return self._request_once(contents, config)
            except AIError as exc:
                if not exc.retryable or attempt >= MAX_ATTEMPTS:
                    raise
            self._sleep(RETRY_DELAY_SECONDS * attempt)
            attempt += 1

    def _request_once(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
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

        return (response.text or "").strip()


def _to_content(message: Message) -> types.Content:
    return types.Content(
        role=_GEMINI_ROLES[message.role],
        parts=[types.Part(text=message.text)],
    )
