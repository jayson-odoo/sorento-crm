"""GEMINI-EXPLICIT-CACHE: price row for gemini-3.5-flash-lite in llm_model_prices

Revision ID: gemprice_0001_gemini_prices
Revises: appeal_0001_appeal_labels
Create Date: 2026-10-28 00:00:00.000000

Data only, additive, idempotent. Prod watch (28 Oct 2026) found no `llm_model_prices` row for
`gemini-3.5-flash-lite`, the chatbot parser's model for most contacts, so every turn on it read
NULL cost; with explicit context caching (this lane) its cached tokens also need a cached price.

Google's published Standard (paid) tier prices, USD per 1M tokens, prompts up to 200k tokens:
input 0.30, cached input 0.03, output 2.50 (output includes thinking tokens).
Source: https://ai.google.dev/gemini-api/docs/pricing (read 28 Oct 2026).

`prices.seed_prices` inserts the row when it is missing (ON CONFLICT DO NOTHING) and otherwise
fills only a NULL cached price; a price an operator set is never overwritten. The same seed row
reaches a fresh environment through `scripts/bootstrap_env.py`, which runs `seed_prices` too.
Downgrade removes nothing: the row may have been edited since, and a missing price reads as
unpriced, never as free.
"""
from alembic import op

from app.services.analytics_connector import prices

revision = "gemprice_0001_gemini_prices"
down_revision = "appeal_0001_appeal_labels"
branch_labels = None
depends_on = None

MODELS = ("gemini-3.5-flash-lite",)


def upgrade() -> None:
    prices.seed_prices(op.get_bind(), MODELS)


def downgrade() -> None:
    pass
