"""Jev (TypeSafe AI) as the console router's classifier (AGENTIC-P2-ROUTE).

One POST to the `systemone` endpoint carrying one typed `choice` question, `route`, with the
criteria of the two sides. The caller (`router.py`) decides what a failure means; this module only
names it (`JevError.kind`). The key is sent as a bearer header and never logged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import httpx

JEV_URL = "https://api.typesafe.ai/v1/systemone"
#: The card's p95 bar for the whole routing step.
TIMEOUT_S = 1.5
#: The model the router asks for when the prompt label pins none.
DEFAULT_MODEL = "jev-1.14.0"


class JevError(Exception):
    """A Jev call that gave no usable answer. `kind` is one of timeout, rate_limited,
    http_<status>, malformed or transport."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass
class JevAnswer:
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


def classify(
    api_key: str,
    *,
    model: str,
    instructions: str,
    criteria: dict[str, Any],
    state: dict[str, Any],
    timeout_s: float = TIMEOUT_S,
) -> JevAnswer:
    body = {
        "model": model,
        "state": state,
        "questions": {"route": {"type": "choice", "instructions": instructions, "criteria": criteria}},
    }
    # Every failure is named OUTSIDE its except block, so the raised error carries no cause or
    # context: the request holds the key, and a chained error could show it.
    failure: str | None = None
    answer: JevAnswer | None = None
    try:
        response = httpx.post(
            JEV_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout_s
        )
        if response.status_code == 429:
            failure = "rate_limited"
        elif response.status_code >= 400:
            failure = f"http_{response.status_code}"
        else:
            try:
                data = response.json()
            except ValueError:
                data = None
            answer = _parse(data, model)
            failure = None if answer is not None else "malformed"
    except httpx.TimeoutException:
        failure = "timeout"
    except Exception:  # noqa: BLE001 - transport errors, an unencodable key: never echo the cause
        failure = "transport"
    if failure is not None or answer is None:
        raise JevError(failure or "malformed")
    return answer


def _parse(data: Any, model: str) -> JevAnswer | None:
    """The answer, or None when the body is not the shape (or the confidence not a number in 0..1)."""
    try:
        route = data["answers"]["route"]
        choice = str(route["choice"])
        confidence = route["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return None
        probabilities = {str(k): float(v) for k, v in (route.get("probabilities") or {}).items()}
        usage = data.get("usage") or {}
        return JevAnswer(
            choice=choice,
            confidence=confidence,
            probabilities=probabilities,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            model=data.get("model") or model,
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
