"""Bedtime story assignment.

With two more hours, I would prototype three improvements:

1. Personalize the brief. Ask an optional question about the child's interests,
   such as silly comedy, fairy tales, or anime-inspired adventures. A research
   agent could suggest storytelling techniques from relevant authors and genres,
   extending the existing library with original examples from author or peculiar characters.
   The planner would use those techniques while preserving the requested age, gentle stakes, and calm ending.

2. Learn from feedback. Offer a simple optional rating and ask which part the
   child liked or wanted changed, with a caregiver's help where appropriate.
   With permission, save a small, editable preference summary. Across roughly
   10-15 stories, test whether feedback reveals personal preferences for
   humor, characters, pacing, or themes. Let families review, reset, or delete that memory.
   Track to check whether they improve enjoyment without weakening age suitability or request fidelity.

3. Keep longer sessions consistent. Extend the existing bounded workflow with
   explicit session state: the current brief, ordered feedback, confirmed
   preferences, and last accepted story. Supply this compact state on each turn
   so earlier instructions remain available and newer requests take precedence.
   If the history grows, retrieve only relevant preferences and continuity facts (RAG).
   Separately, test caching and other reusable techniques to reduce token usage, while still reviewing each new story.

I would prioritize a small preference-and-feedback prototype and human review of
saved failures within the two-hour budget. I would keep a check on
judge's scores against human ratings before trusting it to measure
personalization, and to improve the judge. Persistent retrieval and caching,
measured for quality, latency, and token cost.
"""

from story_engine.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
