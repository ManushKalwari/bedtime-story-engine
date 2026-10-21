"""Model, story policies, and runtime limits."""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

MODEL = "gpt-3.5-turbo"  # Assignment constraint. No model override or silent fallback.
PROMPT_VERSION = "1.3.8"
DIMENSIONS = ("age_fit", "coherence", "fidelity", "warmth", "bedtime_calm", "cadence")
THRESHOLDS = dict(age_fit=4, coherence=3, fidelity=4, warmth=3, bedtime_calm=4, cadence=3)
ARCS = {
    "friendship": "Shared routine; small misunderstanding; caring action; cozy reunion.",
    "wonder": "Familiar setting; discovery; gentle shift in perspective; peaceful return.",
    "comfort": "Acknowledge a worry; supportive companion; small chosen action; reassurance.",
    "whimsy": "A playful goal; three gentle attempts; surprising solution; quiet rest.",
    "sensory": "A simple journey; soft sensory discoveries; slower pace; a settled destination.",
}


def load_environment() -> None:
    """Load a local .env without replacing variables supplied by the shell."""
    local = Path.cwd() / ".env"
    if local.is_file():
        load_dotenv(local, override=False, encoding="utf-8-sig")
        return
    # Editable installs can be launched from outside the source checkout.
    project = Path(__file__).resolve().parent.parent
    if (project / "pyproject.toml").is_file():
        load_dotenv(project / ".env", override=False, encoding="utf-8-sig")


def word_bounds(age: int, length: str) -> tuple[int, int]:
    if length == "short":
        return (120, 220) if age <= 7 else (200, 350)
    return (300, 450) if age <= 7 else (500, 750)


@dataclass(frozen=True)
class Settings:
    max_revisions: int = 2
    max_calls: int = 24  # Includes every transport attempt and JSON repair.
    max_seconds: float = 180
    timeout: float = 40
    transport_retries: int = 2
    json_repairs: int = 1
    writer_temperature: float = 0.8
    editor_temperature: float = 0.45
    parallel_reviews: bool = True
    input_price: float | None = None
    output_price: float | None = None

    def __post_init__(self):
        if not 0 <= self.max_revisions <= 4:
            raise ValueError("max_revisions must be between 0 and 4")
        if self.max_calls < 1 or any(
            not math.isfinite(x) or x <= 0 for x in (self.max_seconds, self.timeout)
        ):
            raise ValueError("Call and time budgets must be positive")
        if not 0 <= self.transport_retries <= 3 or not 0 <= self.json_repairs <= 2:
            raise ValueError("Retry limits are out of range")
        for t in (self.writer_temperature, self.editor_temperature):
            if not 0 <= t <= 2:
                raise ValueError("Temperature must be between 0 and 2")
        for price in (self.input_price, self.output_price):
            if price is not None and (price < 0 or not math.isfinite(price)):
                raise ValueError("Prices must be finite and nonnegative")

    @classmethod
    def from_env(cls, **kwargs):
        load_environment()

        def price(name):
            raw = os.getenv(name)
            return None if raw is None else float(raw)

        return cls(
            input_price=price("STORY_INPUT_USD_PER_MILLION"),
            output_price=price("STORY_OUTPUT_USD_PER_MILLION"),
            **kwargs,
        )
