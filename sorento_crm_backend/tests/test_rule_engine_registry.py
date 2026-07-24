"""Promotion fact-registry tests (app/rule_engine/registry.py).

resolve_facts on a Promotion ORM object -> flat fact dict:
  - promotion.name  == description (there is no `name` column)
  - promotion.accessLevels == the access_levels list
  - promotion.isActive == bool
  - promotion.endDate.daysUntil / .daysSince compute against Malaysia *today*

Plus the accessLevels dynamic-options resolver returns active ContactAccessType
rows as {value: code, label: name}.

Uses an in-memory sqlite engine (conftest compiles JSONB -> JSON for sqlite).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import ContactAccessType
from app.models.marketing import Promotion
from app.rule_engine.registry import fact_map, get_facts, resolve_facts
from app.services.sla_service import MALAYSIA_TZ


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # ContactAccessType.keywords carries a pg `'[]'::jsonb` server_default whose
    # `::jsonb` cast sqlite's DDL compiler can't parse — null it for the fixture.
    for tbl in (Promotion.__table__, ContactAccessType.__table__):
        for col in tbl.columns:
            sd = getattr(col.server_default, "arg", None)
            if sd is not None and "::" in str(sd):
                col.server_default = None
    Base.metadata.create_all(
        engine,
        tables=[Promotion.__table__, ContactAccessType.__table__],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _malaysia_today() -> date:
    return datetime.now(MALAYSIA_TZ).date()


def _mk_promo(db, **kw) -> Promotion:
    today = _malaysia_today()
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=kw.get("description", "Sorento Mega Sale"),
        start_date=kw.get("start_date", today - timedelta(days=3)),
        end_date=kw.get("end_date", today + timedelta(days=7)),
        is_active=kw.get("is_active", True),
        access_levels=kw.get("access_levels", ["sorento_dealer", "sorento_office"]),
    )
    db.add(promo)
    db.flush()
    return promo


def test_resolve_name_from_description(db):
    promo = _mk_promo(db, description="Kitchen Sink Special")
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.name"] == "Kitchen Sink Special"


def test_resolve_access_levels_list(db):
    promo = _mk_promo(db, access_levels=["sorento_dealer", "cabana_office"])
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.accessLevels"] == ["sorento_dealer", "cabana_office"]


def test_resolve_access_levels_non_list_yields_empty(db):
    promo = _mk_promo(db)
    promo.access_levels = None
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.accessLevels"] == []


def test_resolve_is_active_boolean(db):
    promo = _mk_promo(db, is_active=False)
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.isActive"] is False


def test_days_until_end_computes_against_malaysia_today(db):
    today = _malaysia_today()
    promo = _mk_promo(db, end_date=today + timedelta(days=7))
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.endDate.daysUntil"] == 7
    assert facts["promotion.endDate.daysSince"] == -7


def test_days_since_start_computes_against_malaysia_today(db):
    today = _malaysia_today()
    promo = _mk_promo(db, start_date=today - timedelta(days=4))
    facts = resolve_facts(db, {"promotion": promo})
    assert facts["promotion.startDate.daysSince"] == 4
    assert facts["promotion.startDate.daysUntil"] == -4


def test_only_keys_limits_resolution(db):
    promo = _mk_promo(db)
    facts = resolve_facts(db, {"promotion": promo}, only_keys={"promotion.name"})
    assert facts == {"promotion.name": promo.description}


def test_none_object_resolves_all_to_none(db):
    facts = resolve_facts(db, {"promotion": None}, only_keys={"promotion.name"})
    assert facts["promotion.name"] is None


def test_fact_map_registers_the_nine_promotion_facts(db):
    facts = fact_map(["promotion"])
    expected = {
        "promotion.name",
        "promotion.accessLevels",
        "promotion.isActive",
        "promotion.startDate",
        "promotion.startDate.daysSince",
        "promotion.startDate.daysUntil",
        "promotion.endDate",
        "promotion.endDate.daysSince",
        "promotion.endDate.daysUntil",
    }
    assert expected <= set(facts.keys())
    # name/accessLevels/isActive carry the right declared types
    assert facts["promotion.name"].type == "string"
    assert facts["promotion.accessLevels"].type == "list"
    assert facts["promotion.isActive"].type == "boolean"
    assert facts["promotion.endDate"].type == "date"
    assert facts["promotion.endDate.daysUntil"].type == "number"


def test_access_levels_options_callable_returns_active_types(db):
    db.add(ContactAccessType(code="sorento_dealer", name="Sorento Dealer", is_active=True, sort_order=1, keywords=[]))
    db.add(ContactAccessType(code="cabana_office", name="Cabana Office", is_active=True, sort_order=2, keywords=[]))
    db.add(ContactAccessType(code="legacy_off", name="Legacy", is_active=False, sort_order=3, keywords=[]))
    db.commit()

    access_fact = fact_map(["promotion"])["promotion.accessLevels"]
    assert callable(access_fact.options)
    opts = access_fact.options(db, {"id": "tester"})
    values = [o["value"] for o in opts]
    labels = {o["value"]: o["label"] for o in opts}
    assert "sorento_dealer" in values
    assert "cabana_office" in values
    assert "legacy_off" not in values  # inactive excluded
    assert labels["sorento_dealer"] == "Sorento Dealer"
