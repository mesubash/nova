"""The only module that talks to the Gemini API."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx2
from google import genai
from google.genai import errors, types

from nova.actions import ActionRequest
from nova.config import Config

Role = Literal["user", "assistant"]

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_GEMINI_ROLES = {"user": "user", "assistant": "model"}

SYSTEM_INSTRUCTION = (
    "You are NOVA, a personal voice assistant. Your replies are read aloud, so answer "
    "in short, natural spoken sentences, usually one to three. Do not use markdown, "
    "bullet points, tables, emoji, or code blocks unless the user asks for them. "
    "You can open allowed apps, open web pages, and search the user's approved folder "
    "by file name with the provided functions. Call a function only when the user "
    "clearly asks for that action. Use the note functions only when the user explicitly "
    "asks to save, show, find, change, or delete notes."
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
        self._chat_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[_action_tool(config.allowed_apps)],
        )
        self._transcribe_config = types.GenerateContentConfig(temperature=0)
        self._client = client or genai.Client(
            api_key=config.api_key,
            http_options=types.HttpOptions(timeout=int(config.request_timeout_seconds * 1000)),
        )

    def reply(self, messages: Sequence[Message]) -> str | ActionRequest:
        if not messages:
            raise ValueError("messages must not be empty")

        contents = [_to_content(message) for message in messages]
        response = self._with_retries(contents, self._chat_config)
        calls = response.function_calls or []
        if calls:
            call = calls[0]
            return ActionRequest(call.name or "", call.args if call.args is not None else {})
        text = (response.text or "").strip()
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
        response = self._with_retries(contents, self._transcribe_config)
        text = (response.text or "").strip()
        return "" if text.lower() == NO_SPEECH else text

    def close(self) -> None:
        self._client.close()

    def _with_retries(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
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
    ) -> types.GenerateContentResponse:
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

        return response


def _to_content(message: Message) -> types.Content:
    return types.Content(
        role=_GEMINI_ROLES[message.role],
        parts=[types.Part(text=message.text)],
    )


def _action_tool(allowed_apps: tuple[str, ...]) -> types.Tool:
    """Describe NOVA's actions to Gemini. Descriptions guide the model; validation decides."""
    apps = ", ".join(allowed_apps) or "none"

    def declaration(name: str, description: str, **params: tuple[str, str]) -> dict:
        result: dict = {"name": name, "description": description}
        if params:
            result["parameters"] = {
                "type": "object",
                "properties": {
                    param: {"type": kind, "description": text}
                    for param, (kind, text) in params.items()
                },
                "required": list(params),
            }
        return result

    note_number = ("integer", "The note number, for example 3.")
    return types.Tool(
        function_declarations=[
            declaration(
                "open_app",
                f"Open an app on the user's Mac. Allowed apps: {apps}.",
                app=("string", "The app name, for example Safari."),
            ),
            declaration(
                "open_url",
                "Open a web page in the user's default browser.",
                url=("string", "A full http or https address."),
            ),
            declaration(
                "search_files",
                "Find files in the user's approved folder whose names contain the query.",
                query=("string", "Part of a file name, without any folder path."),
            ),
            declaration(
                "save_note",
                "Save a personal note. Only when the user explicitly asks to save or note "
                "something.",
                text=("string", "The note text, in the user's own words."),
            ),
            declaration("list_notes", "Show the user's most recent saved notes."),
            declaration(
                "search_notes",
                "Find saved notes that contain all of the given words.",
                query=("string", "Words to look for."),
            ),
            declaration(
                "edit_note",
                "Replace the text of a saved note, identified by its number.",
                id=note_number,
                text=("string", "The complete new note text."),
            ),
            declaration(
                "delete_note",
                "Delete a saved note, identified by its number.",
                id=note_number,
            ),
        ]
    )
