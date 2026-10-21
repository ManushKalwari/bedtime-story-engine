# Bedtime Story Engine

A Python app that turns a bedtime story request into a story for ages 5-10. It uses `gpt-3.5-turbo` to plan, write, review, and revise each story. An interactive mode lets you request changes after reading it.

## Setup

Requires Python 3.10 or later. Run these commands from the folder containing `pyproject.toml`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Open `.env` and replace `replace_locally` with your own OpenAI API key. The app loads this file automatically. A key already set in your terminal takes precedence. `.env` is excluded from Git.

On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`, and `cp .env.example .env`.

## Run a story

```powershell
.\.venv\Scripts\python.exe -m story_engine --request "Alice and her best friend Bob, a cat, discover a garden on the moon" --age 7 --interactive --inspect
```

| Option | Purpose |
|---|---|
| `--age 5` through `--age 10` | Set the listener's age; default is 7 |
| `--length short` | Request a shorter story; default is `standard` |
| `--interactive` | Ask for changes after each story |
| `--inspect` | Save a local HTML page with drafts and reviews |
| `--trace-content` | Include full prompts and responses in the saved trace |

In interactive mode, type a change such as "Make Bob a little funnier." You can also use `/age 5`, `/short`, `/standard`, `/inspect`, or `/quit`.

To try the app without an API key, run the fixed offline demo:

```powershell
.\.venv\Scripts\python.exe -m story_engine --demo --inspect
```

`main.py` also runs the same app. The model remains `gpt-3.5-turbo`, as required by the assignment.

## How it works

1. **Understand the request.** Identify characters, requirements, and a category: friendship, wonder, comfort, whimsy, or sensory.
2. **Plan and write.** Plan the character's goal, connected events, and ending. Select storytelling techniques for the category and write for the requested age.
3. **Review and revise.** Separate LLM reviews assess safety and story quality. Python checks word count and controls revisions. Edits preserve connected details and payoffs.
4. **Save the result.** Return a story that passes the checks and save its draft history, reviews, token usage, and timing.

The default limit is two revisions and 24 API attempts per turn. Use `--max-revisions`, `--max-calls`, or `--max-seconds` to adjust the limits.

See the [system diagram](docs/ARCHITECTURE.md) for the flow between the user, writer, reviewers, and revision controller.

### Saved runs

Each run is saved under `runs/<run-id>/`:

| File | Contents |
|---|---|
| `story.txt` | The accepted story, when one passes review |
| `run.json` | Request, plan, drafts, reviews, and usage totals |
| `trace.jsonl` | Model calls, token counts, call durations, and errors |
| `inspect.html` | Draft comparison and review details, when requested |

Token totals and elapsed time also appear in the terminal. Optional pricing variables in `.env.example` enable cost estimates. Saved runs contain story and request text; `--trace-content` additionally records prompts and responses. The `runs/` folder is excluded from Git.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Tests run offline. Evaluation scripts cover judge calibration, workflow comparisons, and before/after story reviews. They show a preview by default; `--execute` makes API calls. See [evaluation instructions](docs/EXPERIMENTS.md).

| Location | Contents |
|---|---|
| `story_engine/prompts/` | Instructions for planning, writing, reviewing, and editing |
| `story_engine/techniques.py` | Storytelling technique library |
| `story_engine/agents.py` | Inputs and outputs for each LLM task |
| `story_engine/engine.py` | Revision and acceptance logic |
| `story_engine/llm.py`, `telemetry.py` | API access, retries, usage, and timing |
| `tests/`, `evals/` | Tests and evaluation scripts |

## Documentation

- [Assignment](docs/ASSIGNMENT.md)
- [Design decisions](docs/DECISIONS.md)
- [Storytelling techniques](docs/STORYTELLING.md)
- [Review criteria](docs/RUBRIC.md)
- [Validation results](docs/VALIDATION.md)

## With two more hours

I would start with a small personalization and feedback prototype:

1. **Ask what the child enjoys.** Offer an optional choice of interests, such as silly comedy, fairy tales, or anime-inspired adventures. A research agent could suggest techniques from relevant authors and genres for use in original stories, keeping the language appropriate for the child's age and the ending calm.
2. **Learn from feedback.** Collect an optional rating and a favorite moment, with a caregiver's help where appropriate. With permission, maintain an editable preference summary. Over 10-15 stories, look for patterns in preferred characters, humor, pacing, and themes. Families could review, reset, or delete these preferences.
3. **Keep longer sessions consistent.** Track the current request, feedback, confirmed preferences, and last accepted story explicitly. As history grows, retrieve relevant preferences and story details. Cache reusable research separately to reduce repeated work and token use.

Within the two-hour window, I would prioritize the preference question, feedback capture, and comparison with human ratings. Retrieval and caching would follow, with quality, latency, and token usage guiding further changes. The same priorities are outlined in `main.py`.
