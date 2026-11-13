from unittest.mock import Mock

import httpx2
import pytest
from google.genai import errors

from nova.ai import AIError, GeminiClient, Message
from nova.config import Config

CONFIG = Config(api_key="test-key", model="test-model")
HISTORY = [Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "And?")]


def make_client(**generate_behavior):
    fake = Mock()
    fake.models.generate_content = Mock(**generate_behavior)
    return GeminiClient(CONFIG, client=fake), fake


def test_reply_returns_stripped_text():
    client, _ = make_client(return_value=Mock(text="  Answer  "))
    assert client.reply(HISTORY) == "Answer"


def test_reply_sends_model_and_mapped_roles():
    client, fake = make_client(return_value=Mock(text="ok"))
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
        (
            errors.ClientError(
                400, {"error": {"code": 400, "message": "bad key", "status": "INVALID_ARGUMENT"}}
            ),
            "rejected",
        ),
        (
            errors.ServerError(
                503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}}
            ),
            "Try again",
        ),
    ],
)
def test_failures_become_ai_error(error, expected):
    client, _ = make_client(side_effect=error)
    with pytest.raises(AIError, match=expected):
        client.reply(HISTORY)


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_response_raises(text):
    client, _ = make_client(return_value=Mock(text=text))
    with pytest.raises(AIError, match="empty"):
        client.reply(HISTORY)


def test_empty_history_is_a_programming_error():
    client, _ = make_client(return_value=Mock(text="ok"))
    with pytest.raises(ValueError):
        client.reply([])


def test_timeout_is_passed_in_milliseconds(monkeypatch):
    fake_class = Mock()
    monkeypatch.setattr("nova.ai.genai.Client", fake_class)
    GeminiClient(Config(api_key="k", model="m", request_timeout_seconds=2.5))
    assert fake_class.call_args.kwargs["http_options"].timeout == 2500
