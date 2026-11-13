from unittest.mock import Mock

import httpx2
import pytest
from google.genai import errors, types

from nova.actions import ActionRequest
from nova.ai import (
    MAX_ATTEMPTS,
    NO_SPEECH,
    RETRY_DELAY_SECONDS,
    SYSTEM_INSTRUCTION,
    TRANSCRIBE_PROMPT,
    AIError,
    GeminiClient,
    Message,
)
from nova.config import Config


def fake_response(text=None, calls=None):
    return Mock(text=text, function_calls=calls)


CONFIG = Config(api_key="test-key", model="test-model")
HISTORY = [Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "And?")]
WAV = b"RIFF-fake-wav-bytes"


def server_error(code=503):
    return errors.ServerError(
        code, {"error": {"code": code, "message": "busy", "status": "UNAVAILABLE"}}
    )


def client_error():
    return errors.ClientError(
        400, {"error": {"code": 400, "message": "bad key", "status": "INVALID_ARGUMENT"}}
    )


def make_client(**generate_behavior):
    fake = Mock()
    fake.models.generate_content = Mock(**generate_behavior)
    sleeps = []
    client = GeminiClient(CONFIG, client=fake, sleep=sleeps.append)
    return client, fake, sleeps


def test_reply_returns_stripped_text():
    client, _, _ = make_client(return_value=fake_response(text="  Answer  "))
    assert client.reply(HISTORY) == "Answer"


def test_reply_sends_model_and_mapped_roles():
    client, fake, _ = make_client(return_value=fake_response(text="ok"))
    client.reply(HISTORY)
    kwargs = fake.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert [c.role for c in kwargs["contents"]] == ["user", "model", "user"]
    assert kwargs["contents"][2].parts[0].text == "And?"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx2.ReadTimeout("slow"), "timed out"),
        (httpx2.ConnectError("offline"), "internet connection"),
        (client_error(), "rejected"),
        (server_error(), "Try again"),
    ],
)
def test_failures_become_ai_error(error, expected):
    client, _, _ = make_client(side_effect=error)
    with pytest.raises(AIError, match=expected):
        client.reply(HISTORY)


def test_server_error_is_retried_then_succeeds():
    client, fake, sleeps = make_client(side_effect=[server_error(), fake_response(text="ok")])
    assert client.reply(HISTORY) == "ok"
    assert fake.models.generate_content.call_count == 2
    assert sleeps == [RETRY_DELAY_SECONDS]


def test_gives_up_after_max_attempts():
    client, fake, sleeps = make_client(side_effect=server_error())
    with pytest.raises(AIError):
        client.reply(HISTORY)
    assert fake.models.generate_content.call_count == MAX_ATTEMPTS
    assert sleeps == [RETRY_DELAY_SECONDS * n for n in range(1, MAX_ATTEMPTS)]


@pytest.mark.parametrize(
    "error", [httpx2.ReadTimeout("slow"), httpx2.ConnectError("offline"), client_error()]
)
def test_non_transient_errors_are_not_retried(error):
    client, fake, sleeps = make_client(side_effect=error)
    with pytest.raises(AIError):
        client.reply(HISTORY)
    assert fake.models.generate_content.call_count == 1
    assert sleeps == []


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_response_raises(text):
    client, _, _ = make_client(return_value=fake_response(text=text))
    with pytest.raises(AIError, match="empty"):
        client.reply(HISTORY)


def test_empty_history_is_a_programming_error():
    client, _, _ = make_client(return_value=fake_response(text="ok"))
    with pytest.raises(ValueError):
        client.reply([])


def test_close_closes_underlying_client():
    client, fake, _ = make_client()
    client.close()
    fake.close.assert_called_once()


def test_timeout_is_passed_in_milliseconds(monkeypatch):
    fake_class = Mock()
    monkeypatch.setattr("nova.ai.genai.Client", fake_class)
    GeminiClient(Config(api_key="k", model="m", request_timeout_seconds=2.5))
    assert fake_class.call_args.kwargs["http_options"].timeout == 2500


def test_reply_sends_spoken_style_system_instruction():
    client, fake, _ = make_client(return_value=fake_response(text="ok"))
    client.reply(HISTORY)
    config = fake.models.generate_content.call_args.kwargs["config"]
    assert config.system_instruction == SYSTEM_INSTRUCTION


def test_transcribe_sends_prompt_and_audio_without_chat_instruction():
    client, fake, _ = make_client(return_value=fake_response(text="what time is it"))
    assert client.transcribe(WAV) == "what time is it"
    kwargs = fake.models.generate_content.call_args.kwargs
    parts = kwargs["contents"][0].parts
    assert parts[0].text == TRANSCRIBE_PROMPT
    assert parts[1].inline_data.mime_type == "audio/wav"
    assert parts[1].inline_data.data == WAV
    assert kwargs["config"].system_instruction is None


@pytest.mark.parametrize("text", [NO_SPEECH, NO_SPEECH.upper(), "", None])
def test_transcribe_returns_empty_string_when_no_speech(text):
    client, _, _ = make_client(return_value=fake_response(text=text))
    assert client.transcribe(WAV) == ""


def test_transcribe_retries_transient_errors():
    client, fake, _ = make_client(side_effect=[server_error(), fake_response(text="hello")])
    assert client.transcribe(WAV) == "hello"
    assert fake.models.generate_content.call_count == 2


def test_transcribe_rejects_empty_audio():
    client, _, _ = make_client()
    with pytest.raises(ValueError):
        client.transcribe(b"")


def test_function_call_becomes_untrusted_action_request():
    call = types.FunctionCall(name="open_app", args={"app": "Safari"})
    client, _, _ = make_client(return_value=fake_response(calls=[call]))
    assert client.reply(HISTORY) == ActionRequest("open_app", {"app": "Safari"})


def test_function_call_without_args_has_empty_args():
    call = types.FunctionCall(name="open_app")
    client, _, _ = make_client(return_value=fake_response(calls=[call]))
    assert client.reply(HISTORY) == ActionRequest("open_app", {})


def test_chat_declares_actions_and_lists_allowed_apps():
    client, fake, _ = make_client(return_value=fake_response(text="ok"))
    client.reply(HISTORY)
    tool = fake.models.generate_content.call_args.kwargs["config"].tools[0]
    names = [declaration.name for declaration in tool.function_declarations]
    assert names == [
        "open_app",
        "open_url",
        "search_files",
        "save_note",
        "list_notes",
        "search_notes",
        "edit_note",
        "delete_note",
    ]
    assert "Safari" in tool.function_declarations[0].description


def test_transcription_declares_no_actions():
    client, fake, _ = make_client(return_value=fake_response(text="hello"))
    client.transcribe(WAV)
    assert fake.models.generate_content.call_args.kwargs["config"].tools is None


def test_note_declarations_have_the_right_parameters():
    client, fake, _ = make_client(return_value=fake_response(text="ok"))
    client.reply(HISTORY)
    tool = fake.models.generate_content.call_args.kwargs["config"].tools[0]
    by_name = {declaration.name: declaration for declaration in tool.function_declarations}
    assert by_name["list_notes"].parameters is None
    assert by_name["edit_note"].parameters.required == ["id", "text"]


# Rate limits


def rate_limited(message="Quota exceeded.", retry_info=None):
    error = {"code": 429, "message": message, "status": "RESOURCE_EXHAUSTED"}
    if retry_info is not None:
        error["details"] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_info}
        ]
    return errors.ClientError(429, {"error": error})


def test_short_rate_limit_waits_the_requested_time_then_retries():
    client, fake, sleeps = make_client(
        side_effect=[rate_limited(retry_info="3s"), fake_response(text="ok")]
    )
    assert client.reply(HISTORY) == "ok"
    assert sleeps == [3.0]
    assert fake.models.generate_content.call_count == 2


def test_wait_is_read_from_the_message_when_retry_info_is_missing():
    client, _, sleeps = make_client(
        side_effect=[rate_limited("Please retry in 2.5s."), fake_response(text="ok")]
    )
    assert client.reply(HISTORY) == "ok"
    assert sleeps == [2.5]


def test_rate_limit_is_retried_only_once():
    client, fake, sleeps = make_client(side_effect=rate_limited(retry_info="1s"))
    with pytest.raises(AIError, match="request limit"):
        client.reply(HISTORY)
    assert fake.models.generate_content.call_count == 2
    assert sleeps == [1.0]


def test_long_rate_limit_fails_fast_and_says_how_long_to_wait():
    client, fake, sleeps = make_client(side_effect=rate_limited("Please retry in 30.2s."))
    with pytest.raises(AIError, match="about 31 seconds"):
        client.reply(HISTORY)
    assert fake.models.generate_content.call_count == 1
    assert sleeps == []


def test_rate_limit_without_a_wait_time_says_wait_a_minute():
    client, fake, _ = make_client(side_effect=rate_limited("Quota exceeded."))
    with pytest.raises(AIError, match="Wait a minute"):
        client.reply(HISTORY)
    assert fake.models.generate_content.call_count == 1


def test_transcription_also_waits_on_short_rate_limits():
    client, _, sleeps = make_client(
        side_effect=[rate_limited(retry_info="2s"), fake_response(text="hello")]
    )
    assert client.transcribe(WAV) == "hello"
    assert sleeps == [2.0]


def test_nepali_mode_uses_the_mixed_language_prompt():
    from nova.ai import TRANSCRIBE_PROMPT_MIXED

    fake = Mock()
    fake.models.generate_content = Mock(return_value=fake_response(text="नमस्ते"))
    config = Config(api_key="k", model="m", speech_language="ne")
    GeminiClient(config, client=fake, sleep=lambda s: None).transcribe(WAV)
    parts = fake.models.generate_content.call_args.kwargs["contents"][0].parts
    assert parts[0].text == TRANSCRIBE_PROMPT_MIXED


def test_english_mode_keeps_the_original_prompt():
    client, fake, _ = make_client(return_value=fake_response(text="hello"))
    client.transcribe(WAV)
    parts = fake.models.generate_content.call_args.kwargs["contents"][0].parts
    assert parts[0].text == TRANSCRIBE_PROMPT
