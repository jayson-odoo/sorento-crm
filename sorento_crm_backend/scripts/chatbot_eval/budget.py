"""Token cost estimate and a thread-safe spend cap."""

from __future__ import annotations

import threading

# USD per 1M tokens: (input, cached input, output). https://developers.openai.com/api/docs/pricing, 10 Oct 2026.
PRICES = {
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    # https://platform.claude.com/docs/en/about-claude/pricing, read 11 Oct 2026
    "claude-sonnet-5-5": (2.00, 0.10, 10.00),
}


def _seeded_prices() -> None:
    """CHATBOT-SPEED: the owner-approved app price rows (`analytics_connector/prices.py`, the one place a price lives)
    for every model this table lacks, e.g. the prod parser's gemini-3.5-flash-lite. A row above wins; a seed with no
    cached price is skipped (the meter needs all three). Without them a live replay on that model counted US$0 and
    stopped at its first item (`unpriced_model`)."""
    try:
        from app.services.analytics_connector.prices import SEED_PRICES
    except Exception:  # noqa: BLE001 - run outside the backend: the table above only
        return
    for model, (inp, cached, out, _source) in SEED_PRICES.items():
        if model not in PRICES and cached is not None:
            PRICES[model] = (float(inp), float(cached), float(out))


_seeded_prices()


def cost_usd(tokens: dict, model: str) -> float:
    p_in, p_cached, p_out = PRICES[model]
    prompt, cached, output = (int(tokens.get(k, 0) or 0) for k in ("prompt", "cached", "output"))
    return ((prompt - cached) * p_in + cached * p_cached + output * p_out) / 1e6


class Budget:
    def __init__(self, usd_cap: float, model: str):
        self.usd_cap = usd_cap
        self.model = model
        self._spent = 0.0
        self._lock = threading.Lock()

    def add(self, tokens: dict) -> None:
        with self._lock:
            self._spent += cost_usd(tokens, self.model)

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    @property
    def exceeded(self) -> bool:
        return self.spent > self.usd_cap
