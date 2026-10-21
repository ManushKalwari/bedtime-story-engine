import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from evals.common import load_data, reference_brief
from evals.judge_calibration import main as calibration_main
from story_engine import agents
from story_engine.config import DIMENSIONS, Settings
from story_engine.demo import DemoTransport
from story_engine.engine import StoryEngine, retain_candidate
from story_engine.llm import ModelClient
from story_engine.review_validation import verify_evidence
from story_engine.schemas import (
    Blueprint,
    GroundedQualityReview,
    HolisticVerdict,
    PlannedBlueprint,
    RunResult,
    Story,
)
from story_engine.telemetry import EngineError, Recorder


class CraftTransport(DemoTransport):
    def __init__(self, change=None):
        super().__init__()
        self.change = change
        self.requests = []

    def complete(self, messages, *, stage, **kwargs):
        self.requests.append((stage, json.loads(messages[1]["content"])))
        response = super().complete(messages, stage=stage, **kwargs)
        if self.change:
            value = json.loads(response.content)
            self.change(stage.split(".")[0], value)
            response.content = json.dumps(value)
        return response


def make_client(change=None):
    return ModelClient(CraftTransport(change), Recorder(Settings(parallel_reviews=False)))


def test_judge_example_matches_live_schema_and_quotes_its_own_story():
    text = agents.prompt("quality")
    source = text.split("Example input:", 1)[1].split("Example output", 1)[0]
    paragraphs = [
        line.split(": ", 1)[1]
        for line in source.splitlines()
        if line.startswith("Story paragraph ")
    ]
    example = text.split("Example output", 1)[1]
    value, _ = json.JSONDecoder().raw_decode(example[example.index("{") :])
    review = GroundedQualityReview.model_validate(value)
    story = Story(title="Calibration example", paragraphs=paragraphs)
    evidence = [getattr(review, dimension).evidence for dimension in DIMENSIONS]
    evidence.extend([review.craft.resolution, review.craft.specificity])
    verify_evidence(evidence, story)


def test_new_plans_require_craft_but_legacy_blueprints_still_load(client):
    legacy = dict(client.transport.fixture["blueprint"])
    legacy.pop("craft")
    assert Blueprint.model_validate(legacy).craft is None
    with pytest.raises(ValidationError):
        PlannedBlueprint.model_validate(legacy)


@pytest.mark.parametrize("field", ["character_desire", "distinctive_behavior", "setup", "payoff"])
def test_planner_repairs_missing_craft_fields_within_existing_budget(field):
    def change(stage, value):
        if stage == "planner":
            value["craft"].pop(field)

    client = make_client(change)
    brief = reference_brief(load_data("requests.json")[0])
    with pytest.raises(EngineError, match="bounded repair"):
        agents.plan(client, brief)
    assert client.recorder.attempts == 2


def test_planner_craft_and_techniques_reach_writer(request_data):
    client = make_client()
    result = StoryEngine(client).run(request_data)
    assert result.blueprint.craft.character_desire
    assert result.blueprint.craft.distinctive_behavior
    assert result.blueprint.craft.setup
    assert result.blueprint.craft.payoff
    [writer] = [p for stage, p in client.transport.requests if stage == "writer"]
    assert writer["blueprint"]["craft"] == result.blueprint.craft.model_dump()
    assert client.recorder.attempts == 8


@pytest.mark.parametrize(
    "count, addition, removal", [(255, 45, 0), (246, 54, 0), (500, 0, 50), (350, 0, 0)]
)
def test_editor_receives_length_repair_even_with_perfect_scores(
    request_data, count, addition, removal
):
    client = make_client()
    result = StoryEngine(client).run(request_data)
    draft = result.selected().model_copy(deep=True)
    draft.story = Story(title="Test", paragraphs=["word " * (count // 5)] * 5)
    # Complete the requested count without relying on the assessment's stale count.
    draft.story.paragraphs[-1] += " word" * (count % 5)
    draft.assessment.quality.craft.setup_payoff = None
    for dimension in draft.assessment.scores():
        getattr(draft.assessment.quality, dimension).score = 5
    draft.assessment.quality.fixes = []
    client.transport.requests.clear()
    before = client.recorder.attempts
    agents.edit(client, draft, result.brief, [])
    [(stage, payload)] = client.transport.requests
    task = payload["length_task"]
    assert stage == "editor"
    assert task["current_body_words"] == count
    assert task["minimum_words_to_add"] == addition
    assert task["minimum_words_to_remove"] == removal
    assert task["target_body_words"] == 375
    if addition:
        assert f"at least {addition} words" in task["instruction"]
    if removal:
        assert f"at least {removal} words" in task["instruction"]
    assert client.recorder.attempts == before + 1


@pytest.mark.parametrize(
    "age, length, target",
    [(5, "short", 170), (5, "standard", 375), (10, "short", 275), (10, "standard", 625)],
)
def test_writer_receives_length_target_without_extra_calls(age, length, target):
    client = make_client()
    brief = reference_brief(load_data("requests.json")[0])
    brief.age, brief.length = age, length
    agents.write(client, brief)
    [(stage, payload)] = client.transport.requests
    assert stage == "writer"
    assert payload["length_task"]["target_body_words"] == target
    assert "current_body_words" not in payload["length_task"]
    assert client.recorder.attempts == 1


@pytest.mark.parametrize("target", ["resolution", "specificity", "setup", "payoff"])
def test_craft_quotes_must_be_grounded(target, request_data):
    def change(stage, value):
        if stage == "quality":
            evidence = (
                value["craft"][target]
                if target in ("resolution", "specificity")
                else value["craft"]["setup_payoff"][target]
            )
            evidence["quote"] = "A fabricated detail that does not occur."

    client = make_client(change)
    brief = reference_brief(load_data("requests.json")[0])
    story = Story.model_validate(client.transport.fixture["story"])
    with pytest.raises(EngineError, match="bounded repair"):
        agents.review(client, story, brief, request_data, [])
    assert client.recorder.attempts == 3  # One safety call and two quality attempts.


def test_live_quality_requires_craft_evidence(request_data):
    def change(stage, value):
        if stage == "quality":
            value.pop("craft")

    client = make_client(change)
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed"
    assert result.selected() is None
    assert "bounded repair" in result.stop_reason


def test_missing_connection_is_valid_and_never_invented(request_data):
    def change(stage, value):
        if stage == "quality":
            value["craft"]["setup_payoff"] = None

    client = make_client(change)
    result = StoryEngine(client).run(request_data)
    [editor] = [p for stage, p in client.transport.requests if stage == "editor"]
    assert result.status == "accepted"
    assert editor["protected_connection"] is None


def test_editor_receives_grounded_pair_and_can_update_both_ends(request_data):
    def change(stage, value):
        if stage == "editor":
            value["edits"] = [
                {"paragraph": 1, "replacement": first.replace("sunflower", "rosebush")},
                {"paragraph": 4, "replacement": fourth.replace("sunflower", "rosebush")},
            ]

    client = make_client()
    result = StoryEngine(client).run(request_data)
    initial = result.drafts[0]
    first, fourth = initial.story.paragraphs[0], initial.story.paragraphs[3]
    client.transport.change = change
    client.transport.requests.clear()
    edited = agents.edit(client, initial, result.brief, ["Use a rosebush instead."])
    [(stage, payload)] = client.transport.requests
    assert stage == "editor"
    connection = payload["protected_connection"]
    assert connection == initial.assessment.quality.craft.setup_payoff.model_dump()
    for end in ("setup", "payoff"):
        evidence = connection[end]
        assert evidence["quote"] in initial.story.paragraphs[evidence["paragraph"] - 1]
    assert "rosebush" in edited.paragraphs[0]
    assert "rosebush" in edited.paragraphs[3]
    assert edited.paragraphs[1:3] == initial.story.paragraphs[1:3]
    assert edited.paragraphs[4] == initial.story.paragraphs[4]


def test_broken_payoff_cannot_be_retained_for_better_cadence(client, request_data):
    result = StoryEngine(client).run(request_data)
    original = result.selected().assessment
    broken = original.model_copy(deep=True)
    broken.quality.coherence.score = 2
    broken.quality.cadence.score = 5
    broken.quality.craft.setup_payoff = None
    keep, reason = retain_candidate(original, broken)
    assert not keep
    assert "regressed" in reason


def test_editor_rejects_tampered_protected_evidence_before_calling_model(client, request_data):
    result = StoryEngine(client).run(request_data)
    draft = result.selected()
    draft.assessment.quality.craft.setup_payoff.setup.quote = "This detail is not in the story."
    attempts = client.recorder.attempts
    with pytest.raises(EngineError, match="not grounded"):
        agents.edit(client, draft, result.brief, [])
    assert client.recorder.attempts == attempts


@pytest.mark.parametrize("within_paragraph", [False, True])
def test_reversed_setup_payoff_is_rejected(request_data, within_paragraph):
    def change(stage, value):
        if stage == "quality":
            pair = value["craft"]["setup_payoff"]
            if within_paragraph:
                pair["payoff"]["paragraph"] = 1
                pair["payoff"]["quote"] = "Alice kept a small blue cushion beside her window."
            else:
                pair["setup"], pair["payoff"] = pair["payoff"], pair["setup"]

    client = make_client(change)
    brief = reference_brief(load_data("requests.json")[0])
    story = Story.model_validate(client.transport.fixture["story"])
    with pytest.raises(EngineError, match="bounded repair"):
        agents.review(client, story, brief, request_data, [])


def test_historical_run_roundtrip_still_loads():
    path = Path(__file__).parents[1] / "examples/synthetic-improvement/run.json"
    old = RunResult.model_validate_json(path.read_text(encoding="utf-8"))
    assert old.blueprint.craft is None
    assert old.selected().assessment.quality.craft is None
    assert (
        RunResult.model_validate_json(old.model_dump_json()).selected().story
        == old.selected().story
    )


def test_calibration_includes_matched_constraint_control_and_sensory_control():
    cases = {case["id"]: case for case in load_data("calibration.json")}
    for case in cases.values():
        Story.model_validate(case["story"])
        reference_brief(case)
    assert not cases["pleasant-but-empty"]["expected_accept"]
    assert cases["moonlit-is-not-on-moon"]["target_dimensions"] == ["fidelity"]
    assert cases["broken-setup-after-edit"]["target_dimensions"] == ["coherence"]
    assert not cases["subtle-negative-constraint"]["expected_accept"]
    assert cases["earned-payoff-control"]["expected_accept"]
    assert cases["quiet-sensory-control"]["expected_accept"]
    assert cases["building-replaced-by-friendship"]["target_dimensions"] == ["fidelity"]
    assert cases["ornate-language-for-five"]["target_dimensions"] == ["age_fit"]
    bad = cases["subtle-negative-constraint"]["story"]["paragraphs"]
    good = cases["earned-payoff-control"]["story"]["paragraphs"]
    assert bad[0] == good[0] and bad[2] == good[2]
    assert bad[1] != good[1]


def test_calibration_dry_run_never_constructs_api_client(monkeypatch, capsys):
    monkeypatch.setattr(
        "evals.judge_calibration.make_client",
        lambda: pytest.fail("Dry run must not create an API client"),
    )
    assert calibration_main([]) == 0
    assert f"{len(load_data('calibration.json'))} seeded cases" in capsys.readouterr().out


def test_calibration_reports_targeted_defects_and_keeps_errors_in_denominator(
    client, request_data, monkeypatch, tmp_path
):
    accepted = StoryEngine(client).run(request_data).selected().assessment
    violation = accepted.model_copy(deep=True)
    violation.quality.fidelity.score = 3
    results = iter([EngineError("Unavailable judge"), violation, accepted])

    def review(*args):
        value = next(results)
        if isinstance(value, Exception):
            raise value
        return value

    cases = {case["id"]: case for case in load_data("calibration.json")}
    monkeypatch.setattr(
        "evals.judge_calibration.load_data",
        lambda _: [
            cases[name]
            for name in ("pleasant-but-empty", "moonlit-is-not-on-moon", "quiet-sensory-control")
        ],
    )
    monkeypatch.setattr("evals.judge_calibration.agents.review", review)
    monkeypatch.setattr(
        "evals.judge_calibration.make_client",
        lambda: SimpleNamespace(
            recorder=SimpleNamespace(summary=lambda: {}, save=lambda path: None),
            structured=lambda *a: HolisticVerdict(score=9, feedback="Scripted control."),
        ),
    )
    assert calibration_main(["--execute", "--output", str(tmp_path)]) == 0
    [report] = tmp_path.glob("*/report.md")
    text = report.read_text(encoding="utf-8")
    assert "| coherence | 0.0% (0/1) | 1 |" in text
    assert "| fidelity | 100.0% (1/1) | 0 |" in text
    assert "| structured | 66.7% (2/3) | 2/3 |" in text
