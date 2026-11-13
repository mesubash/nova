import pytest

from nova.config import (
    DEFAULT_MAX_HISTORY_TURNS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ConfigError,
    load_config,
)

VALID_ENV = {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}


def test_minimal_config_uses_defaults():
    config = load_config(VALID_ENV)
    assert config.api_key == "test-key"
    assert config.model == "test-model"
    assert config.request_timeout_seconds == DEFAULT_REQUEST_TIMEOUT_SECONDS
    assert config.max_history_turns == DEFAULT_MAX_HISTORY_TURNS


def test_values_are_stripped():
    config = load_config({"GEMINI_API_KEY": "  key  ", "GEMINI_MODEL": " model\n"})
    assert config.api_key == "key"
    assert config.model == "model"


def test_optional_values_can_be_overridden():
    env = {**VALID_ENV, "NOVA_REQUEST_TIMEOUT": "12.5", "NOVA_MAX_HISTORY_TURNS": "4"}
    config = load_config(env)
    assert config.request_timeout_seconds == 12.5
    assert config.max_history_turns == 4


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GEMINI_MODEL"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_required_value_raises(name, value):
    env = dict(VALID_ENV)
    if value is None:
        del env[name]
    else:
        env[name] = value
    with pytest.raises(ConfigError, match=name):
        load_config(env)


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", "inf"])
def test_invalid_timeout_raises(raw):
    with pytest.raises(ConfigError, match="NOVA_REQUEST_TIMEOUT"):
        load_config({**VALID_ENV, "NOVA_REQUEST_TIMEOUT": raw})


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "2.5"])
def test_invalid_history_limit_raises(raw):
    with pytest.raises(ConfigError, match="NOVA_MAX_HISTORY_TURNS"):
        load_config({**VALID_ENV, "NOVA_MAX_HISTORY_TURNS": raw})


def test_repr_hides_api_key():
    config = load_config({**VALID_ENV, "GEMINI_API_KEY": "secret-value"})
    assert "secret-value" not in repr(config)