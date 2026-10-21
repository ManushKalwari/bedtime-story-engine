from copy import deepcopy

import pytest
from pydantic import ValidationError

from story_engine.config import DIMENSIONS
from story_engine.engine import StoryEngine
from story_engine.review_validation import validate_quality, verify_evidence
from story_engine.schemas import Evidence, GroundedQualityReview, Story
from story_engine.telemetry import ResponseValidationError


@pytest.fixture
def reviewed(client, request_data):
    return StoryEngine(client).run(request_data).selected()


def test_nested_scores_keep_original_values_and_raw_response(reviewed):
    raw = reviewed.assessment.quality.model_dump()
    for dimension in DIMENSIONS:
        raw[dimension]["evidence"]["score"] = raw[dimension].pop("score")
    raw["craft"]["resolution"]["score"] = 1
    raw["craft"]["specificity"]["score"] = 5
    original = deepcopy(raw)
    parsed = GroundedQualityReview.model_validate(raw)
    assert raw == original
    assert {
        name: getattr(parsed, name).score for name in DIMENSIONS
    } == reviewed.assessment.scores()
    assert "score" not in parsed.craft.resolution.model_dump()


@pytest.mark.parametrize("nested", [3, "4", True])
def test_conflicting_or_differently_typed_scores_require_correction(reviewed, nested):
    raw = reviewed.assessment.quality.model_dump()
    raw["age_fit"]["score"] = 4
    raw["age_fit"]["evidence"]["score"] = nested
    with pytest.raises(ValidationError, match="conflicting scores"):
        GroundedQualityReview.model_validate(raw)


def test_missing_ratings_cannot_be_replaced_with_defaults(reviewed):
    raw = reviewed.assessment.quality.model_dump()
    raw["age_fit"].pop("score")
    with pytest.raises(ValidationError):
        GroundedQualityReview.model_validate(raw)


def test_optional_collections_have_independent_empty_defaults(reviewed):
    raw = reviewed.assessment.quality.model_dump()
    for field in ("preserve", "fixes", "arousal_by_paragraph"):
        raw.pop(field)
    raw["craft"].pop("setup_payoff")
    first = GroundedQualityReview.model_validate(raw)
    second = GroundedQualityReview.model_validate(raw)
    assert not first.preserve and not first.fixes and not first.arousal_by_paragraph
    assert first.craft.setup_payoff is None
    first.preserve.append("Keep the cushion.")
    assert second.preserve == []


def test_quality_repair_reports_all_invalid_quote_paths(reviewed, client):
    quality = GroundedQualityReview.model_validate(reviewed.assessment.quality.model_dump())
    quality.age_fit.evidence.quote = "This first fabricated quote is not in the story."
    quality.warmth.evidence.quote = "This second fabricated quote is not in the story."
    with pytest.raises(ResponseValidationError) as caught:
        validate_quality(quality, reviewed.story, reviewed.assessment.metrics, client.recorder)
    paths = {tuple(issue["path"]) for issue in caught.value.issues}
    assert paths == {("age_fit", "evidence", "quote"), ("warmth", "evidence", "quote")}


def test_misaligned_chart_does_not_change_scores_or_invent_ratings(reviewed, client):
    quality = GroundedQualityReview.model_validate(reviewed.assessment.quality.model_dump())
    quality.arousal_by_paragraph = [3] * (len(reviewed.story.paragraphs) + 1)
    scores = {name: getattr(quality, name).score for name in DIMENSIONS}
    validate_quality(quality, reviewed.story, reviewed.assessment.metrics, client.recorder)
    assert quality.arousal_by_paragraph == []
    assert {name: getattr(quality, name).score for name in DIMENSIONS} == scores
    assert any(
        "Arousal chart omitted" in warning for warning in reviewed.assessment.metrics.warnings
    )


def test_quote_can_recover_unique_source_and_remove_trailing_ellipsis():
    story = Story(title="Moon", paragraphs=["Alice opens the curtain.", "Bob rests beside her."])
    evidence = [Evidence(paragraph=1, quote="Bob rests beside her...", observation="He rests.")]
    verify_evidence(evidence, story, restore_case=True, repair_citations=True)
    assert evidence[0].paragraph == 2
    assert evidence[0].quote == "Bob rests beside her"
    assert evidence[0].quote in story.paragraphs[1]


def test_ambiguous_quote_cannot_be_reassigned_to_another_paragraph():
    story = Story(title="Moon", paragraphs=["Bob rests.", "Bob rests.", "Alice opens the curtain."])
    evidence = [Evidence(paragraph=3, quote="Bob rests.", observation="He rests.")]
    with pytest.raises(ResponseValidationError):
        verify_evidence(evidence, story, repair_citations=True)
