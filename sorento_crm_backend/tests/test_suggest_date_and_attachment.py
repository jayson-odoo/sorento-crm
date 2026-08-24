"""Wave 3d - date-axis (M4) + product-attachment entity-axis (M5) relaxation.

Covers PLAN-suggest-on-miss-variant-graph.md §3.4 / §3.5 / §7.3:

  M4  order/delivery empty path -> nearest DELIVERY dates for the SAME customer
      scope, `relaxed_axis="date"`.
  M5  product-attachment / cert empty path -> data-bearing variant/neighbour
      products that HAVE an attachment (optionally of the asked type),
      `relaxed_axis="entity"` (reuses the shared neighbour helper).
  AC-R1  a with-data (non-empty) result carries NO alternatives / relaxed_axis keys.

Both paths depend on live Postgres data (the date-nearest probe and the
pg_trgm/variant graph), so these tests hit the DB via DATABASE_URL and skip
cleanly when it is unreachable or the referenced real rows aren't present.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# --------------------------------------------------------------------------- #
# Live-DB fixture. Skips cleanly when unreachable.
# --------------------------------------------------------------------------- #
def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        from dotenv import dotenv_values

        return dotenv_values(".env").get("DATABASE_URL")
    except Exception:
        return None


@pytest.fixture(scope="module")
def db():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL not configured")
    try:
        engine = create_engine(url)
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres unreachable: {exc}")
    conn.close()
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _require_codes(db, *codes):
    for code in codes:
        exists = db.execute(
            text("SELECT 1 FROM products WHERE product_code = :c LIMIT 1"),
            {"c": code},
        ).first()
        if not exists:
            pytest.skip(f"reference code {code!r} not present in DB")


def _require_debtor_dates(db, debtor, present_dates):
    """Skip unless `debtor` has a DO on each of `present_dates` (YYYY-MM-DD)."""
    for d in present_dates:
        row = db.execute(
            text(
                "SELECT 1 FROM orders WHERE deleted_at IS NULL AND debtor_name = :n "
                "AND actual_delivery_date::date = :d LIMIT 1"
            ),
            {"n": debtor, "d": d},
        ).first()
        if not row:
            pytest.skip(f"debtor {debtor!r} has no DO on {d}")


def _require_no_debtor_date(db, debtor, absent_date):
    row = db.execute(
        text(
            "SELECT 1 FROM orders WHERE deleted_at IS NULL AND debtor_name = :n "
            "AND actual_delivery_date::date = :d LIMIT 1"
        ),
        {"n": debtor, "d": absent_date},
    ).first()
    if row:
        pytest.skip(f"debtor {debtor!r} unexpectedly HAS a DO on {absent_date}")


# Real fixtures verified against the live catalog (2026-07-04).
_DEBTOR = "LUXEWARE BATH AND ART [A/C IV]"
_EMPTY_DATE = "2026-04-05"          # LUXEWARE has no DO here
_NEAR_DATES = ("2026-04-01", "2026-04-02", "2026-04-09")  # DOs exist here
_WITH_DATE = "2026-04-02"           # a date that DOES have a DO

_PROD_NO_ATT = "SRTWC8613-RL-G"     # no attachment
_PROD_SIBLING_ATT = "SRTWC8613-RL"  # sibling WITH an attachment (sim ~0.867)
_PROD_ISOLATED = '1/2" ULTRA CIRCULAR'  # no attachment, no data-bearing neighbour


# --------------------------------------------------------------------------- #
# M4 - date-axis (service layer)
# --------------------------------------------------------------------------- #
def _svc_orders(db):
    from app.services.order_service import OrderService

    return OrderService(db)


def test_m4_empty_date_emits_nearest_dates(db):
    _require_debtor_dates(db, _DEBTOR, _NEAR_DATES)
    _require_no_debtor_date(db, _DEBTOR, _EMPTY_DATE)
    res = _svc_orders(db).list_orders(
        customer_query=_DEBTOR,
        actual_delivery_date_from=datetime(2026, 4, 5, 0, 0, 0),
        actual_delivery_date_to=datetime(2026, 4, 5, 23, 59, 59),
    )
    assert res["empty"] is True
    assert res.get("relaxed_axis") == "date"
    alts = res.get("alternatives") or []
    assert alts, "expected nearest-delivery-date alternatives"
    assert len(alts) <= 3  # DATE_RELAX_LIMIT
    for a in alts:
        assert set(a) == {"value", "display", "order_number"}
    # Nearest-first: distances from 2026-04-05 are non-decreasing.
    asked = datetime(2026, 4, 5).date()
    dists = [abs((datetime.fromisoformat(a["value"]).date() - asked).days) for a in alts]
    assert dists == sorted(dists)
    # Distinct dates, all within the debtor's real DO date set.
    assert len({a["value"] for a in alts}) == len(alts)


def test_m4_with_data_date_omits_alternatives(db):
    # AC-R1: a date that has a DO returns the normal shape, no relaxation keys.
    _require_debtor_dates(db, _DEBTOR, (_WITH_DATE,))
    res = _svc_orders(db).list_orders(
        customer_query=_DEBTOR,
        actual_delivery_date_from=datetime(2026, 4, 2, 0, 0, 0),
        actual_delivery_date_to=datetime(2026, 4, 2, 23, 59, 59),
    )
    assert res["empty"] is False
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


def test_m4_no_customer_scope_does_not_relax(db):
    # Gate: without a resolved customer we never dump every debtor's dates.
    res = _svc_orders(db).list_orders(
        actual_delivery_date_from=datetime(2999, 1, 1, 0, 0, 0),
        actual_delivery_date_to=datetime(2999, 1, 1, 23, 59, 59),
    )
    assert res["empty"] is True
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


# --------------------------------------------------------------------------- #
# M5 - product-attachment entity-axis (service layer)
# --------------------------------------------------------------------------- #
def _svc_attachments(db):
    from app.services.product_service import ProductAttachmentService

    return ProductAttachmentService(db)


def test_m5_empty_product_emits_entity_alternatives(db):
    _require_codes(db, _PROD_NO_ATT, _PROD_SIBLING_ATT)
    res = _svc_attachments(db).list_product_attachments(product_id=_PROD_NO_ATT)
    assert res["empty"] is True
    if not res.get("alternatives"):
        pytest.skip(f"{_PROD_SIBLING_ATT} has no non-trashed attachment in this DB")
    assert res.get("relaxed_axis") == "entity"
    values = [a["value"] for a in res["alternatives"]]
    assert _PROD_SIBLING_ATT in values
    for a in res["alternatives"]:
        assert set(a) == {"value", "display", "id", "sim", "is_variant"}


def test_m5_with_data_product_omits_alternatives(db):
    # AC-R1: a product that HAS an attachment returns the normal shape.
    _require_codes(db, _PROD_SIBLING_ATT)
    res = _svc_attachments(db).list_product_attachments(product_id=_PROD_SIBLING_ATT)
    if res["empty"]:
        pytest.skip(f"{_PROD_SIBLING_ATT} unexpectedly has zero attachments")
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


def test_m5_empty_none_when_no_neighbour_has_attachment(db):
    _require_codes(db, _PROD_ISOLATED)
    res = _svc_attachments(db).list_product_attachments(product_id=_PROD_ISOLATED)
    assert res["empty"] is True
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


def test_m5_unresolved_product_is_not_a_data_miss(db):
    # Resolution miss (unknown code) -> plain empty, no entity relaxation.
    res = _svc_attachments(db).list_product_attachments(
        product_id="ZZZ-NOT-A-REAL-CODE-9999"
    )
    assert res["empty"] is True
    assert "alternatives" not in res


# --------------------------------------------------------------------------- #
# HTTP routes: response_model bypass + auth denial
# --------------------------------------------------------------------------- #
def _api_key():
    key = os.environ.get("EXTERNAL_API_KEY")
    if key:
        return key
    try:
        from dotenv import dotenv_values

        return dotenv_values(".env").get("EXTERNAL_API_KEY")
    except Exception:
        return None


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    # No `with` -> lifespan/startup (scheduler, redis) is not triggered.
    return TestClient(app)


def test_orders_route_auth_denial(client):
    r = client.get(
        "/api/v1/order-management/orders/",
        params={"customer_query": _DEBTOR, "actual_delivery_date_from": _EMPTY_DATE},
    )
    assert r.status_code == 401


def test_product_attachments_route_auth_denial(client):
    r = client.get(
        "/api/v1/master-data/product-attachments/",
        params={"product_id": _PROD_NO_ATT},
    )
    assert r.status_code == 401


def test_orders_route_emits_date_alternatives(client, db):
    # Proves the JSONResponse bypass: date-axis alternatives survive the
    # ListResponse response_model on the empty path.
    _require_debtor_dates(db, _DEBTOR, _NEAR_DATES)
    _require_no_debtor_date(db, _DEBTOR, _EMPTY_DATE)
    key = _api_key()
    if not key:
        pytest.skip("EXTERNAL_API_KEY not configured")
    r = client.get(
        "/api/v1/order-management/orders/",
        params={
            "customer_query": _DEBTOR,
            "actual_delivery_date_from": _EMPTY_DATE,
            "actual_delivery_date_to": _EMPTY_DATE,
        },
        headers={"X-API-Key": key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is True
    assert body.get("relaxed_axis") == "date"
    assert body.get("alternatives")


def test_product_attachments_route_emits_entity_alternatives(client, db):
    _require_codes(db, _PROD_NO_ATT, _PROD_SIBLING_ATT)
    key = _api_key()
    if not key:
        pytest.skip("EXTERNAL_API_KEY not configured")
    r = client.get(
        "/api/v1/master-data/product-attachments/",
        params={"product_id": _PROD_NO_ATT},
        headers={"X-API-Key": key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is True
    if not body.get("alternatives"):
        pytest.skip(f"{_PROD_SIBLING_ATT} has no non-trashed attachment in this DB")
    assert body.get("relaxed_axis") == "entity"
