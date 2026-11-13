import pytest

from nova import config as config_module
from nova.config import (
    DEFAULT_MAX_HISTORY_TURNS,
    DEFAULT_MAX_RECORDING_SECONDS,
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
    assert config.max_recording_seconds == DEFAULT_MAX_RECORDING_SECONDS


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


@pytest.mark.parametrize("raw", ["abc", "0", "-3", "nan"])
def test_invalid_recording_limit_raises(raw):
    with pytest.raises(ConfigError, match="NOVA_MAX_RECORDING_SECONDS"):
        load_config({**VALID_ENV, "NOVA_MAX_RECORDING_SECONDS": raw})


def test_actions_default_to_builtin_apps_and_no_search_folder():
    config = load_config(VALID_ENV)
    assert "Safari" in config.allowed_apps
    assert config.search_folder is None


def test_allowed_apps_are_parsed_from_a_comma_list():
    config = load_config({**VALID_ENV, "NOVA_ALLOWED_APPS": " Safari, Notes ,, "})
    assert config.allowed_apps == ("Safari", "Notes")


def test_search_folder_is_resolved(tmp_path):
    config = load_config({**VALID_ENV, "NOVA_SEARCH_FOLDER": str(tmp_path)})
    assert config.search_folder == tmp_path.resolve()


def test_missing_search_folder_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="NOVA_SEARCH_FOLDER"):
        load_config({**VALID_ENV, "NOVA_SEARCH_FOLDER": str(tmp_path / "missing")})


def test_data_dir_defaults_to_application_support():
    config = load_config(VALID_ENV)
    assert config.data_dir.parts[-3:] == ("Library", "Application Support", "NOVA")


def test_data_dir_can_be_overridden(tmp_path):
    config = load_config({**VALID_ENV, "NOVA_DATA_DIR": str(tmp_path / "nova-data")})
    assert config.data_dir == (tmp_path / "nova-data").resolve()


def test_data_dir_cannot_be_a_file(tmp_path):
    existing_file = tmp_path / "file.txt"
    existing_file.write_text("x")
    with pytest.raises(ConfigError, match="NOVA_DATA_DIR"):
        load_config({**VALID_ENV, "NOVA_DATA_DIR": str(existing_file)})


# Settings files


@pytest.fixture
def settings_files(monkeypatch, tmp_path):
    user_file = tmp_path / "support" / "config.env"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(config_module, "user_config_path", lambda: user_file)
    monkeypatch.chdir(project)
    return user_file, project


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_desktop_app_reads_user_config_file(settings_files):
    user_file, _ = settings_files
    write(user_file, "GEMINI_API_KEY=file-key\nGEMINI_MODEL=file-model\n")
    config = load_config(config_module._environment({}))
    assert (config.api_key, config.model) == ("file-key", "file-model")


def test_project_env_overrides_user_file(settings_files):
    user_file, project = settings_files
    write(user_file, "GEMINI_API_KEY=file-key\nGEMINI_MODEL=file-model\n")
    write(project / ".env", "GEMINI_MODEL=project-model\n")
    env = config_module._environment({})
    assert env["GEMINI_MODEL"] == "project-model"
    assert env["GEMINI_API_KEY"] == "file-key"


def test_process_environment_overrides_both_files(settings_files):
    user_file, project = settings_files
    write(user_file, "GEMINI_MODEL=file-model\n")
    write(project / ".env", "GEMINI_MODEL=project-model\n")
    env = config_module._environment({"GEMINI_MODEL": "shell-model"})
    assert env["GEMINI_MODEL"] == "shell-model"


def test_user_config_permissions_are_tightened(settings_files):
    user_file, _ = settings_files
    write(user_file, "GEMINI_API_KEY=secret\n")
    user_file.chmod(0o644)
    config_module._environment({})
    assert user_file.stat().st_mode & 0o777 == 0o600


def test_template_is_created_private_and_never_overwritten(tmp_path):
    path = tmp_path / "NOVA" / "config.env"
    assert config_module.ensure_user_config(path) == path
    assert path.stat().st_mode & 0o777 == 0o600
    assert "GEMINI_API_KEY=" in path.read_text()

    path.write_text("GEMINI_API_KEY=mine\n")
    config_module.ensure_user_config(path)
    assert path.read_text() == "GEMINI_API_KEY=mine\n"


def test_missing_key_message_names_both_settings_locations():
    with pytest.raises(ConfigError) as error:
        load_config({"GEMINI_MODEL": "m"})
    assert ".env" in str(error.value)
    assert "config.env" in str(error.value)
