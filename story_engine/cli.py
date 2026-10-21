"""CLI for generation, controlled feedback, inspection, and recorded-run replay."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .config import Settings
from .demo import DemoTransport
from .engine import StoryEngine
from .llm import ModelClient, OpenAITransport
from .reporting import save_run
from .schemas import RunResult, StoryRequest
from .telemetry import EngineError, Recorder

DEMO_REQUEST = "A story about Alice and her best friend Bob, who is a cat, finding a quiet place to watch the moon."


def inspect(result, console):
    table = Table(title=f"{result.provenance.upper()} · review history")
    for heading in ("Draft", "Words", "Safety", "Mean /5", "Kept", "Decision"):
        table.add_column(heading)
    for d in result.drafts:
        a = d.assessment
        table.add_row(
            str(d.version),
            str(a.metrics.word_count),
            str(a.safety.safe),
            f"{a.average():.2f}",
            str(d.retained),
            d.decision,
        )
    console.print(table)
    if result.drafts and result.drafts[-1].assessment.safety.reason:
        console.print(
            f"Latest safety review: {result.drafts[-1].assessment.safety.reason}", markup=False
        )
    console.print(f"Stop: {result.stop_reason}", markup=False)
    console.print(result.usage)


def display(result, console):
    if result.provenance == "synthetic":
        console.print(
            "SYNTHETIC DEMO — scripted text and ratings; not a model-quality result.",
            style="yellow",
        )
    if result.brief and result.brief.parent_note:
        console.print(result.brief.parent_note, markup=False)
    for warning in result.warnings:
        console.print(warning, style="yellow", markup=False)
    chosen = result.selected()
    if chosen:
        console.print("\n" + chosen.story.title, style="bold", markup=False)
        console.print("\n" + chosen.story.body() + "\n", markup=False)
    else:
        console.print(
            "No story met the configured acceptance checks. " + result.stop_reason,
            style="yellow",
            markup=False,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate and inspect bedtime stories using gpt-3.5-turbo."
    )
    parser.add_argument("--request")
    parser.add_argument("--age", type=int, default=7)
    parser.add_argument("--length", choices=["short", "standard"], default="standard")
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument(
        "--trace-content",
        action="store_true",
        help="Opt in to saving full prompts/responses locally",
    )
    parser.add_argument("--demo", action="store_true", help="Fixed synthetic offline example")
    parser.add_argument("--scenario", choices=["improve", "rollback", "fail"], default="improve")
    parser.add_argument("--replay", type=Path, help="Display a saved run.json without API calls")
    args = parser.parse_args(argv)
    console = Console(highlight=False)
    try:
        if args.replay:
            result = RunResult.model_validate_json(args.replay.read_text(encoding="utf-8"))
            console.print("RECORDED RUN — no new generation or evaluation.")
            display(result, console)
            if args.inspect:
                inspect(result, console)
            return 0
        if args.demo and (
            args.request or args.age != 7 or args.length != "standard" or args.interactive
        ):
            raise ValueError(
                "--demo is a fixed age-7 example; omit request/age/length/interactive options"
            )
        settings = Settings.from_env(
            max_revisions=args.max_revisions, max_calls=args.max_calls, max_seconds=args.max_seconds
        )
        request_text = (
            DEMO_REQUEST if args.demo else (args.request or input("What kind of story? ").strip())
        )
        request = StoryRequest(prompt=request_text, age=args.age, length=args.length)
        transport = DemoTransport(args.scenario) if args.demo else OpenAITransport()
        previous, change = None, None
        while True:
            recorder = Recorder(settings, synthetic=transport.synthetic, content=args.trace_content)
            client = ModelClient(transport, recorder)
            console.print("Writing and reviewing…", style="dim")
            result = StoryEngine(client).run(request, previous=previous, change=change)
            folder = save_run(result, recorder, args.output)
            display(result, console)
            console.print(f"Saved: {folder / 'inspect.html'}", markup=False)
            if args.inspect:
                inspect(result, console)
            if not args.interactive:
                return 0 if result.status == "accepted" else 2
            # Commit session state only after acceptance. Failed tweaks never erase the old story.
            if result.status == "accepted":
                previous = result
            while True:
                console.print(
                    "Enter a change, /inspect, /age 5–10, /short, /standard, or /quit.", style="dim"
                )
                command = input("> ").strip()
                if command in {"/quit", "/done"}:
                    return 0
                if command == "/inspect":
                    inspect(result, console)
                    continue
                if not command:
                    continue
                if command.startswith("/age "):
                    try:
                        age = int(command.split()[1])
                    except (ValueError, IndexError):
                        console.print("Use /age followed by a number from 5 to 10.")
                        continue
                    if not 5 <= age <= 10:
                        console.print("Age must be 5–10.")
                        continue
                    command = f"Adapt the story for age {age}."
                elif command == "/short":
                    command = "Make this a short story."
                elif command == "/standard":
                    command = "Use the standard story length."
                elif command.startswith("/"):
                    console.print("Unknown command.")
                    continue
                change = command
                break
    except (EngineError, ValidationError, ValueError, OSError) as exc:
        console.print(str(exc), style="red", markup=False)
        return 1
    except (KeyboardInterrupt, EOFError):
        console.print("\nSession ended.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
