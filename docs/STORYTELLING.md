# Storytelling techniques

The writer receives a small library selection to help turn a pleasant premise into
specific actions, discoveries, and payoffs. These are original craft examples, not
author imitation prompts or adaptations of existing stories. Their effectiveness
with the required model still needs live evaluation.

## Prompting the required model

The model remains `gpt-3.5-turbo` for every generation and review call. We use
explicit tasks, separated system instructions and JSON input, schema descriptions,
and short examples of language and scoring. These choices follow the general
[OpenAI prompting guidance](https://developers.openai.com/api/docs/guides/prompt-engineering),
which recommends explicit instructions for GPT models and diverse input/output
examples. This is general guidance, not a measured GPT-3.5-specific performance claim.
GPT-3.5 Turbo does not support schema-enforced
[Structured Outputs](https://developers.openai.com/api/docs/models/gpt-3.5-turbo);
the application retains JSON mode, Python validation, and bounded repairs.

The writer receives a target near the middle of the permitted body word range.
The editor receives the actual current count and calculated minimum addition or
removal, even when the judge supplies perfect ratings and no fixes. Its target
applies to the complete patched story. Expansion should add connected actions,
not harder vocabulary. These targets are guidance; code still enforces the original
word bounds. A later controller fix recognizes reduced distance from that range
as revision progress, while keeping out-of-range drafts ineligible. Safety and
rubric regressions still block retention, and revision/call limits still apply.

Judge examples contrast a missed requested action, age-inappropriate language,
and a concrete earned outcome. Safety and calmness do not imply high fidelity or
age fit. Prompt version `1.3.7` identifies these changes in new traces. Targeted
offline checks validate integration and call counts; they cannot establish honest
model scoring or consistent story quality. Claims about tipping a model or large
percentage gains in the supplied article have not been adopted as requirements.

Version `1.3.8` adds a listener perspective to the writer and judge: imagine an
adult reading aloud to the exact age in `brief.age`. The writer checks whether
the listener can picture the events and follow the character's goal and outcome.
The judge cites language that would require extra explanation, or demonstrates
clarity when no such problem is present. This is an editorial estimate, not child
role-play or measured child comprehension. It adds no calls, output fields, or
acceptance gates; its effect on live judge accuracy remains unverified.

## Catalog

The authoritative records are in `story_engine/techniques.py`. Each immutable
record includes a stable ID, purpose, instructions, guidance for ages 5–7 and
8–10, a compact application for short stories, pitfalls, and an original example.

| ID | Technique | What to do | Avoid |
|---|---|---|---|
| `repetition_with_variation` | Repetition with variation | Repeat a brief image or phrase, changing it meaningfully before a quiet final appearance. | Filler, forced rhyme, or a lively final refrain. |
| `three_gentle_attempts` | Three gentle attempts | Let each manageable attempt teach something used in the next. | Unrelated mishaps, escalating danger, or an unexplained rescue. |
| `setup_and_payoff` | Setup and payoff | Introduce a detail naturally, then let a character use it later. | Last-minute objects and coincidences that solve everything. |
| `distinctive_character_behavior` | Distinctive character behavior | Show a habit that affects events and allows an affectionate return or small adjustment. | Trait labels, ridicule, or compulsory personality changes. |
| `discovery_through_action` | Discovery through action | Let a safe action and observation answer a concrete curiosity. | Lectures, unsafe experiments, and invented science presented as fact. |
| `emotional_return` | Emotional return | Revisit an opening image after a caring action or discovery changes its meaning. | Stated morals, erased grief, and promises of perfect happiness. |

### Original example sketches

- **Repetition with variation:** Neri counts “one more little light” at the gate
  and kitchen window. From bed, a firefly becomes “one last little light” before
  drifting away. The refrain moves from an active search toward rest.
- **Three gentle attempts:** Pella the cloud folds an oversized blanket, then
  rolls it. Its dangling corners and unfolding roll lead her to notice how well
  it fits the hill. She tucks it around the hill and rests above it.
- **Setup and payoff:** Ivo pockets a loose thread before entering the moon
  garden. Later, he and his aunt use it to support a leaning moonflower.
- **Distinctive character behavior:** Tavi sorts pebbles by size. When his
  friend's leaves refuse to form a tidy row, he uses their different sizes to
  make a snug bed. He still keeps one pebble just where he likes it.
- **Discovery through action:** With Dad nearby, Uma moves a battery lantern
  farther from a paper rabbit and sees its shadow shrink. She moves it back to
  check, then leaves a small rabbit shadow resting on the wall.
- **Emotional return:** Fen sits alone in a chair that feels too wide. He offers
  a corner of his blanket to his sister. The same chair eventually holds two
  sleepy shoulders under one blanket.

For ages 5–7, favor visible actions, concrete changes, and direct connections.
For ages 8–10, allow subtler humor, revised guesses, and mixed feelings. Short
guidance compresses the mechanism without removing the quiet landing; three
attempts can each occupy a single compact action and result. None requires dialogue.

## Selection and integration

`select_techniques(category, age, length)` accepts values from a validated brief
and returns fresh JSON-ready dictionaries. Selection is deterministic:

| Category | First technique | Second technique |
|---|---|---|
| Friendship | Distinctive character behavior | Emotional return |
| Wonder | Discovery through action | Setup and payoff |
| Comfort | Emotional return | Repetition with variation |
| Whimsy | Three gentle attempts | Distinctive character behavior |
| Sensory | Repetition with variation | Emotional return |

Standard stories receive both techniques in this order. Short stories receive
only the first, including its compact guidance. Age guidance is selected at the
7/8 boundary. Each returned item includes the mechanism and its example; editing
the returned dictionaries does not change the catalog.

`agents.write(..., use_techniques=True)` adds `storytelling_techniques` to the
existing writer payload. Set `use_techniques=False` to omit this field.

The writer applies the mechanism to the user's own premise and invents fresh
characters, objects, and wording. The brief, blueprint, safety, age, word bounds,
and quiet ending take priority. The editor preserves connected setups, payoffs,
character habits, and meaningful refrains where current requirements permit.
These instructions guide generation; they do not add acceptance gates or API calls.

## Evaluation boundary

`planned` and `naive_rewrite` explicitly disable techniques. `raw` and `engineered`
do not receive the catalog. `full` enables it through the normal engine path.
The architecture comparison now changes technique guidance as well as review and
revision behavior; it cannot isolate the library's contribution. Shared writer
prompt edits also mean historical baselines are not byte-identical to new runs.

Offline tests check category/age/length selection, request serialization, opt-out
controls, output contracts, and unchanged call counts. They do not show that the
generated stories are better. Live generation and judge calibration require an
API key and are not part of the offline evidence.

## Planner and judge integration

The planner now receives the same selected techniques as the writer and always
produces `craft.character_desire`, `craft.distinctive_behavior`, `craft.setup`, and
`craft.payoff`. It must place the setup and payoff in the causal beats and use a
payoff appropriate to the category. New planner output uses `PlannedBlueprint`,
which requires craft; historical `Blueprint` objects may omit it.

New quality output uses `GroundedQualityReview`, requiring evidence for resolution
and specificity plus an optional grounded setup/payoff pair. Historical
`QualityReview` objects may omit craft. The editor receives the identified pair
from the current story, rather than treating an unfulfilled plan as proof that a
detail exists. On feedback turns the old blueprint is not supplied as a new
requirement; the current brief and actual story govern editing.

See [RUBRIC.md](RUBRIC.md) for evidence and preservation rules and
[EXPERIMENTS.md](EXPERIMENTS.md) for the expanded calibration fixtures. The
`planned` and `naive_rewrite` controls disable the library at both planner and
writer stages, but still use the strengthened planner prompt and craft schema.
