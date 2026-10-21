"""Control draft acceptance, revisions, and rollback."""

from . import agents
from .config import word_bounds
from .schemas import Draft, RunResult
from .telemetry import EngineError


def retain_candidate(old, new, *, allow_equal=False, word_range=None) -> tuple[bool, str]:
    """Keep safety repairs and candidates without measured regressions."""
    if old.safety.safe and not new.safety.safe:
        return False, "rollback: safety regressed"
    if not old.safety.safe and new.safety.safe:
        return True, "retained: safety concern resolved (other gates still apply)"
    if len(new.metrics.failures) > len(old.metrics.failures):
        return False, "rollback: deterministic constraints regressed"
    length_improved = False
    if word_range is not None:
        minimum, maximum = word_range
        old_gap = max(minimum - old.metrics.word_count, old.metrics.word_count - maximum, 0)
        new_gap = max(minimum - new.metrics.word_count, new.metrics.word_count - maximum, 0)
        if new_gap > old_gap:
            return False, "rollback: word count moved farther from the required range"
        length_improved = new_gap < old_gap
    old_scores, new_scores = old.scores(), new.scores()
    if any(new_scores[k] < old_scores[k] for k in old_scores):
        return False, "rollback: at least one rubric dimension regressed"
    improved = (
        len(new.metrics.failures) < len(old.metrics.failures)
        or any(new_scores[k] > old_scores[k] for k in old_scores)
        or len(new.safety.concerns) < len(old.safety.concerns)
    )
    if improved:
        return True, "retained: measured improvement"
    if length_improved:
        return True, "retained: word count moved closer to the required range"
    if allow_equal and new.eligible():
        return True, "retained: requested edit with no measured regression"
    return False, "rollback: no measured improvement"


class StoryEngine:
    def __init__(self, client):
        self.client = client

    def run(self, request, *, previous=None, change=None) -> RunResult:
        feedback = list(previous.feedback) if previous else []
        if change:
            if len(feedback) >= 6 or not change.strip() or len(change) > 1500:
                raise ValueError(
                    "Use at most six nonempty changes of at most 1500 characters per story"
                )
            feedback.append(change.strip())
        result = RunResult(
            run_id=self.client.recorder.run_id,
            provenance="synthetic" if self.client.transport.synthetic else "live",
            request=request,
            feedback=feedback,
            status="failed",
            stop_reason="not_started",
        )
        try:
            result.brief = agents.intake(self.client, request, feedback, previous)
            if result.brief.decision == "decline":
                result.status, result.stop_reason = "declined", "intake_declined"
                return result
            if previous and previous.selected():
                # Evaluate the incumbent under the NEW request, never compare stale scores.
                story = previous.selected().story
                result.blueprint = previous.blueprint
            else:
                result.blueprint = agents.plan(self.client, result.brief)
                story = agents.write(self.client, result.brief, result.blueprint)
            assessment = agents.review(self.client, story, result.brief, request, feedback)
            incumbent = Draft(
                version=0,
                story=story,
                assessment=assessment,
                retained=True,
                decision="initial assessment under current requirements",
            )
            result.drafts.append(incumbent)
            for revision in range(self.client.settings.max_revisions + 1):
                # A user edit should be attempted even if the judge overlooks the change.
                force_change = bool(change) and revision == 0
                if incumbent.assessment.eligible() and not force_change:
                    result.stop_reason = "quality_gates_met"
                    break
                if revision == self.client.settings.max_revisions:
                    result.stop_reason = "revision_limit"
                    break
                candidate_story = agents.edit(self.client, incumbent, result.brief, feedback)
                if candidate_story == incumbent.story:
                    result.stop_reason = "unchanged_edit"
                    break
                candidate_assessment = agents.review(
                    self.client, candidate_story, result.brief, request, feedback
                )
                keep, reason = retain_candidate(
                    incumbent.assessment,
                    candidate_assessment,
                    allow_equal=bool(change),
                    word_range=word_bounds(result.brief.age, result.brief.length),
                )
                candidate = Draft(
                    version=revision + 1,
                    story=candidate_story,
                    assessment=candidate_assessment,
                    retained=keep,
                    decision=reason,
                )
                result.drafts.append(candidate)
                self.client.recorder.add(
                    {
                        "type": "decision",
                        "version": candidate.version,
                        "retained": keep,
                        "reason": reason,
                    }
                )
                if keep:
                    incumbent = candidate
                else:
                    result.stop_reason = "regression_or_plateau"
                    break
            if incumbent.assessment.eligible():
                result.status = "accepted"
                result.selected_version = incumbent.version
            if change and result.selected_version == 0:
                result.warnings.append(
                    "The requested change was not retained; the prior story remains."
                )
        except EngineError as exc:
            result.stop_reason = str(exc)
            # Only a previously fully reviewed eligible draft from THIS request may survive.
            approved = [d for d in result.drafts if d.retained and d.assessment.eligible()]
            if approved:
                result.status = "accepted"
                result.selected_version = approved[-1].version
                result.warnings.append("A later step failed; returning the earlier reviewed draft.")
        finally:
            result.usage = self.client.recorder.summary()
        return result
