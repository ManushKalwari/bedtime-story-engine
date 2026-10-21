# Bedtime Story Engine

Generate and revise bedtime stories for ages 5-10 using `gpt-3.5-turbo`, the model required by the [assignment](docs/ASSIGNMENT.md).

The workflow classifies a request, plans an arc, writes a story, and reviews safety and quality independently. Python enforces word limits and decides whether to accept, revise, or retain a previous draft. Feedback can change an accepted story without discarding the parts that still work.

## Setup

Run these commands from the project folder containing `pyproject.toml`.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m story_engine --demo --inspect
```

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` for the equivalent commands. The editable install picks up later source changes. The demo uses fixed responses and needs no API key.

For live generation, copy the example once, then open `.env` and replace
`replace_locally` with your own API key. On macOS/Linux, use `cp .env.example .env`.

```powershell
Copy-Item .env.example .env
# Edit .env before running the next command.
.\.venv\Scripts\python.exe -m story_engine --request "Alice and her best friend Bob, a cat, discover a garden on the moon" --age 7 --interactive --inspect --trace-content
```

The app automatically loads `.env` from the current directory, falling back to the
source checkout when using an editable install. Existing terminal variables take
precedence. `.env` is ignored by Git; `.env.example` contains placeholders only.
For CI or deployment, supply environment variables through the platform's secret
settings; set `PYTHON_DOTENV_DISABLED=1` to disable local file loading.

`bedtime`, `python -m story_engine`, and `python main.py` use the same CLI when run in the installed environment. The model is fixed in `story_engine/config.py`; unavailable model access is reported as an error.

## Usage

```bash
python -m story_engine --request 'A fox finds a quiet place to rest.' --age 6 --length short
python -m story_engine --demo --scenario rollback --inspect
python -m story_engine --replay examples/synthetic-improvement/run.json --inspect
```

Interactive commands are `/inspect`, `/age 5` through `/age 10`, `/short`, `/standard`, and `/quit`. Type a natural-language request to change the story. Up to six feedback turns are supported. A failed change leaves the last accepted story available.

Defaults are two revisions, 24 API attempts per turn, a 180-second overall budget, and a 40-second request timeout. Set `--max-revisions`, `--max-calls`, and `--max-seconds` to change the first three limits. Exit codes are 0 for success, 1 for setup errors, and 2 when no story passes review. Timeouts bound API calls rather than forcibly terminating the process.

Each run saves:

| File | Contents |
|---|---|
| `story.txt` | Accepted story; absent when nothing passes |
| `run.json` | Request, plan, assessed drafts, decisions, and usage |
| `trace.jsonl` | Stages, timing, token usage, validation events, and prompt version |
| `inspect.html` | Local review page with scores, reasons, and draft history |

`--trace-content` also saves full prompts, responses, and detailed validation errors. Run files contain request and story text even without that flag. `.env.example` lists supported environment variables, which can also be loaded from your local `.env`. Cost estimates require both optional token-price variables.

## Code and documentation

| Location | Responsibility |
|---|---|
| `story_engine/engine.py` | Acceptance, revision limits, and rollback |
| `story_engine/agents.py`, `prompts/` | LLM stages and instructions |
| `story_engine/review_validation.py` | Citation grounding and review validation |
| `story_engine/schemas.py`, `metrics.py` | Data contracts, word counts, and readability diagnostics |
| `story_engine/techniques.py` | Six storytelling techniques and category selection |
| `story_engine/llm.py`, `telemetry.py` | API calls, retries, budgets, and traces |
| `story_engine/cli.py`, `reporting.py` | Interactive CLI, saved-run replay, and HTML inspection |
| `evals/`, `tests/` | Evaluation tools and offline tests |

See the [architecture diagram](docs/ARCHITECTURE.md), [design decisions](docs/DECISIONS.md), [review rubric](docs/RUBRIC.md), [technique catalog](docs/STORYTELLING.md), and [validation results](docs/VALIDATION.md).

## Checks and evaluation

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m evals.judge_calibration
python -m evals.run_ablation --limit 2
python -m evals.paired_refinement --limit 2
```

Tests run offline. Evaluation commands default to a dry run; add `--execute` to make API calls. See [EXPERIMENTS.md](docs/EXPERIMENTS.md) for comparisons and reporting.

Live generation has been exercised, but systematic judge accuracy and story-quality improvements have not been measured. Scores and readability estimates remain useful diagnostics rather than guarantees.

With two more hours, I would explore personalization through an optional question about the child's interests: silly comedy, fairy tales, or anime-inspired adventures. A research agent could suggest techniques from authors in the chosen genre for the planner to use in an original story, while preserving age suitability and a calm ending. I would compare the results with the current workflow to assess whether the extra steps help.
