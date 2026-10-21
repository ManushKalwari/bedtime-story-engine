from types import SimpleNamespace

import pytest

from evals.common import compare_pair
from evals.run_ablation import summarize
from story_engine.cli import main
from story_engine.engine import StoryEngine
from story_engine.reporting import save_run
from story_engine.schemas import PairVerdict, RunResult, Story


@pytest.mark.parametrize(
    "votes,expected",
    [
        (["A", "B"], "left"),
        (["B", "A"], "right"),
        (["A", "A"], "inconsistent"),
        (["tie", "tie"], "tie"),
    ],
)
def test_pairwise_order_mapping(request_data, votes, expected):
    responses = iter(votes)
    client = SimpleNamespace(
        structured=lambda *a, **k: PairVerdict(
            winner=next(responses), explanation="A concise comparison."
        )
    )
    story = Story(title="Moon", paragraphs=["A quiet evening."])
    assert compare_pair(client, request_data, story, story)["winner"] == expected


def test_failed_cases_stay_in_denominator(tmp_path):
    base = dict(
        variant="full", generation_usage=dict(input_tokens=0, output_tokens=0, elapsed_seconds=1)
    )
    rows = [
        {**base, "emitted": True, "audit": {"valid": True}, "audit_pass": True},
        {**base, "emitted": False},
    ]
    path = tmp_path / "report.md"
    summarize(rows, path)
    assert "50.0% (1/2)" in path.read_text()
    assert "100.0% (1/1)" in path.read_text()


def test_inspector_escapes_text_and_run_roundtrip(client, request_data, tmp_path):
    result = StoryEngine(client).run(request_data)
    result.request.prompt = "<script>alert(1)</script>"
    folder = save_run(result, client.recorder, tmp_path)
    page = (folder / "inspect.html").read_text()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    restored = RunResult.model_validate_json((folder / "run.json").read_text())
    assert restored.selected().story == result.selected().story
    assert (folder / "story.txt").exists()


def test_cli_failure_has_no_story_artifact(tmp_path):
    assert main(["--demo", "--scenario", "fail", "--output", str(tmp_path)]) == 2
    assert list(tmp_path.glob("*/run.json"))
    assert not list(tmp_path.glob("*/story.txt"))
