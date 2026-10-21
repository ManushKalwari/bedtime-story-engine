# Validation

Checked October 21, 2026, on Windows with Python 3.12.7 in the workspace `.venv312` environment.

| Check | Result |
|---|---|
| Offline unit tests | 143 passed |
| Ruff lint | Passed |
| Ruff format check | Passed; 30 Python files formatted |
| `python -m story_engine --demo --inspect` | Passed from outside the source folder |
| `python main.py --demo --inspect` | Passed from outside the source folder |
| Installed `bedtime --demo --inspect` | Passed from outside the source folder |
| Historical saved-run replay | Passed |
| Calibration, architecture, and paired-refinement dry runs | Passed without API calls |
| Local documentation links | Passed |
| API-key pattern scan of project text files | No matching values remain |

## Coverage

Tests cover input contracts, structured-output repair, strict score types, nested-score normalization and conflicts, optional fields, quote grounding, ambiguous references, linked setup/payoff evidence, chart alignment, length metrics, safety vetoes, rollback, feedback reevaluation, budgets, transport errors, HTML escaping, and saved-run roundtrips.

The API contract is exercised through the real SDK with mocked HTTP responses. Ordinary tests remove the API key and block socket connections. Scripted fixtures demonstrate controller behavior rather than model quality.

The cleanup kept generation prompts and acceptance policies intact, separated review validation from LLM-stage functions, consolidated the entry points, and removed duplicate source/documentation files. The original assignment is retained in `ASSIGNMENT.md`. Generated build and packaging directories remain ignored; automatic approval review blocked recursive deletion of those folders.

## Remaining evaluation

Live generation has been exercised in the user's local runs. No live API calls were made during this cleanup. Systematic judge calibration, comparative story-quality measurements, and hosted CI remain unverified. Quote grounding establishes that text exists, not that the model's interpretation is sound. Same-model ratings can be biased.
