# Evaluation protocol

Live generation has been exercised. Systematic calibration, architecture comparisons, and literary improvement measurements remain unperformed. The included example runs are scripted demonstrations.

## Calibrate the judge

```bash
python -m evals.judge_calibration
python -m evals.judge_calibration --execute --repeats 2
```

The 15 authored cases contain four positive controls and eleven negative examples. They cover unresolved threats, continuity drift, jargon, moralizing, flat narration, unsafe imitation, prompt injection, empty pleasant prose, subtle request violations, and broken setup/payoff links. Positive controls include an earned payoff and a quiet sensory story without conflict.

Reports compare structured review against a holistic judge and show detection by intended defect dimension. Errors remain in the denominator. Word-count failures are excluded from semantic-defect detection so very short examples cannot pass or fail for a trivial reason.

Labels are provisional editorial expectations. These are calibration/development cases, and related principles appear in the judge prompt; they are not an independent held-out benchmark.

## Compare workflow variants

```bash
python -m evals.run_ablation --limit 2 --repeats 1
python -m evals.run_ablation --execute --split dev --limit 4 --repeats 3 --pairwise
python -m evals.run_ablation --execute --split heldout --limit 8 --repeats 3 --pairwise
```

The request set contains 12 development and 8 held-out cases spanning ages, lengths, character constraints, gentle fear, unsafe requests, and prompt injection. Tune on development cases, freeze the prompts, then run the held-out cases once. Retuning after inspecting them makes them development data.

| Variant | Generation |
|---|---|
| `raw` | Original single request, without age instructions |
| `engineered` | Writer instructions and word bounds |
| `planned` | Intake and category plan; technique library disabled |
| `naive_rewrite` | Planned draft, holistic judge, and whole-story rewrites; library disabled |
| `full` | Technique library, independent reviews, targeted edits, and rollback |

The variants differ in several factors, so this is a system comparison rather than an isolated causal test. `engineered` and `planned` are stronger controls than `raw`. Execution order is shuffled per case/repeat.

A fresh audit uses the original request and a reference brief rather than reusing runtime self-scores. Reports include failures and non-emissions in pass/all denominators. Generation, audit, and optional pairwise usage are recorded separately.

Pairwise comparisons use anonymous labels and both presentation orders. Inconsistent votes are reported. Same-model preference can still be biased. Use the generated blind-review packet for your own inspection before opening its answer key.

## Compare editing strategies

```bash
python -m evals.paired_refinement --limit 2
python -m evals.paired_refinement --execute --split dev --limit 4
```

Both strategies receive the same initial story and critique. Compare targeted edits with full rewrites, score changes, constraint regressions, and order-swapped votes. The retention decision is recorded separately, including rejected candidates. This comparison still changes both the editing prompt and its output format.

## Record results

Include the model and prompt version, settings, split, repeats, malformed responses, non-emissions, dimension changes, pairwise inconsistencies, tokens, and latency. Show failures as well as successes. Treat differences on this small dataset as exploratory, and assess improvement against the stronger baselines.

Commands default to a dry run. `--execute` requires `OPENAI_API_KEY` and makes billable calls. Optional `STORY_INPUT_USD_PER_MILLION` and `STORY_OUTPUT_USD_PER_MILLION` enable cost estimates; missing usage means incomplete accounting. Traces save model content for reproducibility, so review artifacts before sharing.
