"""Jev (TypeSafe AI) `systemone` call for the chatbot router (AGENTIC-P2).

One synchronous POST with one `choice` question. Wire format: `PLAN-agentic-p2-routing-30oct.md`
"Jev wire format". Any failure is a `JevError` whose text never carries the key: the key rides in
the Authorization header, and an upstream error body or an exception message may echo it, so
neither is ever copied into the error.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.typesafe.ai"
PATH = "/v1/systemone"
QUESTION = "route"


class JevError(Exception):
    """The Jev call failed or answered in a shape we cannot use. Never contains the key."""


def choose(
    key: str,
    *,
    state: str,
    instructions: str,
    criteria: dict[str, str],
    model: str = "jev-latest",
    timeout: float = 1.5,
    base_url: str | None = None,
) -> dict[str, Any]:
    base = (base_url or os.environ.get("JEV_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    body = {
        "model": model,
        "state": state,
        "questions": {QUESTION: {"type": "choice", "instructions": instructions, "criteria": criteria}},
    }
    try:
        resp = httpx.post(
            base + PATH, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout
        )
    except httpx.HTTPError as exc:
        raise JevError(f"Jev request failed: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise JevError(f"Jev answered HTTP {resp.status_code}")
    try:
        data = resp.json()
        answer = data["answers"][QUESTION]
        usage = data.get("usage") or {}
        return {
            "choice": str(answer["choice"]),
            "confidence": float(answer["confidence"]),
            "probabilities": {str(k): float(v) for k, v in answer["probabilities"].items()},
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise JevError("Jev answered in an unexpected shape") from None
