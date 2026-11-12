"""TOWN-PROJECT-CITY Phase 2 (red): `redact()` and `strip_names()` over the project sections.

Contract: PLAN-town-project-city-11nov.md "Phase 2 contract" (Redacted variant, Wallboard). Pure
dict tests, plus one real build through both variants.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust
from tests.town._town_project_seed import full_with_projects, funnel, link_trading_house, project
from tests.town._town_seed import DAY, NOW, dealer_doc, deep, project_doc

OPAQUE = re.compile(r"s[0-9a-f]{12}")
SPLIT_AMOUNTS = ("400111.10", "100222.20", "12012.30")


def _ident(site: dict) -> tuple:
    """What survives redaction and identifies a site: stage, state, dates (distinct per site)."""
    return (site["stage"], site["state"], site["launch_date"], site["delivery_date"], site["final_negotiation"])


# ------------------------------------------------------------------------------ redact


def test_redact_drops_split_amounts_and_keeps_counts():
    from app.services.town.snapshot import redact

    out = redact(full_with_projects())
    assert out["today"]["split"] == {
        "dealer": {"invoice_count": 200}, "project": {"invoice_count": 100}, "other": {"invoice_count": 21},
    }
    text = json.dumps(out)
    for figure in SPLIT_AMOUNTS:
        assert figure not in text


def test_redact_drops_site_name_code_and_value_keeps_the_rest():
    from app.services.town.snapshot import redact

    full = full_with_projects()
    out = redact(full)
    assert len(out["projects"]["sites"]) == 12
    for site in out["projects"]["sites"]:
        assert set(site) == {"key", "stage", "final_negotiation", "state", "launch_date", "delivery_date"}
    assert {k: out["projects"][k] for k in ("open_count", "more", "dormant")} == {
        "open_count": 15, "more": 3, "dormant": 2}
    text = json.dumps(out)
    for site in full["projects"]["sites"]:
        assert site["name"] not in text and site["code"] not in text
        assert site["estimated_value"] not in text and site["key"] not in text


def test_redact_site_keys_are_opaque_unique_and_stable_for_the_day():
    from app.services.town.snapshot import opaque_key, redact

    full = full_with_projects()
    keys = [s["key"] for s in redact(full)["projects"]["sites"]]
    assert len(set(keys)) == len(keys)
    assert all(OPAQUE.fullmatch(k) for k in keys)
    assert set(keys) == {opaque_key(full, s["key"]) for s in full["projects"]["sites"]}
    later = deep(full)
    later["projects"]["sites"].append({**later["projects"]["sites"][0], "key": "ZZT-late-site", "launch_date": "2031-01-01"})
    again = {_ident(s): s["key"] for s in redact(later)["projects"]["sites"] if s["key"] in keys}
    first = {_ident(s): s["key"] for s in redact(full)["projects"]["sites"]}
    assert all(first[ident] == key for ident, key in again.items())
    other_day = {**full, "day": "2026-11-04"}
    assert not (set(keys) & {s["key"] for s in redact(other_day)["projects"]["sites"]})


def test_redact_sites_are_not_in_value_order_and_do_not_depend_on_input_order():
    from app.services.town.snapshot import redact

    full = full_with_projects(n_sites=12)  # input is by value, descending
    value_order = [_ident(s) for s in full["projects"]["sites"]]
    got = [_ident(s) for s in redact(full)["projects"]["sites"]]
    assert sorted(got, key=str) == sorted(value_order, key=str)
    assert got != value_order
    shuffled = deep(full)
    random.Random(7).shuffle(shuffled["projects"]["sites"])
    assert [_ident(s) for s in redact(shuffled)["projects"]["sites"]] == got  # a hash order, not a sort of input


def test_redact_trading_houses_lose_name_and_get_opaque_keys():
    from app.services.town.snapshot import redact

    full = full_with_projects()
    out = redact(full)
    rows = out["trading_houses"]["rows"]
    assert out["trading_houses"]["more"] == 1
    assert len(rows) == 3
    for row in rows:
        assert set(row) == {"key", "state", "open_projects", "today_docs"}
        assert OPAQUE.fullmatch(row["key"])
    assert len({r["key"] for r in rows}) == 3
    text = json.dumps(out)
    for original in full["trading_houses"]["rows"]:
        assert original["name"] not in text and original["key"] not in text


def test_redact_trading_house_keys_are_stable_for_the_day():
    from app.services.town.snapshot import opaque_key, redact

    full = full_with_projects()
    got = {r["key"] for r in redact(full)["trading_houses"]["rows"]}
    assert got == {opaque_key(full, r["key"]) for r in full["trading_houses"]["rows"]}


def test_redact_leaves_input_untouched_with_project_sections():
    from app.services.town.snapshot import redact, strip_names

    full = full_with_projects()
    before = deep(full)
    redact(full)
    strip_names(full)
    assert full == before


def test_redact_tolerates_an_older_snapshot_without_project_sections():
    from app.services.town.snapshot import redact, strip_names
    from tests.town._town_seed import fake_full

    for variant in (redact, strip_names):
        out = variant(fake_full())
        assert "projects" not in out and "trading_houses" not in out


# ------------------------------------------------------------------------------ wallboard


def test_strip_names_drops_site_name_code_value_and_trading_house_names():
    from app.services.town.snapshot import strip_names

    full = full_with_projects()
    out = strip_names(full)
    for site in out["projects"]["sites"]:
        assert set(site) == {"key", "stage", "final_negotiation", "state", "launch_date", "delivery_date"}
        assert OPAQUE.fullmatch(site["key"])
    for row in out["trading_houses"]["rows"]:
        assert "name" not in row and OPAQUE.fullmatch(row["key"])
        assert {"state", "open_projects", "today_docs"} <= set(row)
    text = json.dumps(out)
    for site in full["projects"]["sites"]:
        assert site["name"] not in text and site["code"] not in text and site["key"] not in text
        assert site["estimated_value"] not in text
    for row in full["trading_houses"]["rows"]:
        assert row["name"] not in text and row["key"] not in text


def test_strip_names_keeps_counts_stage_state_dates_and_flags():
    from app.services.town.snapshot import strip_names

    full = full_with_projects()
    out = strip_names(full)
    assert out["projects"]["open_count"] == full["projects"]["open_count"]
    assert out["projects"]["more"] == 3 and out["projects"]["dormant"] == 2
    assert [_ident(s) for s in out["projects"]["sites"]] == [_ident(s) for s in full["projects"]["sites"]]
    assert [r["open_projects"] for r in out["trading_houses"]["rows"]] == [5, 4, 3]
    assert all(OPAQUE.fullmatch(s["key"]) for s in out["projects"]["sites"])


def test_strip_names_amounts_follow_the_viewers_variant():
    from app.services.town.snapshot import redact, strip_names

    full = full_with_projects()
    assert strip_names(full)["today"]["split"] == full["today"]["split"]  # full viewer on a wallboard
    personal = json.dumps(strip_names(redact(full)))
    for figure in SPLIT_AMOUNTS:
        assert figure not in personal


def test_redact_then_strip_names_keeps_site_keys():
    from app.services.town.snapshot import redact, strip_names

    full = full_with_projects()
    assert all(OPAQUE.fullmatch(s["key"]) for s in redact(full)["projects"]["sites"])
    assert [s["key"] for s in strip_names(redact(full))["projects"]["sites"]] == [
        s["key"] for s in redact(full)["projects"]["sites"]]


# ------------------------------------------------------------------------------ a real build


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def test_real_build_through_both_variants_leaks_no_project_identity(db):
    from app.services.town.snapshot import build_snapshot, redact, strip_names

    ids = funnel(db)
    proj = project(db, ids, code="ZZT-LEAK-CODE", name="ZZT Leak Tower", state="Johor", value="7654321.00",
                   launch=date(2026, 1, 1), delivery_from=date(2028, 1, 1))
    th = cust(db, name="ZZT Leak Trading House")
    link_trading_house(db, proj, th)
    project_doc(db, th, "4242.42", DAY)
    dealer_doc(db, cust(db), "100.00", DAY)
    full = build_snapshot(db, DEFAULT_COMPANY_ID, DAY, now=NOW)
    assert full["projects"]["sites"][0]["name"] == "ZZT Leak Tower"  # the full variant has it
    for variant in (redact(full), strip_names(redact(full))):
        text = json.dumps(variant)
        for secret in ("ZZT-LEAK-CODE", "ZZT Leak Tower", "7654321", "ZZT Leak Trading House", proj.id, str(th.id),
                       "4242.42"):
            assert secret not in text
        assert variant["projects"]["sites"][0]["state"] == "Johor"
        assert OPAQUE.fullmatch(variant["projects"]["sites"][0]["key"])
        assert OPAQUE.fullmatch(variant["trading_houses"]["rows"][0]["key"])
    wallboard = json.dumps(strip_names(full))
    assert "ZZT-LEAK-CODE" not in wallboard and "ZZT Leak Tower" not in wallboard
    assert "ZZT Leak Trading House" not in wallboard and "7654321" not in wallboard


# ------------------------------------------------- security review (11 Nov): ordering must not identify rows


def test_redacted_sites_follow_their_opaque_keys_not_the_raw_ids():
    """An unkeyed hash of the raw project id would let anyone holding project ids rebuild the order
    and match each site to its project: the order is the opaque keys' own (keyed, new every day)."""
    from tests.town._town_project_seed import full_with_projects

    from app.services.town.snapshot import redact

    out = redact(full_with_projects(n_sites=12, n_houses=3))
    keys = [s["key"] for s in out["projects"]["sites"]]
    assert keys == sorted(keys)


def test_trading_houses_go_by_their_count_then_opaque_key_never_by_customer_code():
    from tests.town._town_project_seed import full_with_projects

    from app.services.town.snapshot import redact, strip_names

    snap = full_with_projects(n_sites=4, n_houses=4)
    for row in snap["trading_houses"]["rows"]:
        row["open_projects"] = 2
    for variant in (redact(snap), strip_names(snap)):
        rows = variant["trading_houses"]["rows"]
        assert [r["key"] for r in rows] == sorted(r["key"] for r in rows)
