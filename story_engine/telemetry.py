"""Per-run accounting. Content tracing is opt-in; credentials are never logged."""

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class EngineError(RuntimeError):
    """Expected operational error suitable for a concise user-facing message."""


class BudgetExceeded(EngineError):
    pass


class ResponseValidationError(ValueError):
    """A content-free field error plus optional source context for the model's repair."""

    def __init__(self, message, *, path, code, repair_hint="", issues=None):
        super().__init__(message)
        self.path = path
        self.code = code
        self.repair_hint = repair_hint
        self.issues = issues if issues is not None else [{"path": list(path), "type": code}]


class Recorder:
    def __init__(self, settings, *, synthetic=False, content=False):
        self.settings = settings
        self.run_id = uuid.uuid4().hex[:12]
        self.synthetic = synthetic
        self.content = content
        self.started = time.monotonic()
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.events = []
        self.attempts = 0
        self._lock = threading.Lock()

    def reserve(self) -> int:
        with self._lock:
            if self.attempts >= self.settings.max_calls:
                raise BudgetExceeded("Model-call budget exhausted")
            if self.remaining() <= 0:
                raise BudgetExceeded("Run time budget exhausted")
            self.attempts += 1
            return self.attempts

    def remaining(self) -> float:
        return self.settings.max_seconds - (time.monotonic() - self.started)

    def add(self, event: dict):
        with self._lock:
            self.events.append({"run_id": self.run_id, **event})

    def summary(self) -> dict:
        calls = [e for e in self.events if e.get("type") == "call"]
        inp = sum(e.get("input_tokens", 0) for e in calls)
        out = sum(e.get("output_tokens", 0) for e in calls)
        known = all(e.get("usage_known", False) for e in calls)
        cost = None
        if (
            not self.synthetic
            and known
            and self.settings.input_price is not None
            and self.settings.output_price is not None
        ):
            cost = (inp * self.settings.input_price + out * self.settings.output_price) / 1e6
        return {
            "attempts": self.attempts,
            "completed_calls": len(calls),
            "input_tokens": inp,
            "output_tokens": out,
            "usage_complete": known and len(calls) == self.attempts,
            "estimated_usd_for_recorded_usage": cost,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "input_usd_per_million": self.settings.input_price,
            "output_usd_per_million": self.settings.output_price,
        }

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for event in self.events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
