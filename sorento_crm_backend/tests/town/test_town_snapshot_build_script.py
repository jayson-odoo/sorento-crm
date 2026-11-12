"""`scripts.town_snapshot_build`: build a past day by hand and store it under today's keys."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust
from tests.town._town_seed import DAY, NOW, dealer_doc


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


def _today():
    from app.services.town.snapshot import MYT

    return datetime.now(MYT).date()


def test_as_today_puts_a_seeded_past_day_under_todays_key(db):
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import load
    from scripts.town_snapshot_build import run

    dealer_doc(db, cust(db, name="ZZT Hand Test Shop"), "123.00", DAY)
    stored_day, version = run(db, redis_conn, DEFAULT_COMPANY_ID, DAY, NOW, as_today=True)
    assert stored_day == _today()
    body, loaded_version = load(redis_conn, DEFAULT_COMPANY_ID, _today(), "full")
    assert loaded_version == version
    snap = json.loads(gzip.decompress(body))
    assert snap["day"] == DAY.isoformat() and snap["today"]["amount"] == "123.00"
    assert load(redis_conn, DEFAULT_COMPANY_ID, DAY, "full") is None  # not under the built day's own key


def test_without_as_today_it_stores_under_the_built_day(db):
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import load
    from scripts.town_snapshot_build import run

    stored_day, _ = run(db, redis_conn, DEFAULT_COMPANY_ID, DAY, NOW, as_today=False)
    assert stored_day == DAY
    assert load(redis_conn, DEFAULT_COMPANY_ID, DAY, "full") is not None
    assert load(redis_conn, DEFAULT_COMPANY_ID, _today(), "full") is None


def test_as_today_is_refused_in_production(monkeypatch, capsys):
    from app.config import settings
    from scripts.town_snapshot_build import main

    monkeypatch.setattr(settings, "environment", "production")
    assert main(["--as-today", "--date", "2026-11-03"]) == 2
    assert "Refusing" in capsys.readouterr().err
