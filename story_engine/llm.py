"""Single SDK boundary: fixed model, finite retries, JSON validation, and accounting."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .config import MODEL, PROMPT_VERSION
from .telemetry import BudgetExceeded, EngineError, Recorder, ResponseValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass
class Completion:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    model: str = MODEL
    usage_known: bool = True
    fingerprint: str | None = None


class TransientError(EngineError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class Transport(Protocol):
    synthetic: bool

    def complete(
        self,
        messages: list[dict],
        *,
        stage: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        timeout: float,
    ) -> Completion: ...


class OpenAITransport:
    synthetic = False

    def __init__(self):
        from openai import OpenAI

        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or key == "replace_locally":
            raise EngineError(
                "Set OPENAI_API_KEY in your shell, or run --demo for an offline example."
            )
        # Disable SDK retries so every attempt is counted by our single retry policy.
        self.client = OpenAI(api_key=key, max_retries=0, base_url="https://api.openai.com/v1")

    def complete(self, messages, *, stage, temperature, max_tokens, json_mode, timeout):
        import openai

        try:
            kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                stream=False,
                **kwargs,
            )
        except openai.AuthenticationError as exc:
            raise EngineError("OpenAI authentication failed. Check your API key.") from exc
        except (openai.NotFoundError, openai.PermissionDeniedError) as exc:
            raise EngineError(
                f"{MODEL} is unavailable to this account or retired. Ask the assignment owner; "
                "this repo never substitutes a different model."
            ) from exc
        except (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ) as exc:
            if (
                isinstance(exc, openai.RateLimitError)
                and getattr(exc, "code", None) == "insufficient_quota"
            ):
                raise EngineError("OpenAI quota exhausted. Check API billing.") from exc
            delay = None
            headers = getattr(getattr(exc, "response", None), "headers", {})
            try:
                delay = float(headers.get("retry-after", ""))
            except (TypeError, ValueError):
                pass
            raise TransientError(
                "Temporary OpenAI connection, rate-limit, or server failure", delay
            ) from exc
        except openai.APIError as exc:
            raise EngineError(
                "OpenAI rejected the request. Check model access and API compatibility."
            ) from exc
        if not response.choices:
            raise EngineError("OpenAI returned no completion")
        choice = response.choices[0]
        usage = response.usage
        return Completion(
            choice.message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            choice.finish_reason,
            response.model,
            usage is not None,
            response.system_fingerprint,
        )


def parse_json(text: str):
    """Accept one object, optionally fenced. Never eval strings or guess missing fields."""
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(value)


class ModelClient:
    def __init__(self, transport: Transport, recorder: Recorder):
        self.transport = transport
        self.recorder = recorder
        self.settings = recorder.settings

    def call(self, stage, messages, *, temperature=0.1, max_tokens=2600, json_mode=True):
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        for attempt in range(self.settings.transport_retries + 1):
            call_id = self.recorder.reserve()
            start = time.monotonic()
            try:
                result = self.transport.complete(
                    messages,
                    stage=stage,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    timeout=min(self.settings.timeout, self.recorder.remaining()),
                )
            except EngineError as exc:
                self.recorder.add(
                    {
                        "type": "call_error",
                        "stage": stage,
                        "call_id": call_id,
                        "error_type": type(exc).__name__,
                    }
                )
                if (
                    not isinstance(exc, TransientError)
                    or attempt == self.settings.transport_retries
                ):
                    raise
                delay = min(
                    8, max(0, exc.retry_after if exc.retry_after is not None else 2**attempt)
                )
                if delay >= self.recorder.remaining():
                    raise BudgetExceeded("Time budget exhausted during retry backoff") from exc
                time.sleep(delay)
                continue
            event = {
                "type": "call",
                "stage": stage,
                "call_id": call_id,
                "model": result.model,
                "prompt_version": PROMPT_VERSION,
                "request_hash": digest,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "usage_known": result.usage_known,
                "finish_reason": result.finish_reason,
                "fingerprint": result.fingerprint,
                "seconds": round(time.monotonic() - start, 3),
            }
            if self.recorder.content:
                # Repair appends messages later; each trace entry must preserve its own request.
                event.update(
                    messages=[dict(message) for message in messages], response=result.content
                )
            self.recorder.add(event)
            if self.recorder.remaining() <= 0:
                raise BudgetExceeded("Run time budget exhausted after completion")
            if result.finish_reason != "stop":
                raise EngineError(
                    f"Incomplete or filtered {stage} response ({result.finish_reason}); not accepted"
                )
            if not result.content.strip():
                raise EngineError(f"Empty response from {stage}")
            return result.content
        raise AssertionError("Unreachable")

    def structured(
        self,
        stage: str,
        instruction: str,
        payload: dict,
        schema: type[T],
        *,
        temperature=0.1,
        validate: Callable[[T], None] | None = None,
        repair_instruction: str = "",
    ) -> T:
        system = (
            instruction
            + "\nReturn only one JSON object matching this schema:\n"
            + json.dumps(schema.model_json_schema())
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        for repair in range(self.settings.json_repairs + 1):
            raw = self.call(
                stage if repair == 0 else stage + ".repair", messages, temperature=temperature
            )
            try:
                result = schema.model_validate(parse_json(raw))
                if validate:
                    validate(result)
                return result
            except (ValidationError, ValueError, TypeError, KeyError, IndexError) as exc:
                # Paths and error codes explain shape failures without logging story content.
                if isinstance(exc, ResponseValidationError):
                    issues = exc.issues
                elif isinstance(exc, ValidationError):
                    issues = [
                        {"path": list(error["loc"]), "type": error["type"]}
                        for error in exc.errors(include_input=False, include_url=False)
                    ]
                else:
                    issues = [{"path": [], "type": type(exc).__name__}]
                event = {
                    "type": "validation_error",
                    "stage": stage,
                    "repair": repair,
                    "issues": issues,
                }
                if self.recorder.content:
                    event["validation_message"] = str(exc)[:1200]
                self.recorder.add(event)
                if repair == self.settings.json_repairs:
                    summary = "; ".join(
                        f"{'.'.join(str(part) for part in issue['path']) or 'response'} "
                        f"({issue['type']})"
                        for issue in issues[:3]
                    )
                    raise EngineError(
                        f"{stage} returned invalid structured output after bounded repair: {summary}"
                    ) from exc
                # Do not use a heuristic JSON fixer that could turn malformed safety data into approval.
                errors = str(exc)[:1200]
                if isinstance(exc, ResponseValidationError) and exc.repair_hint:
                    errors += "\n" + exc.repair_hint
                messages.extend(
                    [
                        {"role": "assistant", "content": raw},
                        {
                            "role": "user",
                            "content": "Correct the JSON to satisfy the schema and validation. "
                            "Preserve honest findings; never default to approval. Validation errors: "
                            + errors
                            + ("\n" + repair_instruction if repair_instruction else ""),
                        },
                    ]
                )
        raise AssertionError("Unreachable")
