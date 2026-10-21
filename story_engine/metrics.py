"""Deterministic counts, heuristic readability, and non-authoritative lexical signals."""

import re

from .schemas import Metrics, Story

WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
# Signals for semantic review, never a keyword-only safety decision.
WATCH_TERMS = ("blood", "kill", "knife", "pills", "poison", "monster", "death", "scream")


def words(text: str) -> list[str]:
    return WORD.findall(text)


def syllables(word: str) -> int:
    """Rough English vowel-group heuristic. Names and irregular words are unreliable."""
    w = re.sub(r"[^a-z]", "", word.lower())
    count = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ye")) and count > 1:
        count -= 1
    return max(1, count)


def measure(story: Story, bounds: tuple[int, int]) -> Metrics:
    body = story.body()
    tokens = words(body)
    count = len(tokens)
    # Sentence segmentation is heuristic; punctuation inside abbreviations can mislead it.
    sentences = [s for s in re.split(r'[.!?]+(?:["”])?\s*', body) if words(s)]
    n_sentences = max(1, len(sentences))
    n_syllables = sum(map(syllables, tokens))
    avg = count / n_sentences
    density = n_syllables / max(1, count)
    grade = 0.39 * avg + 11.8 * density - 15.59
    dialogue = re.findall(r'“([^”]*)”|"([^"]*)"', body)
    dialogue_words = sum(len(words(a or b)) for a, b in dialogue)
    flags = [w for w in WATCH_TERMS if re.search(rf"\b{w}\b", body, re.I)]
    failures = []
    if not bounds[0] <= count <= bounds[1]:
        failures.append(f"Body has {count} words; target is {bounds[0]}–{bounds[1]}.")
    warnings = []
    if avg > 20:
        warnings.append("Long average sentence length; inspect read-aloud clarity.")
    if "moral of the story" in body.lower():
        warnings.append("Explicit moral may sound preachy; inspect in context.")
    normalized = [p.strip().casefold() for p in story.paragraphs]
    if len(set(normalized)) < len(normalized):
        warnings.append(
            "Repeated paragraphs detected; distinguish refrain from accidental repetition."
        )
    return Metrics(
        word_count=count,
        paragraph_count=len(story.paragraphs),
        sentence_count=n_sentences,
        mean_sentence_words=round(avg, 2),
        estimated_fk_grade=round(grade, 2),
        estimated_syllables_per_word=round(density, 2),
        dialogue_word_fraction=round(dialogue_words / max(1, count), 3),
        lexical_flags=flags,
        failures=failures,
        warnings=warnings,
    )
