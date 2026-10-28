"""GEMINI-EXPLICIT-CACHE: `llm_model_prices` carries Google's prices for the bot's Gemini models.

Prod watch, 28 Oct 2026: `gemini-3.5-flash-lite` had no price row, so every parser turn on it
showed a NULL cost, and once explicit caching lands its cached tokens need a cached price too
(`prices.cost_sql` reads a cached token without one as NULL). The migration inserts the row when
it is missing and fills only a NULL cached price on a row that exists; a price someone set is
never overwritten. Runs on Postgres (`pg_session`, rolled back).
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from tests._pg_fixture import pg_session

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "gemprice_0001_gemini_prices.py"
MODEL = "gemini-3.5-flash-lite"


def _load():
    spec = importlib.util.spec_from_file_location("gemprice_0001_gemini_prices", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(db) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        _load().upgrade()


def _row(db, model=MODEL):
    return db.execute(
        text("SELECT input_usd_per_1m, cached_input_usd_per_1m, output_usd_per_1m, note "
             "FROM llm_model_prices WHERE model = :m"),
        {"m": model},
    ).one_or_none()


def _log(db, *, prompt, cached, completion, model=MODEL):
    lid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO ai_assistant_usage_logs (id, feature, provider, model, prompt_tokens, cached_tokens, "
             "completion_tokens, total_tokens, tool_calls_count, response_time_ms, was_answered) "
             "VALUES (:id, 'chatbot_parser', 'gemini', :m, :pt, :ct, :co, :tt, 0, 10, true)"),
        {"id": lid, "m": model, "pt": prompt, "ct": cached, "co": completion, "tt": prompt + completion},
    )
    return lid


def _cost(db, lid):
    from app.services.analytics_connector.prices import cost_sql

    c = cost_sql("u", "p")
    return db.execute(
        text(f"SELECT {c.cost_usd} AS cost_usd, {c.priced} AS priced FROM ai_assistant_usage_logs u "
             "LEFT JOIN llm_model_prices p ON p.model = u.model WHERE u.id = :id"),
        {"id": lid},
    ).one()


def test_flash_lite_gets_googles_standard_prices_when_it_has_no_row():
    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model = :m"), {"m": MODEL})
        _upgrade(db)

        row = _row(db)
        assert row is not None
        assert (row.input_usd_per_1m, row.cached_input_usd_per_1m, row.output_usd_per_1m) == (
            Decimal("0.300000"), Decimal("0.030000"), Decimal("2.500000"),
        )
        assert "ai.google.dev/gemini-api/docs/pricing" in row.note


def test_a_flash_lite_call_with_cached_tokens_is_costed_at_the_cached_rate():
    """The live-check shape (28 Oct): 9114 prompt tokens, 9106 of them cached, 100 out.

    Gemini counts cached tokens INSIDE `prompt_tokens`: 8 uncached at 0.30, 9106 cached at
    0.03, 100 output at 2.50 -> (2.4 + 273.18 + 250) / 1e6.
    """
    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model = :m"), {"m": MODEL})
        _upgrade(db)
        lid = _log(db, prompt=9114, cached=9106, completion=100)

        row = _cost(db, lid)
        assert row.priced is True
        assert Decimal(row.cost_usd) == Decimal("0.00052558")


def test_an_existing_row_gets_only_its_missing_cached_price():
    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model = :m"), {"m": MODEL})
        db.execute(
            text("INSERT INTO llm_model_prices (model, input_usd_per_1m, cached_input_usd_per_1m, output_usd_per_1m, note) "
                 "VALUES (:m, 0.31, NULL, 2.60, 'owner, 28 Oct 2026')"),
            {"m": MODEL},
        )
        _upgrade(db)

        row = _row(db)
        assert row.input_usd_per_1m == Decimal("0.310000")
        assert row.output_usd_per_1m == Decimal("2.600000")
        assert row.cached_input_usd_per_1m == Decimal("0.030000")
        assert row.note == "owner, 28 Oct 2026"


def test_a_cached_price_someone_set_is_never_overwritten_and_a_rerun_changes_nothing():
    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model = :m"), {"m": MODEL})
        db.execute(
            text("INSERT INTO llm_model_prices (model, input_usd_per_1m, cached_input_usd_per_1m, output_usd_per_1m) "
                 "VALUES (:m, 0.30, 0.025, 2.50)"),
            {"m": MODEL},
        )
        _upgrade(db)
        _upgrade(db)

        assert _row(db).cached_input_usd_per_1m == Decimal("0.025000")
        assert db.execute(
            text("SELECT count(*) FROM llm_model_prices WHERE model = :m"), {"m": MODEL}
        ).scalar() == 1


def test_a_fresh_environment_seeds_the_same_row():
    """`scripts/bootstrap_env.py` builds from the models and runs `prices.seed_prices`, not the migrations."""
    from app.services.analytics_connector import prices

    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model = :m"), {"m": MODEL})
        prices.seed_prices(db.connection())

        row = _row(db)
        assert (row.input_usd_per_1m, row.cached_input_usd_per_1m, row.output_usd_per_1m) == (
            Decimal("0.300000"), Decimal("0.030000"), Decimal("2.500000"),
        )


def test_the_migration_touches_only_the_rows_it_names():
    """A NULL cached price on another seed model is that migration's business, not this one's."""
    with pg_session() as db:
        db.execute(text("DELETE FROM llm_model_prices WHERE model IN (:m, 'gpt-5.4-mini')"), {"m": MODEL})
        db.execute(
            text("INSERT INTO llm_model_prices (model, input_usd_per_1m, cached_input_usd_per_1m, output_usd_per_1m) "
                 "VALUES ('gpt-5.4-mini', 0.75, NULL, 4.50)")
        )
        _upgrade(db)

        assert _row(db, "gpt-5.4-mini").cached_input_usd_per_1m is None
