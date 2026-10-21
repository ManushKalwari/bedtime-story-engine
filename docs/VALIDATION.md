# Validation

## Partial length-repair regression

Inspected local run `d87b5d6004b8`: 173 words became 220 against a 300–450 range,
but the controller counted one failed constraint in both drafts and stopped as a
plateau. The controller now measures distance from the word range as well as
failure count. Progress can use a remaining revision; moving farther away is a
regression. Existing safety and rubric-regression checks still apply, and a draft
outside the range remains ineligible for output. Budgets and revision limits are
unchanged. Twenty-five focused engine tests and changed-file lint/format checks
passed. Rechecking the saved assessments retains draft 1 under this rule. No live
API calls were made for this fix; the judge's inflated ratings remain unresolved.

## Targeted length and judge checks

Prompt version `1.3.7` was checked with 32 focused offline tests covering craft,
length guidance, calibration fixtures, revision, and rollback. Ruff lint and format
checks passed for the changed Python files. The complete offline suite was not rerun.
The complete judge example validates against the live schema and all eight quotes
match its example story exactly.

A bounded live `gpt-3.5-turbo` run of the age-5 Moria request produced a 284-word
draft, then a 355-word revision, repairing the 300–450-word constraint. See local
`runs/dd138d5ce48f`. This establishes one successful length repair, not consistent
age adaptation or story quality: the accepted text still had abstract language and
near-repeated passages, while the judge awarded every dimension 5.

Reassessing the earlier 255-word failure first exhausted quote repair. After adding
a complete JSON calibration example, a second reassessment returned valid JSON
but again awarded every dimension 5 (`runs/2c36ed4d9d68`). Thus the prompt changes
have **not established reliable judge calibration**. Two additional provisional
cases isolate missed building and ornate age-5 language; the full live calibration
suite has not been run. No acceptance thresholds were weakened.

## Earlier full-suite baseline

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
