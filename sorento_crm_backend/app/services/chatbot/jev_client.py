"""Jev (TypeSafe AI) as the console router's classifier (AGENTIC-P2-ROUTE).

One POST to the `systemone` endpoint carrying one typed `choice` question, `route`, with the
criteria of the two sides. The caller (`router.py`) decides what a failure means; this module only
names it (`JevError.kind`). The key is sent as a bearer header and never logged.
"""
from __future__ import annotations

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
    try:
        response = httpx.post(
            JEV_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout_s
        )
    except httpx.TimeoutException:
        raise JevError("timeout") from None
    except httpx.HTTPError:
        raise JevError("transport") from None
    if response.status_code == 429:
        raise JevError("rate_limited")
    if response.status_code >= 400:
        raise JevError(f"http_{response.status_code}")
    try:
        data = response.json()
        route = data["answers"]["route"]
        choice = str(route["choice"])
        confidence = float(route["confidence"])
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
        raise JevError("malformed") from None
