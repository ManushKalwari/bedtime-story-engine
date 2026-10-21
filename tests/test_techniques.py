import json
from dataclasses import FrozenInstanceError

import pytest

from evals.common import generate_variant
from story_engine import agents
from story_engine.config import Settings
from story_engine.demo import DemoTransport
from story_engine.engine import StoryEngine
from story_engine.llm import ModelClient
from story_engine.schemas import Blueprint, Brief, Story
from story_engine.techniques import TECHNIQUES, select_techniques
from story_engine.telemetry import Recorder

PAIRS = {
    "friendship": ("distinctive_character_behavior", "emotional_return"),
    "wonder": ("discovery_through_action", "setup_and_payoff"),
    "comfort": ("emotional_return", "repetition_with_variation"),
    "whimsy": ("three_gentle_attempts", "distinctive_character_behavior"),
    "sensory": ("repetition_with_variation", "emotional_return"),
}


@pytest.mark.parametrize("category", PAIRS)
@pytest.mark.parametrize("age", [5, 7, 8, 10])
@pytest.mark.parametrize("length", ["short", "standard"])
def test_selection_is_bounded_age_specific_and_json_ready(category, age, length):
    guidance = select_techniques(category, age, length)
    assert guidance == select_techniques(category, age, length)
    assert json.loads(json.dumps(guidance)) == guidance
    expected = PAIRS[category][:1] if length == "short" else PAIRS[category]
    assert tuple(item["id"] for item in guidance) == expected
    for item in guidance:
        technique = TECHNIQUES[item["id"]]
        assert item["age_guidance"] == (technique.younger if age <= 7 else technique.older)
        assert all(item.values())
        if length == "short":
            assert item["short_guidance"] == technique.short
        else:
            assert "short_guidance" not in item


def test_catalog_is_immutable_and_returned_guidance_is_independent():
    technique = TECHNIQUES["emotional_return"]
    with pytest.raises(FrozenInstanceError):
        technique.example = "Changed"
    with pytest.raises(TypeError):
        TECHNIQUES["emotional_return"] = technique
    guidance = select_techniques("comfort", 7, "standard")
    guidance[0]["example"] = "Changed"
    assert select_techniques("comfort", 7, "standard")[0]["example"] == technique.example


class CapturingTransport(DemoTransport):
    def __init__(self):
        super().__init__()
        self.requests = []

    def complete(self, messages, *, stage, **kwargs):
        self.requests.append((stage, json.loads(messages[1]["content"])))
        return super().complete(messages, stage=stage, **kwargs)


def capture_client(**settings):
    transport = CapturingTransport()
    return ModelClient(transport, Recorder(Settings(parallel_reviews=False, **settings)))


@pytest.mark.parametrize("enabled", [True, False])
def test_writer_serializes_guidance_without_extra_calls(enabled):
    client = capture_client()
    brief = Brief.model_validate(client.transport.fixture["brief"])
    blueprint = Blueprint.model_validate(client.transport.fixture["blueprint"])
    story = agents.write(client, brief, blueprint, use_techniques=enabled)
    assert isinstance(story, Story)
    assert story.model_dump() == client.transport.fixture["story"]
    assert client.recorder.attempts == 1
    [(stage, payload)] = client.transport.requests
    assert stage == "writer"
    assert payload["brief"] == brief.model_dump()
    assert payload["blueprint"] == blueprint.model_dump()
    if enabled:
        assert payload["storytelling_techniques"] == select_techniques(
            brief.category, brief.age, brief.length
        )
    else:
        assert "storytelling_techniques" not in payload


def test_engine_enables_library_by_default_without_changing_call_count(request_data):
    client = capture_client()
    result = StoryEngine(client).run(request_data)
    assert result.status == "accepted"
    assert result.selected_version == 1
    assert client.recorder.attempts == 8
    [payload] = [p for stage, p in client.transport.requests if stage == "writer"]
    assert payload["storytelling_techniques"] == select_techniques("friendship", 7, "standard")
    assert all(
        "storytelling_techniques" not in payload
        for stage, payload in client.transport.requests
        if stage not in ("planner", "writer")
    )
    [planner_payload] = [p for stage, p in client.transport.requests if stage == "planner"]
    assert planner_payload["storytelling_techniques"] == payload["storytelling_techniques"]


@pytest.mark.parametrize("variant", ["planned", "naive_rewrite"])
def test_experiment_controls_omit_library(variant, request_data):
    client = capture_client(max_revisions=0)
    story, emitted, _ = generate_variant(client, request_data, variant)
    assert emitted and isinstance(story, Story)
    [payload] = [p for stage, p in client.transport.requests if stage == "writer"]
    assert "storytelling_techniques" not in payload
    [planner_payload] = [p for stage, p in client.transport.requests if stage == "planner"]
    assert "storytelling_techniques" not in planner_payload
    assert client.recorder.attempts == 3
