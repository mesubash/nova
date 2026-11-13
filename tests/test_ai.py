from unittest.mock import Mock

import httpx2
import pytest
from google.genai import errors
from nova.ai import SYSTEM_INSTRUCTION

from nova.ai import MAX_ATTEMPTS, RETRY_DELAY_SECONDS, AIError, GeminiClient, Message
from nova.config import Config

CONFIG = Config(api_key="test-key", model="test-model")
HISTORY = [Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "And?")]


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
    client, _, _ = make_client(return_value=Mock(text="  Answer  "))
    assert client.reply(HISTORY) == "Answer"


def test_reply_sends_model_and_mapped_roles():
    client, fake, _ = make_client(return_value=Mock(text="ok"))
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
    client, fake, sleeps = make_client(side_effect=[server_error(), Mock(text="ok")])
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
    client, _, _ = make_client(return_value=Mock(text=text))
    with pytest.raises(AIError, match="empty"):
        client.reply(HISTORY)


def test_empty_history_is_a_programming_error():
    client, _, _ = make_client(return_value=Mock(text="ok"))
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
    client, fake, _ = make_client(return_value=Mock(text="ok"))
    client.reply(HISTORY)
    config = fake.models.generate_content.call_args.kwargs["config"]
    assert config.system_instruction == SYSTEM_INSTRUCTION
