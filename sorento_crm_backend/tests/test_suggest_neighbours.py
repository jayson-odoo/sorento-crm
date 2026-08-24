"""Wave 3c - data-miss neighbour helper + stock / incoming entity-axis wiring.

Covers PLAN-suggest-on-miss-variant-graph.md §3.3 / §3.5 / §7.2:

  AC-N2  data-miss prefers STORED variants (graph) over trigram digit-neighbours.
  AC-N3  the has-data gate drops a no-data neighbour even when highly similar
         (the "8518 rule") - the walk continues to the next neighbour WITH data.
  AC-N4  when no data-bearing neighbour clears SUGGEST_FLOOR -> alternatives == [].
  AC-R1  a with-data (non-empty) result carries NO alternatives / relaxed_axis keys.

The neighbour helper depends on pg_trgm `similarity()` + the persisted variant
graph (`products.variant_of_id`), so these tests hit the live Postgres DB via
DATABASE_URL and skip cleanly when it is unreachable or the referenced real codes
aren't present. Gate/floor MECHANICS are proven deterministically with a STUBBED
`has_data` (depends only on the stable backfilled graph, not on live stock levels);
the endpoint tests assert the wiring against real stock / incoming data.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import entity_resolver as er
from app.services.entity_resolver import find_entity_neighbours_with_data


# --------------------------------------------------------------------------- #
# DB-free: constant is exported + tunable
# --------------------------------------------------------------------------- #
def test_suggest_floor_constant_present():
    assert er.SUGGEST_FLOOR == 0.40


# --------------------------------------------------------------------------- #
# Live-DB fixture (pg_trgm + variant graph). Skips cleanly when unreachable.
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


def _all_data(ids):
    """has_data stub: every candidate has data (isolates ranking/floor)."""
    return set(ids)


def _no_data(ids):
    """has_data stub: nothing has data."""
    return set()


# --------------------------------------------------------------------------- #
# Helper - happy path (real graph, stubbed has_data)
# --------------------------------------------------------------------------- #
def test_helper_returns_variants_ranked_and_capped(db):
    _require_codes(db, "SRTWC8066", "SRTWC8066-SC")
    out = find_entity_neighbours_with_data(db, "SRTWC8066", has_data=_all_data)
    assert out, "expected variant neighbours for SRTWC8066"
    assert len(out) <= 3  # default cap N=3
    # Every returned shape carries the contract keys.
    for a in out:
        assert set(a) == {"value", "display", "id", "sim", "is_variant"}
    # All children are curated variants; sim is non-increasing (variants-first, sim DESC).
    assert all(a["is_variant"] for a in out)
    sims = [a["sim"] for a in out]
    assert sims == sorted(sims, reverse=True)
    # The stored children are prefix-extensions of the base.
    assert all(a["value"].upper().startswith("SRTWC8066") for a in out)


# --------------------------------------------------------------------------- #
# AC-N2 - stored variant beats a trigram-only digit-neighbour
# --------------------------------------------------------------------------- #
def test_ac_n2_stored_variant_ranks_above_trgm_neighbour(db):
    # CB889SS-GM has a stored child CB889SS-GM-DIY (graph, is_variant=True) and a
    # trigram digit-neighbour CB88SS-GM-DIY (is_variant=False). The curated variant
    # must lead.
    _require_codes(db, "CB889SS-GM", "CB889SS-GM-DIY", "CB88SS-GM-DIY")
    out = find_entity_neighbours_with_data(db, "CB889SS-GM", has_data=_all_data, limit=10)
    values = [a["value"] for a in out]
    assert "CB889SS-GM-DIY" in values
    variant_flags = [a["is_variant"] for a in out]
    # No is_variant=False appears before an is_variant=True.
    first_false = variant_flags.index(False) if False in variant_flags else len(variant_flags)
    assert all(variant_flags[:first_false])
    assert not any(variant_flags[first_false:])
    if "CB88SS-GM-DIY" in values:
        assert values.index("CB889SS-GM-DIY") < values.index("CB88SS-GM-DIY")


# --------------------------------------------------------------------------- #
# AC-N3 - has-data gate drops a no-data neighbour (deterministic via stub)
# --------------------------------------------------------------------------- #
def test_ac_n3_has_data_gate_drops_no_data_neighbour(db):
    _require_codes(db, "SRTWC8066", "SRTWC8066-SC")
    # First find the top-ranked candidate with the all-data stub.
    full = find_entity_neighbours_with_data(db, "SRTWC8066", has_data=_all_data, limit=10)
    assert len(full) >= 2
    top_id = full[0]["id"]
    top_value = full[0]["value"]

    # Now gate OUT exactly the top-ranked neighbour: it must NOT be returned, and
    # the next data-bearing neighbour takes its place (the 8518 rule).
    def _all_but_top(ids):
        return {i for i in ids if i != top_id}

    gated = find_entity_neighbours_with_data(db, "SRTWC8066", has_data=_all_but_top, limit=10)
    gated_values = [a["value"] for a in gated]
    assert top_value not in gated_values
    assert gated, "gate must surface the next data-bearing neighbour, not empty"


def test_ac_n3_empty_when_no_neighbour_has_data(db):
    _require_codes(db, "SRTWC8066")
    assert find_entity_neighbours_with_data(db, "SRTWC8066", has_data=_no_data) == []


# --------------------------------------------------------------------------- #
# AC-N4 - distance floor: nearest data-bearing neighbour too far -> []
# --------------------------------------------------------------------------- #
def test_ac_n4_floor_excludes_all(db):
    _require_codes(db, "SRTWC8066")
    # An impossibly-high floor drops every candidate even with data present.
    assert find_entity_neighbours_with_data(
        db, "SRTWC8066", has_data=_all_data, suggest_floor=0.99
    ) == []


def test_ac_n4_below_floor_neighbours_yield_empty(db):
    # ADX-BTE010's only data-bearing neighbour (BT010) is sim ~0.31 < 0.40 floor,
    # so even with the all-data stub the floor yields [].
    _require_codes(db, "ADX-BTE010")
    assert find_entity_neighbours_with_data(db, "ADX-BTE010", has_data=_all_data) == []


def test_helper_unknown_code_returns_empty(db):
    assert find_entity_neighbours_with_data(
        db, "ZZZ-NOT-A-REAL-CODE-9999", has_data=_all_data
    ) == []


# --------------------------------------------------------------------------- #
# Stock endpoint wiring (service layer, live stock data)
# --------------------------------------------------------------------------- #
def test_stock_empty_with_alternatives(db):
    from app.services.inventory_service import StockService

    _require_codes(db, "SRTWC8066", "SRTWC8066-S-NEW")
    res = StockService(db).list_stock(product_id="SRTWC8066", limit=50)
    assert res["empty"] is True
    assert res.get("relaxed_axis") == "entity"
    alts = res.get("alternatives") or []
    assert alts, "expected data-bearing variant alternatives for empty SRTWC8066 stock"
    assert all(a["value"].upper().startswith("SRTWC8066") for a in alts)


def test_stock_empty_no_alternatives(db):
    from app.services.inventory_service import StockService

    _require_codes(db, "ADX-BTE010")
    res = StockService(db).list_stock(product_id="ADX-BTE010", limit=50)
    assert res["empty"] is True
    # Only-below-floor data-bearing neighbours -> no alternatives keys.
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


def test_stock_with_data_has_no_alternatives_keys(db):
    # AC-R1: a non-empty result must not carry the neighbour keys.
    from app.services.inventory_service import StockService

    _require_codes(db, "SRTWC8066-S-NEW")
    res = StockService(db).list_stock(product_id="SRTWC8066-S-NEW", limit=50)
    if res["empty"]:
        pytest.skip("SRTWC8066-S-NEW unexpectedly has zero stock in this DB")
    assert "alternatives" not in res
    assert "relaxed_axis" not in res


# --------------------------------------------------------------------------- #
# Incoming / eta endpoint wiring (service layer, live incoming data)
# --------------------------------------------------------------------------- #
def test_incoming_empty_with_alternatives(db):
    from app.services.incoming_stock_service import IncomingStockService

    _require_codes(db, "CB889SS-GM", "CB889SS-GM-DIY")
    res = IncomingStockService(db).incoming_for_product(product_id="CB889SS-GM", limit=10)
    assert res["empty"] is True
    if not res.get("alternatives"):
        pytest.skip("CB889SS-GM-DIY has no open incoming line in this DB")
    assert res.get("relaxed_axis") == "entity"
    assert any(a["value"] == "CB889SS-GM-DIY" for a in res["alternatives"])


def test_incoming_empty_no_alternatives_for_unresolved(db):
    from app.services.incoming_stock_service import IncomingStockService

    res = IncomingStockService(db).incoming_for_product(
        product_id="ZZZ-NOT-A-REAL-CODE-9999", limit=10
    )
    assert res["empty"] is True
    assert "alternatives" not in res  # resolution miss, not a data miss


# --------------------------------------------------------------------------- #
# Unified incoming-list tool (crm_incoming_stock_list) - same data-miss probe
# --------------------------------------------------------------------------- #
def test_incoming_list_empty_with_alternatives(db):
    from app.services.incoming_stock_service import IncomingStockService

    _require_codes(db, "CB889SS-GM", "CB889SS-GM-DIY")
    res = IncomingStockService(db).incoming_list(product_ids=["CB889SS-GM"], limit=10)
    assert res["empty"] is True
    if not res.get("alternatives"):
        pytest.skip("CB889SS-GM-DIY has no open incoming line in this DB")
    assert res.get("relaxed_axis") == "entity"
    assert any(a["value"] == "CB889SS-GM-DIY" for a in res["alternatives"])


def test_incoming_list_no_alternatives_for_unresolved(db):
    from app.services.incoming_stock_service import IncomingStockService

    res = IncomingStockService(db).incoming_list(
        product_ids=["ZZZ-NOT-A-REAL-CODE-9999"], limit=10
    )
    assert res["empty"] is True
    assert "alternatives" not in res  # resolution miss, not a data miss


# --------------------------------------------------------------------------- #
# Parent / base product is now included in the variant-graph pool
# --------------------------------------------------------------------------- #
def test_parent_base_included_in_neighbours(db):
    from app.models.product import Product

    _require_codes(db, "SRTWC8066", "SRTWC8066-SC")
    # Precondition: SRTWC8066-SC is stored as a variant of the base SRTWC8066.
    child = db.query(Product).filter(Product.product_code == "SRTWC8066-SC").first()
    base = db.query(Product).filter(Product.product_code == "SRTWC8066").first()
    if not (child and base and str(child.variant_of_id) == str(base.id)):
        pytest.skip("SRTWC8066-SC is not linked to base SRTWC8066 in this DB")

    # Querying from the CHILD, its parent/base must be offered as an alternative.
    out = find_entity_neighbours_with_data(db, "SRTWC8066-SC", has_data=_all_data, limit=10)
    values = [a["value"] for a in out]
    assert "SRTWC8066" in values, "parent/base should be a suggested alternative"


# --------------------------------------------------------------------------- #
# HTTP route: response_model bypass + auth denial
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


def test_stock_route_auth_denial(client):
    r = client.get("/api/v1/inventory/stock/balance?product_id=SRTWC8066")
    assert r.status_code == 401


def test_incoming_route_auth_denial(client):
    r = client.get("/api/v1/incoming-stock/by-product?product_id=CB889SS-GM")
    assert r.status_code == 401


def test_stock_route_emits_alternatives(client, db):
    # Proves the JSONResponse bypass: alternatives survive the ListResponse
    # response_model on the data-miss path.
    _require_codes(db, "SRTWC8066")
    key = _api_key()
    if not key:
        pytest.skip("EXTERNAL_API_KEY not configured")
    r = client.get(
        "/api/v1/inventory/stock/balance",
        params={"product_id": "SRTWC8066", "exclude_zero_system_adjustment": "true"},
        headers={"X-API-Key": key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is True
    assert body.get("relaxed_axis") == "entity"
    assert body.get("alternatives")


def test_stock_route_with_data_omits_alternatives(client, db):
    # AC-R1 at the HTTP layer: with-data response is the normal ListResponse
    # shape (no alternatives / relaxed_axis keys).
    _require_codes(db, "SRTWC8066-S-NEW")
    key = _api_key()
    if not key:
        pytest.skip("EXTERNAL_API_KEY not configured")
    r = client.get(
        "/api/v1/inventory/stock/balance",
        params={"product_id": "SRTWC8066-S-NEW", "exclude_zero_system_adjustment": "true"},
        headers={"X-API-Key": key},
    )
    assert r.status_code == 200
    body = r.json()
    if body["empty"]:
        pytest.skip("SRTWC8066-S-NEW unexpectedly has zero stock in this DB")
    assert "alternatives" not in body
    assert "relaxed_axis" not in body
