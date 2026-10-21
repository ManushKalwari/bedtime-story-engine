# Review policy

The scoring anchors are in `story_engine/prompts/quality.md`. Scores are ordinal integers from 1 to 5.

| Dimension | Question | Minimum |
|---|---|---:|
| Age fit | Can this age follow the language and action? | 4 |
| Coherence | Do events connect with an earned resolution or quiet landing? | 3 |
| Fidelity | Are the request and current feedback honored? | 4 |
| Warmth | Are care and sensory details specific to this story? | 3 |
| Bedtime calm | Are tensions resolved before a settled ending? | 4 |
| Cadence | Does the story read aloud naturally? | 3 |

Acceptance requires a safe verdict, no word-count failures, and every dimension at its threshold. The average score is for inspection only. Thresholds are product choices rather than validated developmental standards.

## Safety

The live reviewer returns exactly `safe` and `reason`: a strict JSON boolean and one nonempty sentence of at most 400 characters. It assesses the entire story for inappropriate content, sustained threats, cruelty, and dangerous imitable actions. Harmless fantasy, sadness, and warnings about danger are considered in context.

An unsafe reason identifies the problem and needed change. It is passed to the editor as a concern. Safety does not require a quote. Missing or malformed verdicts/reasons still fail after bounded repair. Historical safety evidence remains readable in saved runs.

## Quality evidence

Each dimension has a score, a literal quote, its 1-based paragraph number, and an observation. The score belongs beside the evidence object. Quality also requires `craft.resolution` and `craft.specificity` evidence. Missing story elements should be explained using a passage where they were needed, with an appropriate lower score.

`craft.setup_payoff` is optional. When supplied, both quotes must be grounded and the setup must precede the payoff. The editor receives that pair together. Omission means no connection was identified; it does not establish that none exists.

Pleasant events without meaningful progression and broken setup/payoff links should score at most 2 for coherence. Generic positive adjectives without concrete care or meaningful detail should score at most 2 for warmth. Missing a meaningful request constraint caps fidelity at 3. These are judge instructions; Python validates the response structure and evidence rather than independently deciding literary merit.

## Response normalization

- A misplaced nested dimension score is moved to the proper location unchanged. Identical duplicates are removed; conflicting values or types are rejected. Unused craft-note scores are discarded.
- ASCII capitalization can be restored from the source. A trailing ellipsis can be removed only when the remaining quote matches literal text. Internal omissions and paraphrases are rejected.
- A paragraph reference can be corrected only when the quote uniquely identifies another paragraph. An existing match in the supplied paragraph takes precedence.
- `preserve` and `fixes` default to empty lists. Scores and required craft judgments never receive defaults.

Normalized quotes stored in the assessment are exact source substrings. Raw responses remain in content traces. Grounding proves that the passage exists, not that the model interpreted it correctly. Direct verification of saved editor anchors stays strict.

## Length and diagnostics

Body word counts exclude the title.

| Age | Short | Standard |
|---|---|---|
| 5-7 | 120-220 | 300-450 |
| 8-10 | 200-350 | 500-750 |

The counter uses an English-oriented regex. Sentence length, dialogue fraction, repeated paragraphs, lexical flags, and approximate Flesch-Kincaid grade are diagnostics only.

Arousal ratings are optional chart metadata, from 1 (still) to 5 (intense). If the count does not match the story's paragraphs, the whole curve is omitted with a warning. Ratings are not truncated or invented, and a chart alignment error does not block the story.
