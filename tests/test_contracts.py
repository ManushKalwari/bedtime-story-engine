import pytest
from pydantic import ValidationError

from story_engine import agents
from story_engine.config import Settings
from story_engine.llm import Completion, ModelClient, parse_json
from story_engine.metrics import measure, words
from story_engine.schemas import Brief, Patch, Story, StoryRequest
from story_engine.telemetry import BudgetExceeded, EngineError, Recorder


class QueueTransport:
    synthetic = True

    def __init__(self, values):
        self.values = iter(values)

    def complete(self, *a, **kw):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, Completion) else Completion(value, usage_known=False)


def make_queue(values, **settings):
    return ModelClient(QueueTransport(values), Recorder(Settings(**settings)))


@pytest.mark.parametrize("age", [4, 11, True, "7"])
def test_invalid_age(age):
    with pytest.raises(ValidationError):
        StoryRequest(prompt="A moon.", age=age)


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
def test_empty_or_excessive_input(text):
    with pytest.raises(ValidationError):
        StoryRequest(prompt=text)


def test_reframe_requires_disclosure():
    with pytest.raises(ValidationError):
        Brief(
            premise="A friendly monster.",
            category="comfort",
            age=6,
            length="short",
            constraints=[],
            decision="reframe",
            parent_note="",
        )


def test_json_fences_and_reject_embedded_extra_objects():
    assert parse_json('```json\n{"a":1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json('{"a":1} {"a":2}')


def test_repair_is_bounded_and_can_recover():
    valid = '{"title":"Moon","paragraphs":["The moon is quiet."]}'
    client = make_queue(['{"title":', valid])
    assert client.structured("writer", "Return JSON", {}, Story).title == "Moon"
    assert client.recorder.attempts == 2
    client = make_queue(["bad", "still bad"])
    with pytest.raises(EngineError, match="bounded repair"):
        client.structured("writer", "Return JSON", {}, Story)
    assert client.recorder.attempts == 2


def test_contextual_validation_also_repairs():
    raw = '{"title":"Moon","paragraphs":["A quiet moon."]}'
    client = make_queue([raw, raw])
    with pytest.raises(EngineError):
        client.structured(
            "writer",
            "JSON",
            {},
            Story,
            validate=lambda v: (_ for _ in ()).throw(ValueError("Wrong quote")),
        )


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_incomplete_generation_never_accepted(reason):
    client = make_queue([Completion('{"title":"Moon"}', finish_reason=reason)])
    with pytest.raises(EngineError, match="Incomplete"):
        client.call("writer", [])


def test_budget_counts_json_repair():
    client = make_queue(["bad"], max_calls=1)
    with pytest.raises(BudgetExceeded):
        client.structured("judge", "JSON", {}, Story)


def test_patch_preserves_other_paragraphs():
    story = Story(title="Moon", paragraphs=["First.", "Second.", "Third."])
    patch = Patch(edits=[{"paragraph": 2, "replacement": "A new middle."}])
    result = agents.apply_patch(story, patch)
    assert result.paragraphs == ["First.", "A new middle.", "Third."]
    assert story.paragraphs[1] == "Second."
    assert result.title == story.title


def test_duplicate_and_invalid_patch_targets():
    with pytest.raises(ValidationError):
        Patch(edits=[{"paragraph": 1, "replacement": "a"}, {"paragraph": 1, "replacement": "b"}])
    with pytest.raises(ValueError):
        agents.apply_patch(
            Story(title="M", paragraphs=["A."]),
            Patch(edits=[{"paragraph": 2, "replacement": "B."}]),
        )


def test_metrics_counts_and_soft_flags():
    story = Story(
        title="Excluded title", paragraphs=['"Hello," said Alice. Bob is a kind monster.']
    )
    metrics = measure(story, (1, 20))
    assert metrics.word_count == 8
    assert metrics.paragraph_count == 1
    assert metrics.dialogue_word_fraction > 0
    assert metrics.lexical_flags == ["monster"]
    assert not metrics.failures  # A word match alone is not a safety failure.
    assert measure(story, (30, 50)).failures
    assert words("Alice’s cat isn't sleepy.") == ["Alice’s", "cat", "isn't", "sleepy"]


def test_evidence_must_exist_in_correct_paragraph():
    from story_engine.schemas import Evidence

    story = Story(title="Moon", paragraphs=["Bob is a cat.", "Alice rests."])
    with pytest.raises(ValueError):
        agents.verify_evidence(
            [Evidence(paragraph=2, quote="Bob is a cat.", observation="Identity")], story
        )


def test_semantic_boolean_cannot_be_string():
    from story_engine.schemas import SafetyReview

    with pytest.raises(ValidationError):
        SafetyReview(safe="true", evidence=[], concerns=[], fixes=[])
