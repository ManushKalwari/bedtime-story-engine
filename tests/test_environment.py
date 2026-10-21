import os

import pytest

from story_engine import config
from story_engine.llm import OpenAITransport


@pytest.fixture
def environment(tmp_path, monkeypatch):
    project = tmp_path / "source"
    project.mkdir()
    (project / "pyproject.toml").touch()
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.setattr(config, "__file__", str(project / "story_engine" / "config.py"))
    monkeypatch.chdir(working)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED")
    for name in ("STORY_INPUT_USD_PER_MILLION", "STORY_OUTPUT_USD_PER_MILLION"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    # Register key restoration even when load_dotenv writes directly to os.environ.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_API_KEY")
    return project, working


@pytest.mark.parametrize("location", [0, 1])
def test_loads_from_checkout_or_working_directory(environment, location):
    (environment[location] / ".env").write_text(
        '\ufeffOPENAI_API_KEY="local-test-key"\n', encoding="utf-8"
    )
    config.load_environment()
    assert os.environ["OPENAI_API_KEY"] == "local-test-key"


def test_working_directory_file_takes_precedence(environment):
    project, working = environment
    (project / ".env").write_text("OPENAI_API_KEY=source-key\n", encoding="utf-8")
    (working / ".env").write_text("OPENAI_API_KEY=working-key\n", encoding="utf-8")
    config.load_environment()
    assert os.environ["OPENAI_API_KEY"] == "working-key"


def test_shell_takes_precedence(environment, monkeypatch):
    (environment[1] / ".env").write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "shell-key")
    config.load_environment()
    assert os.environ["OPENAI_API_KEY"] == "shell-key"


def test_no_file_is_optional(environment):
    config.load_environment()
    assert "OPENAI_API_KEY" not in os.environ


def test_loading_can_be_disabled(environment, monkeypatch):
    (environment[1] / ".env").write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    config.load_environment()
    assert "OPENAI_API_KEY" not in os.environ


def test_settings_load_optional_prices(environment):
    (environment[1] / ".env").write_text(
        "STORY_INPUT_USD_PER_MILLION=1.5\nSTORY_OUTPUT_USD_PER_MILLION=2\n", encoding="utf-8"
    )
    settings = config.Settings.from_env()
    assert (settings.input_price, settings.output_price) == (1.5, 2)


def test_transport_loads_key_without_calling_api(environment):
    (environment[1] / ".env").write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")
    transport = OpenAITransport()
    try:
        assert transport.client.api_key == "file-key"
    finally:
        transport.client.close()
