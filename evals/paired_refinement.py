"""Compare generic rewrite and targeted edit from the SAME draft and critique."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from story_engine import agents
from story_engine.config import word_bounds
from story_engine.engine import retain_candidate
from story_engine.schemas import Draft, Story, StoryRequest
from story_engine.telemetry import EngineError

from .common import append_jsonl, compare_pair, load_data, make_client, reference_brief


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--limit", type=int, default=2)
    p.add_argument("--split", choices=["dev", "heldout"], default="dev")
    p.add_argument("--output", type=Path, default=Path("evals/results"))
    args = p.parse_args(argv)
    if args.limit < 1:
        p.error("limit must be positive")
    cases = [c for c in load_data("requests.json") if c["split"] == args.split][: args.limit]
    print(f"{len(cases)} paired refinement cases. Approximately 15 calls/case before repairs.")
    if not args.execute:
        print(
            "Plan only. Add --execute to run. This experiment may show no benefit or regressions."
        )
        return 0
    folder = args.output / datetime.now(timezone.utc).strftime("paired-%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    for case in cases:
        request = StoryRequest(
            prompt=case["prompt"], age=case["age"], length=case.get("length", "standard")
        )
        client = make_client()
        row = {"case_id": case["id"], "request": request.model_dump()}
        try:
            brief = reference_brief(case)
            blueprint = agents.plan(client, brief)
            original = agents.write(client, brief, blueprint)
            assessment = agents.review(client, original, brief, request, [])
            initial = Draft(
                version=0,
                story=original,
                assessment=assessment,
                retained=True,
                decision="shared starting draft",
            )
            row["initial"] = initial.model_dump()
            targeted = agents.edit(client, initial, brief, [])
            generic = client.structured(
                "eval.generic_rewrite",
                agents.prompt("writer")
                + "\nRewrite the entire story using the provided critique. Preserve the request.",
                {
                    "story": original.model_dump(),
                    "critique": assessment.model_dump(),
                    "brief": brief.model_dump(),
                    "body_word_range": word_bounds(brief.age, brief.length),
                },
                Story,
                temperature=client.settings.editor_temperature,
            )
            targeted_review = agents.review(client, targeted, brief, request, [])
            generic_review = agents.review(client, generic, brief, request, [])
            retain, reason = retain_candidate(assessment, targeted_review)
            row.update(
                targeted=targeted.model_dump(),
                generic=generic.model_dump(),
                targeted_review=targeted_review.model_dump(),
                generic_review=generic_review.model_dump(),
                rollback_retains_targeted=retain,
                rollback_reason=reason,
                targeted_minus_initial=targeted_review.average() - assessment.average(),
                generic_minus_initial=generic_review.average() - assessment.average(),
            )
            row["pairwise_targeted_vs_generic"] = compare_pair(client, request, targeted, generic)
            row["pairwise_initial_vs_targeted"] = compare_pair(client, request, original, targeted)
        except EngineError as exc:
            row["error"] = str(exc)
        row["usage"] = client.recorder.summary()
        client.recorder.save(folder / f"{case['id']}-trace.jsonl")
        append_jsonl(folder / "results.jsonl", row)
    (folder / "README.md").write_text(
        "# Paired edit experiment\n\nEach case shares the exact initial story and critique. "
        "Compare targeted versus full rewrite, measured regressions, and order-swapped votes. "
        "The rollback decision is logged separately from raw candidate quality; do not hide rejected drafts. "
        "Dollar estimates require configured pricing. These same-model ratings need your manual review.\n",
        encoding="utf-8",
    )
    print("Saved", folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
