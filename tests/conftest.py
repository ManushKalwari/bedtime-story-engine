import pytest

from story_engine.config import Settings
from story_engine.demo import DemoTransport
from story_engine.llm import ModelClient
from story_engine.schemas import StoryRequest
from story_engine.telemetry import Recorder


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for name in (
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "socket.create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Tests must not make network calls")),
    )


@pytest.fixture
def request_data():
    return StoryRequest(prompt="A story about Alice and Bob, her best friend, a cat.", age=7)


@pytest.fixture
def client():
    return ModelClient(DemoTransport(), Recorder(Settings(parallel_reviews=False)))
