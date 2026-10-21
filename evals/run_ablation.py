"""Run architecture comparisons. Default is a cost-awareness plan; --execute makes API calls."""

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from story_engine import agents
from story_engine.config import MODEL, PROMPT_VERSION, Settings
from story_engine.schemas import StoryRequest
from story_engine.telemetry import EngineError

from .common import (
    VARIANTS,
    append_jsonl,
    compare_pair,
    export_blind,
    generate_variant,
    load_data,
    make_client,
    percent,
    reference_brief,
)


def summarize(rows, path):
    lines = [
        "# Architecture experiment",
        "",
        "LIVE observations only. No variant is presumed to win.",
        "",
        "Pass rates include errors and non-emissions as failures. Valid-output rates are also shown.",
        "Audit ratings are fallible same-model measurements, not human preference or a safety certificate.",
        "",
        "| Variant | All cases | Emitted | Audit pass / all | Audit pass / audited | Generation seconds (mean) | Generation tokens |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in dict.fromkeys(r["variant"] for r in rows):
        rs = [r for r in rows if r["variant"] == variant]
        audited = [r for r in rs if r.get("audit")]
        passed = sum(r.get("audit_pass", False) for r in rs)
        tokens = sum(
            r["generation_usage"]["input_tokens"] + r["generation_usage"]["output_tokens"]
            for r in rs
        )
        seconds = sum(r["generation_usage"]["elapsed_seconds"] for r in rs) / len(rs)
        lines.append(
            f"| {variant} | {len(rs)} | {sum(r['emitted'] for r in rs)} | {percent(passed, len(rs))} | {percent(passed, len(audited))} | {seconds:.2f} | {tokens} |"
        )
    lines.extend(
        [
            "",
            "Generation, common-audit, and pairwise usage are recorded separately in results.jsonl.",
            "Dollar estimates appear only when explicit input/output token prices are configured.",
            "FK grade is heuristic telemetry; no readability-compliance claim is made.",
            "Inspect errors, per-dimension ratings, first/final drafts and all denominators before concluding.",
            "The raw baseline lacks age instructions. Compare full against engineered/planned as stronger controls.",
            "This ladder changes multiple factors. Use paired refinement for a cleaner edit-mechanism comparison.",
            "Full also receives storytelling techniques; planned and naive_rewrite disable the library.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    p.add_argument(
        "--pairwise",
        action="store_true",
        help="Compare each emitted variant to engineered, both orders",
    )
    p.add_argument("--output", type=Path, default=Path("evals/results"))
    args = p.parse_args(argv)
    if args.limit < 1 or args.repeats < 1:
        p.error("limit and repeats must be positive")
    cases = [
        c for c in load_data("requests.json") if args.split == "all" or c["split"] == args.split
    ][: args.limit]
    print(
        f"{len(cases)} cases × {args.repeats} repeats × {len(args.variants)} variants. Model: {MODEL}."
    )
    print(
        "Each generation has a 24-attempt cap; common audits and optional pairwise comparisons add calls."
    )
    if not args.execute:
        print("Plan only. Add --execute to use your API key and incur charges.")
        return 0
    folder = args.output / datetime.now(timezone.utc).strftime("ablation-%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    settings = Settings.from_env()
    rows = []
    for case in cases:
        for repeat in range(args.repeats):
            variants = list(dict.fromkeys(args.variants))
            random.Random(case["id"] + str(repeat)).shuffle(variants)
            group = []
            for variant in variants:
                request = StoryRequest(
                    prompt=case["prompt"], age=case["age"], length=case.get("length", "standard")
                )
                client = make_client(settings)
                row = {
                    "case_id": case["id"],
                    "split": case["split"],
                    "repeat": repeat,
                    "variant": variant,
                    "model": MODEL,
                    "prompt_version": PROMPT_VERSION,
                    "request": request.model_dump(),
                    "emitted": False,
                    "story": None,
                }
                try:
                    story, emitted, detail = generate_variant(client, request, variant)
                    row.update(
                        emitted=emitted, story=story.model_dump() if story else None, detail=detail
                    )
                except (EngineError, ValidationError) as exc:
                    row["generation_error"] = str(exc)
                row["generation_usage"] = client.recorder.summary()
                client.recorder.save(folder / f"{case['id']}-{repeat}-{variant}-generation.jsonl")
                if row["story"]:
                    audit_client = make_client(settings)
                    try:
                        audit = agents.review(
                            audit_client, story, reference_brief(case), request, []
                        )
                        row.update(audit=audit.model_dump(), audit_pass=audit.eligible())
                    except EngineError as exc:
                        row["audit_error"] = str(exc)
                    row["audit_usage"] = audit_client.recorder.summary()
                    audit_client.recorder.save(
                        folder / f"{case['id']}-{repeat}-{variant}-audit.jsonl"
                    )
                rows.append(row)
                group.append(row)
                append_jsonl(folder / "results.jsonl", row)
                summarize(rows, folder / "report.md")
                print(case["id"], variant, "audit_pass=", row.get("audit_pass", False))
            if args.pairwise:
                baseline = next(
                    (r for r in group if r["variant"] == "engineered" and r["story"]), None
                )
                if baseline:
                    from story_engine.schemas import Story

                    for row in group:
                        if row is baseline or not row["story"]:
                            continue
                        judge = make_client(settings)
                        pair = {
                            "case_id": case["id"],
                            "repeat": repeat,
                            "left": "engineered",
                            "right": row["variant"],
                        }
                        try:
                            pair.update(
                                compare_pair(
                                    judge,
                                    request,
                                    Story.model_validate(baseline["story"]),
                                    Story.model_validate(row["story"]),
                                )
                            )
                        except EngineError as exc:
                            pair["error"] = str(exc)
                        pair["usage"] = judge.recorder.summary()
                        append_jsonl(folder / "pairs.jsonl", pair)
                        judge.recorder.save(
                            folder / f"{case['id']}-{repeat}-{row['variant']}-pair.jsonl"
                        )
    export_blind(rows, folder)
    print("Saved", folder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
