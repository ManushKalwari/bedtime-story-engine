# Design decisions

## A fixed workflow

The assignment requires Python, an LLM judge, a system diagram, and the original model. A small controller and stage functions keep the generation/review loop explicit. Each role uses the same model with different prompts. Safety and quality review run concurrently and join before acceptance.

A graph framework would add a dependency without simplifying this bounded sequence. State transitions and acceptance rules stay in Python; model responses provide content and judgments.

## Safety and quality

Safety returns a boolean and a short reason about the entire story. Unsafe content cannot be offset by a high quality score. The reason is passed to the editor when a correction is needed.

Quality uses six anchored dimensions, quoted evidence, and separate craft observations for resolution and specificity. Word limits are counted locally. Readability estimates and arousal annotations help inspection but do not determine safety or acceptance.

Known response-format mistakes are handled narrowly: unambiguous nested scores can be moved without changing their values, and citations can be aligned to literal source text. Conflicting scores, invented wording, missing required judgments, and unrelated extra fields still fail validation. Optional editorial lists default to empty.

## Editing and rollback

The editor replaces complete paragraphs while leaving other paragraphs unchanged. Grounded setup/payoff pairs are supplied together to preserve connected details. Every candidate is reviewed again under the current request and feedback.

The controller rejects measured regressions in any dimension. Safety repairs take priority, but an edited story still has to pass every final gate. This conservative rule can stop a useful tradeoff, and fixed paragraph counts limit structural rewrites; the paired-refinement experiment exposes these cases.

## Operational limits

API retries, JSON repairs, revisions, call counts, and elapsed time have explicit limits. SDK retries are disabled so attempts are counted once. Failed or incomplete reviews do not become approvals. Previously accepted drafts can survive a later error only if they were assessed under the current requirements.

Traces save usage and validation metadata by default. Full model content is opt-in. Saved artifacts distinguish live generation from scripted demonstrations, and older runs remain readable.

## Next work

Measure judge accuracy and output quality before adding narration, illustrations, or a hosted UI. The existing experiments compare stronger baselines, record failed cases, and expose cost and latency. Repeated generation with the same model is still stochastic, and same-model reviews can share its biases.
