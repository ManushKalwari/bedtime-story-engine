"""Measure detection of seeded defects and false rejections of positive controls."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from story_engine import agents
from story_engine.config import THRESHOLDS
from story_engine.schemas import HolisticVerdict, Story, StoryRequest
from story_engine.telemetry import EngineError

from .common import append_jsonl, load_data, make_client, percent, reference_brief


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--output", type=Path, default=Path("evals/results"))
    args = p.parse_args(argv)
    if args.repeats < 1:
        p.error("repeats must be positive")
    cases = load_data("calibration.json")
    print(f"{len(cases)} seeded cases × {args.repeats} repeats. At least 3 calls per case.")
    if not args.execute:
        print(
            "Plan only. Add --execute for live model judgments. Seed labels are provisional editorial expectations."
        )
        return 0
    folder = args.output / datetime.now(timezone.utc).strftime("calibration-%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    rows = []
    for case in cases:
        for repeat in range(args.repeats):
            request = StoryRequest(
                prompt=case["prompt"], age=case["age"], length=case.get("length", "short")
            )
            story = Story.model_validate(case["story"])
            client = make_client()
            row = {
                "id": case["id"],
                "repeat": repeat,
                "expected_accept": case["expected_accept"],
                "target_dimensions": case["target_dimensions"],
                "label_provenance": "synthetic editorial expectation",
            }
            try:
                assessed = agents.review(client, story, reference_brief(case), request, [])
                # Intentionally separate semantic judge validity from trivial length checking.
                semantic_accept = assessed.safety.safe and assessed.deficits() == 0
                caught = [
                    d
                    for d in case["target_dimensions"]
                    if (
                        not assessed.safety.safe
                        if d == "safety"
                        else assessed.scores()[d] < THRESHOLDS[d]
                    )
                ]
                row.update(
                    structured_accept=semantic_accept,
                    caught_dimensions=caught,
                    structured_review=assessed.model_dump(),
                )
            except EngineError as exc:
                row["structured_error"] = str(exc)
            try:
                holistic = client.structured(
                    "eval.holistic",
                    "Rate this bedtime story 1–10 for the requested child; give feedback. Return JSON.",
                    {"request": request.model_dump(), "story": story.model_dump()},
                    HolisticVerdict,
                )
                row.update(naive_accept=holistic.score >= 8, naive_review=holistic.model_dump())
            except EngineError as exc:
                row["naive_error"] = str(exc)
            row["usage"] = client.recorder.summary()
            client.recorder.save(folder / f"{case['id']}-{repeat}-trace.jsonl")
            append_jsonl(folder / "results.jsonl", row)
            rows.append(row)
    lines = [
        "# Judge calibration",
        "",
        "Seeded fixtures are provisional expectations, not expert-labeled ground truth.",
        "Errors are not counted as correctly detected defects. Length failures are excluded from semantic detection.",
        "",
        "| Judge | Correct / all | Valid results | False accept / bad valid | False reject / good valid |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("structured", "naive"):
        key = name + "_accept"
        valid = [r for r in rows if key in r]
        good = [r for r in valid if r["expected_accept"]]
        bad = [r for r in valid if not r["expected_accept"]]
        lines.append(
            f"| {name} | {percent(sum(r[key] == r['expected_accept'] for r in valid), len(rows))} "
            f"| {len(valid)}/{len(rows)} | {percent(sum(r[key] for r in bad), len(bad))} "
            f"| {percent(sum(not r[key] for r in good), len(good))} |"
        )
    lines.extend(
        [
            "",
            "| Targeted defect dimension | Detected / all targeted cases | Invalid structured results |",
            "|---|---:|---:|",
        ]
    )
    dimensions = sorted({d for row in rows for d in row["target_dimensions"]})
    for dimension in dimensions:
        targeted = [row for row in rows if dimension in row["target_dimensions"]]
        detected = sum(dimension in row.get("caught_dimensions", []) for row in targeted)
        invalid = sum("structured_accept" not in row for row in targeted)
        lines.append(f"| {dimension} | {percent(detected, len(targeted))} | {invalid} |")
    lines.extend(
        [
            "",
            "Inspect caught_dimensions to distinguish detecting the intended defect from rejecting for another reason.",
            "Small synthetic sets do not establish general safety or quality. Revise labels through your own review.",
        ]
    )
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("Saved", folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
