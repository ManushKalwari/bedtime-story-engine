"""Original craft examples and bounded, deterministic guidance for the writer."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .schemas import Category


@dataclass(frozen=True)
class Technique:
    id: str
    name: str
    purpose: str
    instructions: str
    younger: str
    older: str
    short: str
    pitfalls: str
    example: str


TECHNIQUES = MappingProxyType(
    {
        t.id: t
        for t in (
            Technique(
                id="repetition_with_variation",
                name="Repetition with variation",
                purpose="Make a familiar rhythm gain meaning as the story settles.",
                instructions="Repeat a brief image or phrase with a concrete change each time; "
                "let its last appearance express arrival or rest. Narration can carry the refrain.",
                younger="Use two or three concrete variations with easy-to-follow wording.",
                older="Let the final variation reveal a small change in the character's outlook.",
                short="Use just two appearances: introduce the phrase, then quietly transform it.",
                pitfalls="Avoid filler, forced rhyme, mandatory spoken dialogue, or a refrain "
                "that keeps the ending lively.",
                example="One more little light: Neri counted the lantern by the gate. "
                "One more little light: the kitchen window glowed. From bed, Neri saw a "
                "firefly pause outside the screen. One last little light. Then it drifted away.",
            ),
            Technique(
                id="three_gentle_attempts",
                name="Three gentle attempts",
                purpose="Build causal progression through three different, manageable tries.",
                instructions="Give the character a small goal. Each attempt reveals something "
                "that helps the next; the third uses what was learned, then the story settles.",
                younger="Keep one concrete goal and make each result immediately visible.",
                older="Allow gentle humor and let the final attempt reframe the original goal.",
                short="Give each attempt one compact action and result; leave room for rest.",
                pitfalls="Avoid three unrelated mishaps, rising danger, humiliation, or a "
                "solution supplied by an unexplained new helper.",
                example="Pella the cloud folded her blanket, but its corners hung down. "
                "She rolled it, but the roll slipped open. Seeing how neatly it followed "
                "the hillside, she tucked its edges around the hill. The blanket stayed. "
                "Pella rested above the warm, rounded shape.",
            ),
            Technique(
                id="setup_and_payoff",
                name="Setup and payoff",
                purpose="Make an early detail become meaningfully useful later.",
                instructions="Introduce an ordinary object, habit, or observation naturally. "
                "Bring it back when a character can use it to contribute to the resolution.",
                younger="Keep the early detail visible and show a direct, concrete use later.",
                older="Make the later use unexpected but understandable from the setup.",
                short="Use one detail, one later use, and no extra subplot.",
                pitfalls="Avoid a last-minute object, a coincidence that solves everything, "
                "or an explanatory moral after the payoff.",
                example="Ivo tucked a loose thread into his pocket before following Aunt "
                "Seli into the moon garden. A moonflower leaned away from its little stake. "
                "Ivo remembered the thread. Together they tied a soft, loose loop around "
                "the stem, and its pale cup faced the light again.",
            ),
            Technique(
                id="distinctive_character_behavior",
                name="Distinctive character behavior",
                purpose="Show personality through a habit that influences what happens.",
                instructions="Choose one specific behavior. Show it in action, let it affect "
                "a gentle problem or discovery, and allow a small adjustment or affectionate return.",
                younger="Use an easily pictured habit and make its effect clear.",
                older="Let the habit have both a useful side and a gently comic limitation.",
                short="Show the habit once, then let it matter in one later action.",
                pitfalls="Avoid merely naming a trait, mocking a difference, or making a "
                "character abandon their personality to deserve friendship.",
                example="Tavi the hedgehog sorted every pebble by size. His friend's little "
                "nest of leaves refused to form a tidy row. Tavi tried the largest leaf "
                "underneath and tucked the smaller ones around it. The untidy pile became "
                "a snug bed. He set one smooth pebble beside it, just where he liked it.",
            ),
            Technique(
                id="discovery_through_action",
                name="Discovery through action",
                purpose="Turn curiosity into a discovery the character helps make.",
                instructions="Start with a concrete question or curiosity. Let the character "
                "try a safe, small action, notice its effect, and change their understanding.",
                younger="Use one observable action and result, with concrete sensory language.",
                older="Allow a second observation to refine the character's first guess.",
                short="Keep one question, one safe experiment, and one quiet discovery.",
                pitfalls="Avoid passive lectures, unsafe experiments, or treating invented "
                "fantasy explanations as real-world scientific facts.",
                example="Uma wondered why her paper rabbit cast such a tall shadow. "
                "With Dad beside her, she moved the battery lantern farther from the rabbit. "
                "The shadow grew smaller. She moved it back and watched the long ears "
                "stretch again, then left a small rabbit resting on the wall.",
            ),
            Technique(
                id="emotional_return",
                name="Emotional return",
                purpose="Let an opening image feel different after a small emotional change.",
                instructions="Establish a concrete image linked to a feeling. After a caring "
                "action or discovery, return to that image with a small visible difference.",
                younger="Show the feeling through a clear action and a comforting final image.",
                older="Allow mixed feelings to remain; show connection without claiming "
                "every worry or sadness has disappeared.",
                short="Use one opening image and one changed return, linked by a caring action.",
                pitfalls="Avoid announcing the lesson, erasing grief, promising perfect "
                "happiness, or adding a new adventure at the close.",
                example="The chair beside Fen's window looked too wide when he sat alone. "
                "He carried a corner of his blanket to his sister, who put down her book "
                "and came to sit with him. Later, the same wide chair held two sleepy "
                "shoulders beneath one blanket.",
            ),
        )
    }
)

_CATEGORY_TECHNIQUES = MappingProxyType(
    {
        "friendship": ("distinctive_character_behavior", "emotional_return"),
        "wonder": ("discovery_through_action", "setup_and_payoff"),
        "comfort": ("emotional_return", "repetition_with_variation"),
        "whimsy": ("three_gentle_attempts", "distinctive_character_behavior"),
        "sensory": ("repetition_with_variation", "emotional_return"),
    }
)


def select_techniques(
    category: Category, age: int, length: Literal["short", "standard"]
) -> list[dict[str, str]]:
    """Return fresh JSON-ready guidance for a validated story brief; no model calls."""
    ids = _CATEGORY_TECHNIQUES[category]
    if length == "short":
        ids = ids[:1]
    guidance = []
    for technique_id in ids:
        technique = TECHNIQUES[technique_id]
        item = {
            "id": technique.id,
            "name": technique.name,
            "purpose": technique.purpose,
            "instructions": technique.instructions,
            "age_guidance": technique.younger if age <= 7 else technique.older,
            "pitfalls": technique.pitfalls,
            "example": technique.example,
        }
        if length == "short":
            item["short_guidance"] = technique.short
        guidance.append(item)
    return guidance
