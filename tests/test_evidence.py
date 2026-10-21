import pytest

from story_engine import agents
from story_engine.schemas import Evidence, Story
from story_engine.telemetry import ResponseValidationError


def test_mid_sentence_capitalization_is_restored_from_source():
    story = Story(
        title="The Rabbit",
        paragraphs=["Sitting under a tree, the rabbit shared stories of the stars."],
    )
    evidence = [
        Evidence(
            paragraph=1,
            quote="The rabbit shared stories of the stars.",
            observation="An observation.",
        )
    ]
    assert agents.verify_evidence(evidence, story, restore_case=True) == [0]
    assert evidence[0].quote == "the rabbit shared stories of the stars."
    assert evidence[0].observation == "An observation."


@pytest.mark.parametrize(
    "quote,paragraph",
    [
        ("The rabbit changed stories of the stars.", 1),
        ("The rabbit shared stories of the stars!", 1),
        ("The rabbit  shared stories of the stars.", 1),
        ("The rabbit shared stories of the stars.", 2),
    ],
)
def test_quality_evidence_still_rejects_changed_words_punctuation_and_wrong_paragraph(
    quote, paragraph
):
    story = Story(
        title="The Rabbit",
        paragraphs=[
            "Sitting under a tree, the rabbit shared stories of the stars.",
            "Alice rested beside Bob.",
        ],
    )
    evidence = [Evidence(paragraph=paragraph, quote=quote, observation="An observation.")]
    with pytest.raises(ResponseValidationError, match="verbatim substring"):
        agents.verify_evidence(evidence, story, restore_case=True)


def test_real_quote_mismatch_identifies_field_and_supplies_source_to_repair():
    story = Story(title="Cushion", paragraphs=["Alice kept a small blue cushion."])
    evidence = [
        Evidence(
            paragraph=1, quote="Alice kept a large green cushion.", observation="Changed words."
        )
    ]
    with pytest.raises(ResponseValidationError) as caught:
        agents.verify_evidence(evidence, story, restore_case=True)
    assert caught.value.path == ("evidence", 0, "quote")
    assert caught.value.code == "quote_mismatch"
    assert "actual_text" in caught.value.repair_hint
    assert story.paragraphs[0] in caught.value.repair_hint
    assert "Alice" not in str(caught.value)
