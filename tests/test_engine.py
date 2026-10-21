import pytest

from story_engine import agents
from story_engine.config import Settings
from story_engine.demo import DemoTransport
from story_engine.engine import StoryEngine, retain_candidate
from story_engine.llm import ModelClient
from story_engine.metrics import measure
from story_engine.schemas import Story
from story_engine.telemetry import EngineError, Recorder


def assessment(client, request_data):
    story = Story.model_validate(client.transport.fixture["story"])
    brief = agents.intake(client, request_data, [])
    return agents.review(client, story, brief, request_data, [])


def test_end_to_end_revision(client, request_data):
    result = StoryEngine(client).run(request_data)
    assert result.status == "accepted"
    assert result.selected_version == 1
    assert len(result.drafts) == 2
    assert result.drafts[0].story.paragraphs[:4] == result.selected().story.paragraphs[:4]
    assert client.recorder.attempts == 8


def test_initial_pass_skips_editor(client, request_data):
    client.transport.quality_count = 1
    result = StoryEngine(client).run(request_data)
    assert result.status == "accepted"
    assert result.selected_version == 0
    assert not any(e.get("stage") == "editor" for e in client.recorder.events)


def test_regression_is_not_emitted(request_data):
    client = ModelClient(DemoTransport("rollback"), Recorder(Settings(parallel_reviews=False)))
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed"  # Incumbent also fails the calm gate.
    assert result.selected() is None
    assert not result.drafts[-1].retained
    assert "regressed" in result.drafts[-1].decision


def test_no_safe_draft_fails_closed(request_data):
    client = ModelClient(DemoTransport("fail"), Recorder(Settings(parallel_reviews=False)))
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed" and result.selected() is None
    assert len(result.drafts) <= 3


def test_zero_revision_budget(client, request_data):
    client = ModelClient(DemoTransport(), Recorder(Settings(max_revisions=0)))
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed"
    assert result.stop_reason == "revision_limit"
    assert len(result.drafts) == 1


def test_declined_request_never_reaches_writer(client, request_data):
    client.transport.fixture["brief"].update(
        decision="decline", parent_note="Please choose a gentler premise."
    )
    result = StoryEngine(client).run(request_data)
    assert result.status == "declined" and not result.drafts
    assert client.recorder.attempts == 1


def test_reframe_is_disclosed(client, request_data):
    client.transport.fixture["brief"].update(
        decision="reframe", parent_note="The creature will be friendly."
    )
    result = StoryEngine(client).run(request_data)
    assert result.brief.parent_note == "The creature will be friendly."


def test_safety_cannot_be_outvoted_by_quality(client, request_data):
    old = assessment(client, request_data)
    new = old.model_copy(deep=True)
    new.safety = type(new.safety).model_validate(
        {**new.safety.model_dump(), "safe": False, "concerns": ["A safety problem."]}
    )
    for field in new.scores():
        getattr(new.quality, field).score = 5
    assert not retain_candidate(old, new)[0]


def test_component_regression_blocks_higher_average(client, request_data):
    old = assessment(client, request_data)
    new = old.model_copy(deep=True)
    new.quality.warmth.score = 5
    new.quality.bedtime_calm.score = 5
    new.quality.fidelity.score = 3
    assert new.average() > old.average()
    assert not retain_candidate(old, new)[0]


def test_noop_quality_does_not_extend_loop(client, request_data):
    old = assessment(client, request_data)
    assert not retain_candidate(old, old)[0]


@pytest.mark.parametrize(
    "old_count,new_count,keep",
    [
        (173, 220, True),
        (255, 246, False),
        (500, 480, True),
        (300, 299, False),
        (220, 220, False),
        (173, 530, True),
        (173, 600, False),
    ],
)
def test_length_progress_uses_distance_from_range(client, request_data, old_count, new_count, keep):
    old = assessment(client, request_data)
    new = old.model_copy(deep=True)
    old.metrics.word_count, new.metrics.word_count = old_count, new_count
    old.metrics.failures = [] if 300 <= old_count <= 450 else ["Outside word range"]
    new.metrics.failures = [] if 300 <= new_count <= 450 else ["Outside word range"]
    assert retain_candidate(old, new, word_range=(300, 450))[0] is keep


def test_length_progress_does_not_override_rubric_regression(client, request_data):
    old = assessment(client, request_data)
    new = old.model_copy(deep=True)
    old.metrics.word_count, new.metrics.word_count = 173, 220
    old.metrics.failures = new.metrics.failures = ["Outside word range"]
    new.quality.fidelity.score = old.quality.fidelity.score - 1
    assert not retain_candidate(old, new, word_range=(300, 450))[0]


@pytest.mark.parametrize("revisions,expected_status", [(1, "failed"), (2, "accepted")])
def test_partial_length_repair_continues_without_accepting_short_story(
    client, request_data, monkeypatch, revisions, expected_status
):
    base = assessment(client, request_data)
    for dimension in base.scores():
        getattr(base.quality, dimension).score = 5

    def story_with_words(count):
        return Story(title="Length repair", paragraphs=["word " * count])

    def review(_client, story, *_args):
        result = base.model_copy(deep=True)
        result.metrics = measure(story, (300, 450))
        return result

    candidates = iter([story_with_words(220), story_with_words(320)])
    monkeypatch.setattr(agents, "write", lambda *a: story_with_words(173))
    monkeypatch.setattr(agents, "review", review)
    monkeypatch.setattr(agents, "edit", lambda *a: next(candidates))
    client.settings = Settings(max_revisions=revisions, parallel_reviews=False)
    result = StoryEngine(client).run(request_data)
    assert result.status == expected_status
    assert result.drafts[1].retained
    assert "closer" in result.drafts[1].decision
    if revisions == 1:
        assert result.selected() is None
        assert result.stop_reason == "revision_limit"
    else:
        assert result.selected().assessment.metrics.word_count == 320
        assert result.stop_reason == "quality_gates_met"


def test_missing_judge_never_approves(client, request_data, monkeypatch):
    monkeypatch.setattr(
        agents, "review", lambda *a: (_ for _ in ()).throw(EngineError("Judge unavailable"))
    )
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed" and result.selected() is None


def test_new_feedback_rechecks_prior_story(client, request_data):
    previous = StoryEngine(client).run(request_data)
    new_transport = DemoTransport()
    next_client = ModelClient(
        new_transport, Recorder(Settings(parallel_reviews=False), content=True)
    )
    result = StoryEngine(next_client).run(
        request_data, previous=previous, change="Make the ending gentler."
    )
    assert result.feedback == ["Make the ending gentler."]
    assert result.drafts[0].story == previous.selected().story
    stages = [e["stage"] for e in next_client.recorder.events if e["type"] == "call"]
    assert stages[:3] == ["intake", "safety", "quality"]
    assert "writer" not in stages
    assert result.selected() is None  # New bad initial rating cannot inherit old approval.


def test_eligible_previous_survives_failed_edit(client, request_data, monkeypatch):
    previous = StoryEngine(client).run(request_data)
    next_transport = DemoTransport()
    next_transport.quality_count = 1
    next_client = ModelClient(next_transport, Recorder(Settings(parallel_reviews=False)))
    monkeypatch.setattr(
        agents, "edit", lambda *a: (_ for _ in ()).throw(EngineError("Edit failed"))
    )
    result = StoryEngine(next_client).run(request_data, previous=previous, change="Make it warmer.")
    assert result.status == "accepted" and result.selected_version == 0
    assert result.warnings


def test_bounded_feedback(client, request_data):
    previous = StoryEngine(client).run(request_data)
    previous.feedback = ["Change"] * 6
    with pytest.raises(ValueError):
        StoryEngine(client).run(request_data, previous=previous, change="More")


def test_call_budget_is_safe_under_parallel_reviews(request_data):
    client = ModelClient(DemoTransport(), Recorder(Settings(max_calls=4)))
    result = StoryEngine(client).run(request_data)
    assert result.status == "failed"
    assert client.recorder.attempts <= 4
