"""CHAT-SLIM-INDEX S3, red tests: brands, promotion kinds, locations, salespeople, visibility, warm-up.

Contract: PLAN-chat-lookup-lists-25oct.md "S3 code contract" + "Access scoping". AC-9, AC-10 (no customers), AC-11 (brand list).
Sources the rows must come from today (cited for the coder):
- brands: turn_runtime.active_brands (turn_runtime.py:543) + brand_alias words; label as context.known_brands_line spells it.
- promotion kinds: turn_runtime.promotion_kind_rows (turn_runtime.py:814).
- locations: active `warehouses` (models/inventory.py:26), company scoped by the session.
- salespeople: `sales_agents.sales_agent` (reports/ask.py:159; models/sales_agent.py): code, person_label, aliases; shared rows have NULL company.
Assumed: `load_rows(db)` returns the S3 rows too; `warm(rows, embed)` (module `lookup_lists`) starts a daemon thread and returns.
Postgres only, fake names (ZZ prefix).
"""
from __future__ import annotations

import threading
import time
import uuid

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.marketing import PromotionType
from app.models.product import Brand
from app.models.sales_agent import SalesAgent
from app.services.chatbot import turn_runtime
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.turn import context as context_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped

HDR = {
    "brand": "Brand candidates (pick one only if the message means it):",
    "promotion_kind": "Promotion kind candidates (pick one only if the message means it):",
    "salesperson": "Salesperson candidates (pick one only if the message means it):",
    "location": "Location candidates (pick one only if the message means it):",
}
BRAND_NAME, BRAND_CODE, BRAND_ALIAS = "ZZSORENTO", "ZZSRT", "zzsrtalias"


def seed_world3(session_factory) -> None:
    db = session_factory()
    brand = Brand(id=str(uuid.uuid4()), brand_code=BRAND_CODE, brand_name=BRAND_NAME, is_active=True, company_id=DEFAULT_COMPANY_ID)
    ghost = Brand(id=str(uuid.uuid4()), brand_code="ZZGHOST", brand_name="ZZGhostbrand", is_active=False, company_id=DEFAULT_COMPANY_ID)
    s = LookupSet(id=str(uuid.uuid4()), set_key="brand_alias", name="Brand Alias")
    db.add_all([brand, ghost, s])
    db.flush()
    o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=BRAND_CODE, label=BRAND_CODE, sort_order=0)
    db.add(o)
    db.flush()
    db.add(LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword=BRAND_ALIAS))
    db.add_all([
        PromotionType(id=str(uuid.uuid4()), type_code="a3_flyer", type_name="A3 Flyer"),
        PromotionType(id=str(uuid.uuid4()), type_code="focus_item", type_name="Focus Item"),
        Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZBRW", warehouse_name="ZZ Bravo Warehouse", is_active=True, company_id=DEFAULT_COMPANY_ID),
        Warehouse(id=str(uuid.uuid4()), warehouse_code="ZZOLD", warehouse_name="ZZ Closed Depot", is_active=False, company_id=DEFAULT_COMPANY_ID),
        SalesAgent(id=str(uuid.uuid4()), sales_agent="ZZ SEAN I", person_label="ZZ Sean", aliases="Seany, Shawn", is_active=True),
        SalesAgent(id=str(uuid.uuid4()), sales_agent="ZZ RETIRED", person_label="ZZ Retired", is_active=False),
    ])
    db.commit()


def brand_label(db) -> str:
    """The label today's Known brands line gives the seeded brand."""
    rows = [r for r in turn_runtime.active_brands(db) if r["brand_name"] == BRAND_NAME]
    return context_mod.known_brands_line(rows).removeprefix("Known brands: ")


def labels(hits: dict, name: str) -> list[str]:
    return [h.row.label for h in hits.get(name, [])]


def _hit(list_name: str, label: str) -> ll.Hit:
    return ll.Hit(ll.LookupRow(list_name, label, label, (label,)), "x", 1.0, 0.0)


# ------------------------------------------------------------------ constants and render


def test_s3_header_nouns_top_k_and_headers():
    for name, noun, k in (("brand", "Brand", 3), ("salesperson", "Salesperson", 5), ("location", "Location", 5),
                          ("promotion_kind", "Promotion kind", 3)):
        assert ll.HEADER_NOUN[name] == noun and ll.TOP_K[name] == k, name
        assert ll.header(name) == HDR[name]


def test_render_order_includes_the_s3_lists():
    names = ("sales_channel", "location", "salesperson", "promotion_kind", "brand", "file_type", "spec", "category")
    out = ll.render({n: [_hit(n, f"{n} one")] for n in names})
    assert [ln for ln in out if not ln.startswith("- ")] == [
        ll.header(n) for n in ("category", "spec", "file_type", "brand", "promotion_kind", "salesperson", "location", "sales_channel")
    ]


# ------------------------------------------------------------------ brands


def test_brand_rows_use_the_known_brands_label_and_match_code_alias_and_name(session_factory):
    seed_world3(session_factory)
    db = scoped(session_factory)
    want = brand_label(db)
    assert want.startswith(BRAND_NAME) and BRAND_CODE in want and BRAND_ALIAS in want, want
    rows = ll.load_rows(db)
    for word in (BRAND_CODE.lower(), BRAND_ALIAS, BRAND_NAME.lower()):
        assert labels(ll.shortlist(f"{word} basin", rows, None), "brand") == [want], word


def test_an_inactive_brand_is_never_offered(session_factory):
    seed_world3(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    assert labels(ll.shortlist("zzghostbrand zzghost", rows, None), "brand") == []
    assert not any("ghost" in r.label.casefold() for r in rows if r.list_name == "brand")


def test_brand_lookup_never_offers_a_brand_the_known_brands_line_would_not(session_factory):
    seed_world3(session_factory)
    db = scoped(session_factory)
    today = {r["brand_name"] for r in turn_runtime.active_brands(db)}
    offered = {r.label.split(" (")[0] for r in ll.load_rows(db) if r.list_name == "brand"}
    assert offered and offered <= today, (offered, today)


def test_brand_and_location_rows_follow_the_session_company_scope(session_factory):
    seed_world3(session_factory)
    db = session_factory()
    set_company_scope(db, frozenset({str(uuid.uuid4())}))
    rows = ll.load_rows(db)
    assert not [r for r in rows if r.list_name in ("brand", "location")], [r.label for r in rows if r.list_name in ("brand", "location")]


# ------------------------------------------------------------------ promotion kinds


def test_promotion_kind_label_carries_the_type_code(session_factory):
    seed_world3(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    assert labels(ll.shortlist("a3 flyer", rows, None), "promotion_kind") == ["a3_flyer (A3 Flyer)"]
    assert labels(ll.shortlist("focus item", rows, None), "promotion_kind") == ["focus_item (Focus Item)"]
    kinds = {r.label for r in rows if r.list_name == "promotion_kind"}
    assert kinds == {"a3_flyer (A3 Flyer)", "focus_item (Focus Item)"}


# ------------------------------------------------------------------ locations


def test_location_label_is_name_and_code_and_a_code_alone_offers_it(session_factory):
    seed_world3(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    for message in ("zzbrw", "stock at zz bravo warehouse"):
        assert labels(ll.shortlist(message, rows, None), "location") == ["ZZ Bravo Warehouse (ZZBRW)"], message


def test_an_inactive_warehouse_is_never_offered(session_factory):
    seed_world3(session_factory)
    rows = ll.load_rows(scoped(session_factory))
    assert labels(ll.shortlist("zzold zz closed depot", rows, None), "location") == []


# ------------------------------------------------------------------ salespeople


def test_salesperson_by_code_person_alias_and_typo_and_never_an_inactive_one(session_factory):
    seed_world3(session_factory)
    rows = ll.load_rows(scoped(session_factory), include_salespeople=True)
    for message in ("zz sean i", "zz sean", "seany", "zz seen i"):
        assert labels(ll.shortlist(message, rows, None), "salesperson") == ["ZZ SEAN I"], message
    assert labels(ll.shortlist("zz retired", rows, None), "salesperson") == []


# ------------------------------------------------------------------ one span one list (brand list itself)


def test_a_brand_word_feeds_no_category_row_through_load_rows(session_factory):
    from app.models.product import ProductCategory

    seed_world3(session_factory)
    db = session_factory()
    db.add(ProductCategory(id=str(uuid.uuid4()), category_code=BRAND_CODE, category_name=BRAND_CODE, class_label=BRAND_CODE,
                           search_synonyms=[], is_searchable=True, company_id=DEFAULT_COMPANY_ID))
    db.commit()
    scope = scoped(session_factory)
    hits = ll.shortlist("zzsrt a3 flyer", ll.load_rows(scope), None, brand_words=ll.brand_words(scope))
    assert labels(hits, "category") == [] and len(labels(hits, "brand")) == 1, hits


# ------------------------------------------------------------------ warm-up


def test_warm_returns_at_once_and_embeds_in_the_background(session_factory):
    rows = [ll.LookupRow("brand", f"b{i}", f"Brand {i}", (f"brand {i}",)) for i in range(3)]
    started, release = threading.Event(), threading.Event()

    def slow(texts):
        started.set()
        release.wait(5)
        return [[1.0] + [0.0] * 7 for _ in texts]

    t0 = time.monotonic()
    ll.warm(rows, slow)
    assert time.monotonic() - t0 < 0.5, "warm must not wait for the embedder"
    assert started.wait(2), "the embedder was never called in the background"
    release.set()


def test_warm_swallows_an_embedder_failure():
    def boom(texts):
        raise RuntimeError("zz embedding down")

    ll.warm([ll.LookupRow("brand", "b", "Brand", ("brand",))], boom)
    time.sleep(0.2)


def test_load_rows_default_returns_no_salesperson_rows(session_factory):
    seed_world3(session_factory)
    assert not [r for r in ll.load_rows(scoped(session_factory)) if r.list_name == "salesperson"]
