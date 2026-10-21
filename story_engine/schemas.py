"""Validated boundaries between probabilistic model output and deterministic code."""

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .config import DIMENSIONS, THRESHOLDS

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Score = Annotated[int, Field(strict=True, ge=1, le=5)]
Category = Literal["friendship", "wonder", "comfort", "whimsy", "sensory"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class StoryRequest(StrictModel):
    prompt: Text
    age: int = Field(default=7, strict=True, ge=5, le=10)
    length: Literal["short", "standard"] = "standard"


class Brief(StrictModel):
    premise: Text
    category: Category
    age: int = Field(strict=True, ge=5, le=10)
    length: Literal["short", "standard"]
    constraints: list[Text] = Field(max_length=12)
    decision: Literal["allow", "reframe", "decline"]
    parent_note: str = Field(max_length=700)

    @model_validator(mode="after")
    def disclose_changes(self):
        if self.decision != "allow" and not self.parent_note.strip():
            raise ValueError("A reframe or decline requires a parent-facing explanation")
        return self


class CraftPlan(StrictModel):
    character_desire: Text
    distinctive_behavior: Text
    setup: Text
    payoff: Text


class Blueprint(StrictModel):
    characters: list[Text] = Field(min_length=1, max_length=5)
    beats: list[Text] = Field(min_length=3, max_length=6)
    continuity_facts: list[Text] = Field(max_length=10)
    wind_down: Text
    craft: CraftPlan | None = None  # Older persisted runs predate craft planning.


class PlannedBlueprint(Blueprint):
    craft: CraftPlan  # Required for newly generated plans, not historical artifacts.


class Story(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    paragraphs: list[Text] = Field(min_length=1, max_length=16)

    def body(self) -> str:
        return "\n\n".join(self.paragraphs)


class Evidence(StrictModel):
    paragraph: int = Field(strict=True, ge=1, le=16)
    quote: str = Field(min_length=1, max_length=400)
    observation: str = Field(min_length=1, max_length=350)


class SafetyVerdict(StrictModel):
    """The concise contract requested from the live safety reviewer."""

    safe: bool = Field(strict=True)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]


class SafetyReview(StrictModel):
    safe: bool = Field(strict=True)
    reason: str | None = Field(default=None, min_length=1, max_length=400)
    evidence: list[Evidence] = Field(default_factory=list, max_length=5)  # Historical run support.
    concerns: list[Text] = Field(max_length=5)
    fixes: list[Text] = Field(max_length=5)

    @model_validator(mode="after")
    def consistent(self):
        if self.safe and self.concerns:
            raise ValueError("safe=true cannot coexist with safety concerns")
        if not self.safe and not self.concerns:
            raise ValueError("Unsafe verdict needs a concern")
        return self


class Rating(StrictModel):
    evidence: Evidence
    score: Score


class Fix(StrictModel):
    paragraph: int = Field(strict=True, ge=1, le=16)
    instruction: Text


class SetupPayoff(StrictModel):
    setup: Evidence
    payoff: Evidence

    @model_validator(mode="after")
    def chronological(self):
        if self.setup.paragraph > self.payoff.paragraph:
            raise ValueError("The setup must precede its payoff")
        return self


class CraftReview(StrictModel):
    resolution: Evidence
    specificity: Evidence
    setup_payoff: SetupPayoff | None = None


class QualityReview(StrictModel):
    age_fit: Rating
    coherence: Rating
    fidelity: Rating
    warmth: Rating
    bedtime_calm: Rating
    cadence: Rating
    preserve: list[Text] = Field(default_factory=list, max_length=5)
    fixes: list[Fix] = Field(default_factory=list, max_length=6)
    arousal_by_paragraph: list[Score] = Field(default_factory=list)
    craft: CraftReview | None = None  # Compatibility with previously saved reviews.


class GroundedQualityReview(QualityReview):
    craft: CraftReview

    @model_validator(mode="before")
    @classmethod
    def normalize_score_placement(cls, value):
        """Accept a known nesting mistake without inventing or choosing any rating."""
        if not isinstance(value, dict):
            return value
        data = deepcopy(value)
        for dimension in DIMENSIONS:
            rating = data.get(dimension)
            if not isinstance(rating, dict) or not isinstance(rating.get("evidence"), dict):
                continue
            evidence = rating["evidence"]
            if "score" not in evidence:
                continue
            nested = evidence.pop("score")
            if "score" in rating:
                if type(rating["score"]) is not type(nested) or rating["score"] != nested:
                    raise ValueError(
                        f"{dimension} has conflicting scores inside and outside evidence; "
                        "return one honest dimension score, outside evidence"
                    )
            else:
                rating["score"] = nested
        # Craft notes are evidence, not additional scored acceptance dimensions.
        craft = data.get("craft")
        if isinstance(craft, dict):
            notes = [craft.get("resolution"), craft.get("specificity")]
            connection = craft.get("setup_payoff")
            if isinstance(connection, dict):
                notes.extend([connection.get("setup"), connection.get("payoff")])
            for note in notes:
                if isinstance(note, dict):
                    note.pop("score", None)
        return data


class ParagraphEdit(StrictModel):
    paragraph: int = Field(strict=True, ge=1, le=16)
    replacement: Text


class Patch(StrictModel):
    edits: list[ParagraphEdit] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_targets(self):
        ids = [e.paragraph for e in self.edits]
        if len(ids) != len(set(ids)):
            raise ValueError("A paragraph may only be edited once per patch")
        return self


class Metrics(StrictModel):
    word_count: int
    paragraph_count: int
    sentence_count: int
    mean_sentence_words: float
    estimated_fk_grade: float
    estimated_syllables_per_word: float
    dialogue_word_fraction: float
    lexical_flags: list[str]
    failures: list[str]
    warnings: list[str]


class Assessment(StrictModel):
    metrics: Metrics
    safety: SafetyReview
    quality: QualityReview

    def scores(self) -> dict[str, int]:
        return {key: getattr(self.quality, key).score for key in DIMENSIONS}

    def deficits(self) -> int:
        return sum(max(0, THRESHOLDS[k] - v) for k, v in self.scores().items())

    def eligible(self) -> bool:
        return self.safety.safe and not self.metrics.failures and self.deficits() == 0

    def average(self) -> float:
        return sum(self.scores().values()) / len(DIMENSIONS)


class Draft(StrictModel):
    version: int
    story: Story
    assessment: Assessment
    retained: bool
    decision: str


class RunResult(StrictModel):
    run_id: str
    provenance: Literal["live", "synthetic"]
    request: StoryRequest
    feedback: list[str]
    brief: Brief | None = None
    blueprint: Blueprint | None = None
    drafts: list[Draft] = Field(default_factory=list)
    selected_version: int | None = None
    status: Literal["accepted", "declined", "failed", "unverified"]
    stop_reason: str
    warnings: list[str] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)

    def selected(self) -> Draft | None:
        return next((d for d in self.drafts if d.version == self.selected_version), None)


class PairVerdict(StrictModel):
    winner: Literal["A", "B", "tie"]
    explanation: str = Field(min_length=1, max_length=700)


class HolisticVerdict(StrictModel):
    score: int = Field(strict=True, ge=1, le=10)
    feedback: Text
