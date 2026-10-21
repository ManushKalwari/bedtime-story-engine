"""LLM stages for intake, planning, writing, review, and editing."""

from concurrent.futures import ThreadPoolExecutor
from importlib.resources import files

from .config import ARCS, word_bounds
from .metrics import measure
from .review_validation import validate_quality, verify_evidence
from .schemas import (
    Assessment,
    Brief,
    GroundedQualityReview,
    Patch,
    PlannedBlueprint,
    SafetyReview,
    SafetyVerdict,
    Story,
)
from .techniques import select_techniques
from .telemetry import EngineError


def prompt(name: str) -> str:
    return files("story_engine").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")


def length_task(brief, current_words=None):
    """Give the model a concrete writing target and precomputed repair amounts."""
    minimum, maximum = word_bounds(brief.age, brief.length)
    target = (minimum + maximum) // 2
    task = {"target_body_words": target, "instruction": f"Aim for about {target} body words."}
    if current_words is not None:
        task["current_body_words"] = current_words
        task["minimum_words_to_add"] = max(0, minimum - current_words)
        task["minimum_words_to_remove"] = max(0, current_words - maximum)
        if current_words < minimum:
            task["instruction"] = (
                f"Expand the body by at least {minimum - current_words} words; "
                f"aim to add about {target - current_words} words to reach {target}. "
                "Add connected actions or discoveries inside existing paragraphs."
            )
        elif current_words > maximum:
            task["instruction"] = (
                f"Shorten the body by at least {current_words - maximum} words; "
                f"aim to remove about {current_words - target} words to reach {target}. "
                "Keep the character's goal, setup, payoff, and quiet ending."
            )
    return task


def intake(client, request, feedback, previous=None):
    def validate(brief):
        if not feedback and (brief.age != request.age or brief.length != request.length):
            raise ValueError("Initial age and length must match the supplied settings")

    return client.structured(
        "intake",
        prompt("intake"),
        {
            "request": request.model_dump(),
            "feedback_ledger": feedback,
            "previous_brief": previous.brief.model_dump() if previous and previous.brief else None,
            "previous_story": previous.selected().story.model_dump()
            if previous and previous.selected()
            else None,
        },
        Brief,
        validate=validate,
    )


def plan(client, brief, *, use_techniques=True):
    payload = {
        "brief": brief.model_dump(),
        "narrative_spine": ARCS[brief.category],
    }
    if use_techniques:
        payload["storytelling_techniques"] = select_techniques(
            brief.category, brief.age, brief.length
        )
    return client.structured(
        "planner",
        prompt("planner"),
        payload,
        PlannedBlueprint,
        temperature=0.3,
    )


def write(client, brief, blueprint=None, *, use_techniques=True):
    payload = {
        "brief": brief.model_dump(),
        "body_word_range": word_bounds(brief.age, brief.length),
        "length_task": length_task(brief),
        "narrative_spine": ARCS[brief.category],
        "blueprint": blueprint.model_dump() if blueprint else None,
    }
    if use_techniques:
        payload["storytelling_techniques"] = select_techniques(
            brief.category, brief.age, brief.length
        )
    return client.structured(
        "writer",
        prompt("writer"),
        payload,
        Story,
        temperature=client.settings.writer_temperature,
    )


def review(client, story, brief, request, feedback):
    metrics = measure(story, word_bounds(brief.age, brief.length))
    payload = {
        "story": story.model_dump(),
        "brief": brief.model_dump(),
        "original_request": request.model_dump(),
        "feedback_ledger": feedback,
        "code_metrics": metrics.model_dump(),
    }

    def safety():
        verdict = client.structured(
            "safety",
            prompt("safety"),
            payload,
            SafetyVerdict,
            temperature=0,
            repair_instruction="Return exactly safe (a JSON boolean) and reason "
            "(one brief, nonempty explanation, at most 400 characters). "
            "Do not include quotes, evidence, concerns, or fixes fields. "
            "Preserve your honest assessment when correcting the response.",
        )
        # Keep the controller and historical run format compatible; never infer a verdict.
        return SafetyReview(
            safe=verdict.safe,
            reason=verdict.reason,
            concerns=[] if verdict.safe else [verdict.reason],
            fixes=[],
        )

    def quality():
        return client.structured(
            "quality",
            prompt("quality"),
            {
                **payload,
                "review_requirements": {
                    "paragraph_count": len(story.paragraphs),
                    "paragraph_numbers": list(range(1, len(story.paragraphs) + 1)),
                },
            },
            GroundedQualityReview,
            temperature=0,
            validate=lambda review: validate_quality(review, story, metrics, client.recorder),
            repair_instruction="Correct ALL reported evidence and paragraph-reference "
            "errors, not just the first. Always include craft.resolution and "
            "craft.specificity, each with paragraph, quote, and observation. "
            "craft.setup_payoff may be omitted or null when no meaningful connection "
            "is identified; do not invent one. Preserve all valid scored dimensions "
            "when repairing another field. The preserve and fixes lists may be omitted "
            "when empty. Put each dimension's score outside evidence; evidence contains "
            "only paragraph, quote, and observation. Craft evidence has no score. "
            "Keep scores honest. Arousal annotations are "
            f"optional; if supplied, return exactly {len(story.paragraphs)} ratings "
            "in paragraph order, excluding the title.",
        )

    if client.settings.parallel_reviews:
        with ThreadPoolExecutor(max_workers=2) as pool:
            s, q = pool.submit(safety), pool.submit(quality)
            safety_result, quality_result = s.result(), q.result()
    else:
        safety_result, quality_result = safety(), quality()
    return Assessment(metrics=metrics, safety=safety_result, quality=quality_result)


def apply_patch(story: Story, patch: Patch) -> Story:
    paragraphs = list(story.paragraphs)
    for edit in patch.edits:
        if edit.paragraph > len(paragraphs):
            raise ValueError("Patch paragraph outside the story")
        paragraphs[edit.paragraph - 1] = edit.replacement
    return Story(title=story.title, paragraphs=paragraphs)


def edit(client, draft, brief, feedback):
    def validate(patch):
        apply_patch(draft.story, patch)

    craft = draft.assessment.quality.craft
    connection = craft.setup_payoff if craft else None
    if connection:
        # Persisted reviews may bypass current live validation; never forward ungrounded anchors.
        try:
            verify_evidence([connection.setup, connection.payoff], draft.story)
        except ValueError as exc:
            raise EngineError(
                "The editor's protected connection is not grounded in this draft"
            ) from exc
    bounds = word_bounds(brief.age, brief.length)
    current_words = measure(draft.story, bounds).word_count
    patch = client.structured(
        "editor",
        prompt("editor"),
        {
            "story": draft.story.model_dump(),
            "brief": brief.model_dump(),
            "feedback_ledger": feedback,
            "assessment": draft.assessment.model_dump(),
            "body_word_range": bounds,
            "length_task": length_task(brief, current_words),
            "protected_connection": connection.model_dump() if connection else None,
        },
        Patch,
        temperature=client.settings.editor_temperature,
        validate=validate,
    )
    return apply_patch(draft.story, patch)
