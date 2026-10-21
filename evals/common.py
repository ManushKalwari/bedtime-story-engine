import json
import random
from importlib.resources import files
from pathlib import Path

from story_engine import agents
from story_engine.config import Settings, word_bounds
from story_engine.engine import StoryEngine
from story_engine.llm import ModelClient, OpenAITransport
from story_engine.schemas import Brief, HolisticVerdict, PairVerdict, Story
from story_engine.telemetry import Recorder

VARIANTS = ("raw", "engineered", "planned", "naive_rewrite", "full")


def load_data(name):
    return json.loads(files("evals").joinpath("data", name).read_text(encoding="utf-8"))


def make_client(settings=None, *, content=True):
    settings = settings or Settings.from_env()
    return ModelClient(OpenAITransport(), Recorder(settings, content=content))


def reference_brief(case):
    return Brief(
        premise=case.get("safe_premise", case["prompt"]),
        category=case["category"],
        age=case["age"],
        length=case.get("length", "standard"),
        constraints=case.get("constraints", []),
        decision="reframe" if "safe_premise" in case else "allow",
        parent_note="Use a gentle version of the requested theme."
        if "safe_premise" in case
        else "",
    )


def generate_variant(client, request, variant):
    """Returns candidate, emitted flag, metadata. Baselines are explicitly unverified."""
    if variant == "full":
        result = StoryEngine(client).run(request)
        selected = result.selected()
        return selected.story if selected else None, bool(selected), result.model_dump()
    if variant == "raw":
        text = client.call(
            "baseline.raw",
            [{"role": "user", "content": request.prompt}],
            temperature=0.1,
            max_tokens=3000,
            json_mode=False,
        )
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Baseline text is preserved; no age/safety instructions are silently added.
        return (
            Story(title="Raw skeleton output", paragraphs=paragraphs),
            True,
            {"verification": "none"},
        )
    if variant == "engineered":
        story = client.structured(
            "baseline.engineered",
            agents.prompt("writer"),
            {
                "request": request.model_dump(),
                "body_word_range": word_bounds(request.age, request.length),
            },
            Story,
            temperature=client.settings.writer_temperature,
        )
        return story, True, {"verification": "none"}
    brief = agents.intake(client, request, [])
    if brief.decision == "decline":
        return None, False, {"brief": brief.model_dump(), "reason": "declined"}
    blueprint = agents.plan(client, brief, use_techniques=False)
    story = agents.write(client, brief, blueprint, use_techniques=False)
    initial = story.model_dump()
    if variant == "naive_rewrite":
        for _ in range(client.settings.max_revisions):
            verdict = client.structured(
                "baseline.holistic",
                "Rate the bedtime story from 1 to 10 and give feedback. Return JSON.",
                {"request": request.model_dump(), "story": story.model_dump()},
                HolisticVerdict,
            )
            if verdict.score >= 8:
                break
            story = client.structured(
                "baseline.rewrite",
                "Rewrite the whole story to improve it using the feedback. Return JSON title and paragraphs.",
                {
                    "story": story.model_dump(),
                    "feedback": verdict.feedback,
                    "request": request.model_dump(),
                },
                Story,
                temperature=0.45,
            )
    return (
        story,
        True,
        {
            "brief": brief.model_dump(),
            "blueprint": blueprint.model_dump(),
            "initial_story": initial,
            "verification": "not acceptance-gated",
        },
    )


def compare_pair(client, request, left, right):
    """Order-swapped judgments; contradictory votes are reported, never forced into a win."""

    def judge(a, b):
        return client.structured(
            "eval.pairwise",
            agents.prompt("pairwise"),
            {
                "request": request.model_dump(),
                "A": a.model_dump(),
                "B": b.model_dump(),
            },
            PairVerdict,
            temperature=0,
        )

    first, second = judge(left, right), judge(right, left)
    first_vote = {"A": "left", "B": "right", "tie": "tie"}[first.winner]
    second_vote = {"A": "right", "B": "left", "tie": "tie"}[second.winner]
    return {
        "winner": first_vote if first_vote == second_vote else "inconsistent",
        "order_consistent": first_vote == second_vote,
        "forward": first.model_dump(),
        "reverse": second.model_dump(),
    }


def append_jsonl(path, row):
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def percent(n, d):
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def export_blind(rows, folder, seed=41):
    """Create manual comparison packets; the answer key is a separate file."""
    rng = random.Random(seed)
    groups = {}
    for row in rows:
        if row.get("story"):
            groups.setdefault((row["case_id"], row["repeat"]), []).append(row)
    keys, sheets = [], []
    for (case_id, repeat), group in groups.items():
        rng.shuffle(group)
        for index, row in enumerate(group):
            label = f"{case_id}-r{repeat}-{index + 1}"
            story = Story.model_validate(row["story"])
            keys.append(
                {"blind_id": label, "variant": row["variant"], "case_id": case_id, "repeat": repeat}
            )
            sheets.append(
                f"## {label}\n\nRequest: {row['request']['prompt']}\n\n"
                f"Age: {row['request']['age']}\n\n{story.title}\n\n{story.body()}\n\n"
                "Your notes / preference / constraint failures: __________\n"
            )
    (folder / "blind_review.md").write_text(
        "# Manual review packet\n\n"
        "Review these yourself. Baseline outputs may be unsuitable; this packet is for adult engineering review. "
        "Do not inspect blind_key.json until after recording judgments.\n\n" + "\n".join(sheets),
        encoding="utf-8",
    )
    (folder / "blind_key.json").write_text(json.dumps(keys, indent=2), encoding="utf-8")
