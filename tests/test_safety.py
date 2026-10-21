import hashlib
import json

import pytest

from story_engine import agents
from story_engine.config import Settings
from story_engine.demo import DemoTransport
from story_engine.engine import StoryEngine
from story_engine.llm import Completion, ModelClient
from story_engine.schemas import Brief, SafetyReview, Story
from story_engine.telemetry import EngineError, Recorder

SAFE = {"safe": True, "reason": "No threatening content or dangerous behavior is present."}
UNSAFE = {
    "safe": False,
    "reason": "The child swallows unknown pills; replace this with asking a trusted adult for help.",
}


class SafetyResponses(DemoTransport):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)
        self.safety_requests = []

    def complete(self, messages, *, stage, **kwargs):
        if stage.startswith("safety"):
            self.safety_requests.append([dict(message) for message in messages])
            return Completion(json.dumps(next(self.responses)), usage_known=False)
        return super().complete(messages, stage=stage, **kwargs)


def make_client(responses, *, trace=False):
    return ModelClient(
        SafetyResponses(responses),
        Recorder(Settings(parallel_reviews=False), content=trace),
    )


def review(client, request):
    brief = Brief.model_validate(client.transport.fixture["brief"])
    story = Story.model_validate(client.transport.fixture["story"])
    return agents.review(client, story, brief, request, [])


def test_safe_review_needs_only_verdict_and_concise_reason(request_data):
    client = make_client([SAFE])
    assessed = review(client, request_data)
    assert assessed.safety.safe
    assert assessed.safety.reason == SAFE["reason"]
    assert assessed.safety.evidence == []
    assert assessed.safety.concerns == [] and assessed.safety.fixes == []
    assert client.recorder.attempts == 2  # One safety call and one quality call.
    [(system, user)] = client.transport.safety_requests
    schema = json.loads(system["content"].split("matching this schema:\n")[1])
    assert set(schema["properties"]) == {"safe", "reason"}
    assert set(schema["required"]) == {"safe", "reason"}
    assert json.loads(user["content"])["story"] == client.transport.fixture["story"]


def test_unsafe_reason_is_passed_to_editor_and_never_accepted(request_data):
    client = make_client([UNSAFE, UNSAFE, UNSAFE], trace=True)
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed"
    assert result.selected() is None
    assert not result.drafts[0].assessment.safety.safe
    assert result.drafts[0].assessment.safety.concerns == [UNSAFE["reason"]]
    # The editor receives the assessed reason, including the requested correction.
    assessment = result.drafts[0].assessment
    assert assessment.safety.reason == UNSAFE["reason"]
    assert not assessment.eligible()
    editor = next(e for e in client.recorder.events if e.get("stage") == "editor")
    payload = json.loads(editor["messages"][1]["content"])
    assert payload["assessment"]["safety"]["reason"] == UNSAFE["reason"]


def test_missing_reason_can_be_repaired_without_quote_requirements(request_data):
    client = make_client([{"safe": True}, SAFE])
    assessed = review(client, request_data)
    assert assessed.safety.reason == SAFE["reason"]
    assert client.recorder.attempts == 3
    repair = client.transport.safety_requests[1][-1]["content"]
    assert "exactly safe" in repair
    assert "Do not include quotes, evidence, concerns, or fixes fields" in repair


@pytest.mark.parametrize(
    "invalid,field,code",
    [
        ({"safe": "true", "reason": "No concerns found."}, "safe", "bool_type"),
        ({"reason": "No concerns found."}, "safe", "missing"),
        ({"safe": True}, "reason", "missing"),
        ({"safe": True, "reason": "   "}, "reason", "string_too_short"),
        ({"safe": True, "reason": "x" * 401}, "reason", "string_too_long"),
        ({**SAFE, "evidence": []}, "evidence", "extra_forbidden"),
    ],
)
def test_invalid_safety_response_fails_closed_with_field_diagnostics(
    request_data, invalid, field, code
):
    client = make_client([invalid, invalid])
    with pytest.raises(EngineError, match=rf"bounded repair: {field} \({code}\)"):
        review(client, request_data)
    assert client.recorder.attempts == 2
    errors = [event for event in client.recorder.events if event["type"] == "validation_error"]
    assert len(errors) == 2
    assert all(event["issues"] == [{"path": [field], "type": code}] for event in errors)
    assert "Alice" not in json.dumps(client.recorder.events)


def test_trace_keeps_original_request_separate_from_repair(request_data):
    client = make_client([{"safe": True}, SAFE], trace=True)
    review(client, request_data)
    calls = [event for event in client.recorder.events if event["type"] == "call"]
    first, repaired = [event for event in calls if event["stage"].startswith("safety")]
    assert len(first["messages"]) == 2
    assert len(repaired["messages"]) == 4
    for event in calls:
        digest = hashlib.sha256(json.dumps(event["messages"], sort_keys=True).encode()).hexdigest()
        assert digest == event["request_hash"]


def test_historical_safety_evidence_is_preserved_without_requiring_new_reason():
    historical = SafetyReview(
        safe=True,
        evidence=[
            {"paragraph": 1, "quote": "Alice rested beside Bob.", "observation": "Legacy quote."}
        ],
        concerns=[],
        fixes=[],
    )
    assert historical.reason is None
    assert (
        SafetyReview.model_validate_json(historical.model_dump_json()).evidence
        == historical.evidence
    )


def test_concise_reason_is_escaped_in_inspector(client, request_data, tmp_path):
    from story_engine.reporting import write_inspector

    result = StoryEngine(client).run(request_data)
    result.selected().assessment.safety.reason = "<script>example</script>"
    path = tmp_path / "inspect.html"
    write_inspector(result, path)
    page = path.read_text(encoding="utf-8")
    assert "&lt;script&gt;example&lt;/script&gt;" in page
    assert "<script>example</script>" not in page
