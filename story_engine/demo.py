"""Synthetic scripted responses: an offline controller demo, NOT GPT-3.5 outputs."""

import json
from importlib.resources import files

from .config import DIMENSIONS
from .llm import Completion


class DemoTransport:
    synthetic = True

    def __init__(self, scenario="improve"):
        self.scenario = scenario
        self.quality_count = 0
        self.fixture = json.loads(
            files("story_engine").joinpath("fixtures", "demo.json").read_text(encoding="utf-8")
        )

    def complete(self, messages, *, stage, **kwargs):
        payload = json.loads(messages[1]["content"])
        base = stage.split(".")[0]
        if base == "intake":
            value = self.fixture["brief"]
        elif base == "planner":
            value = self.fixture["blueprint"]
        elif base == "writer":
            value = self.fixture["story"]
        elif base == "editor":
            value = {"edits": [{"paragraph": 5, "replacement": self.fixture["ending"]}]}
        elif base == "safety":
            value = {
                "safe": self.scenario != "fail",
                "reason": "Synthetic failure flag for controller testing; repair the scripted issue."
                if self.scenario == "fail"
                else "Scripted synthetic review found no safety concerns; not a live assessment.",
            }
        elif base == "quality":
            self.quality_count += 1
            p = payload["story"]["paragraphs"]
            value = {}
            for k in DIMENSIONS:
                score = 4
                if k == "bedtime_calm":
                    score = 3 if self.quality_count == 1 else 5
                if self.scenario == "rollback" and self.quality_count > 1 and k == "fidelity":
                    score = 2
                value[k] = {
                    "evidence": {
                        "paragraph": 5,
                        "quote": p[4][:60],
                        "observation": "Scripted rating to exercise the controller.",
                    },
                    "score": score,
                }
            value.update(
                preserve=["Alice and Bob's friendship"],
                fixes=[{"paragraph": 5, "instruction": "Give the ending a quieter landing."}],
                arousal_by_paragraph=[2, 3, 3, 2, 3 if self.quality_count == 1 else 1],
                craft={
                    "resolution": {
                        "paragraph": 4,
                        "quote": "they had simply found another place to look.",
                        "observation": "Scripted evidence: Alice's choice leads to a new view.",
                    },
                    "specificity": {
                        "paragraph": 1,
                        "quote": "as if he were saving a place for the moon.",
                        "observation": "Scripted evidence: Bob's habitual paw gesture.",
                    },
                    "setup_payoff": {
                        "setup": {
                            "paragraph": 1,
                            "quote": "a tall sunflower nodded across their view.",
                            "observation": "Scripted setup of the blocked view.",
                        },
                        "payoff": {
                            "paragraph": 4,
                            "quote": "they had simply found another place to look.",
                            "observation": "Scripted payoff: a change of viewpoint.",
                        },
                    },
                },
            )
        else:
            raise RuntimeError(f"The fixed demo does not implement stage {stage}")
        return Completion(json.dumps(value), model="synthetic-fixture", usage_known=False)
