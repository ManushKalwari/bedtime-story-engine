import json

import httpx
import pytest
from openai import OpenAI

from story_engine.config import MODEL, Settings
from story_engine.llm import ModelClient, OpenAITransport
from story_engine.telemetry import EngineError, Recorder


def transport(monkeypatch, handler):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    instance = OpenAITransport()
    instance.client.close()
    instance.client = OpenAI(
        api_key="offline-test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return instance


def response():
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": '{"ok":true}'},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_real_sdk_request_contract(monkeypatch):
    captured = []

    def handler(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200, json=response())

    t = transport(monkeypatch, handler)
    client = ModelClient(t, Recorder(Settings(input_price=1, output_price=2)))
    client.call("judge", [{"role": "user", "content": "Return JSON"}])
    assert captured[0]["model"] == "gpt-3.5-turbo"
    assert captured[0]["response_format"] == {"type": "json_object"}
    assert client.recorder.summary()["estimated_usd_for_recorded_usage"] == 0.00002
    assert "offline-test-key" not in json.dumps(client.recorder.events)


def test_429_retry_counted_once_per_attempt(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={"error": {"message": "slow", "type": "rate_limit_error"}},
            )
        return httpx.Response(200, json=response())

    client = ModelClient(transport(monkeypatch, handler), Recorder(Settings()))
    client.call("judge", [{"role": "user", "content": "JSON"}])
    assert client.recorder.attempts == 2
    assert not client.recorder.summary()["usage_complete"]


@pytest.mark.parametrize("status", [401, 403, 404, 400])
def test_permanent_errors_not_retried(monkeypatch, status):
    client = ModelClient(
        transport(
            monkeypatch, lambda req: httpx.Response(status, json={"error": {"message": "failed"}})
        ),
        Recorder(Settings()),
    )
    with pytest.raises(EngineError):
        client.call("judge", [{"role": "user", "content": "JSON"}])
    assert client.recorder.attempts == 1


def test_missing_key_is_clear():
    with pytest.raises(EngineError, match="OPENAI_API_KEY"):
        OpenAITransport()
