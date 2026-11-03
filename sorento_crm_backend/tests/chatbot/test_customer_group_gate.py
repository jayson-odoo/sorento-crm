"""CUSTOMER-GROUP-GATE: the chatbot's which-one lists apply the office's explicit customer groups,
and nothing else joins ledgers.

Bug (found by SALES-ACCOUNT-TYPE, #2105): `gate._cust_base` stripped the `[A/C ..]` account
suffix BEFORE asking `customer_group_of`, which answers only by the exact FULL ledger name. So no
suffixed ledger ever reached its group and every ledger fell to the name rule: on the dev copy
all 8 FULLSHUN ledgers, grouped or not, became one name-rule family.

Owner ruling (CUSTOMER-GROUP, 2 Oct 2026, restated by crew 3 Nov 2026 for this lane): explicit,
staff-set groups only. So, for every which-one list:
- the ledgers the office put in ONE group are one entry (looked up by the customer's id, or its
  exact full name when no id is at hand);
- a group is per company: a group name that exists in two companies is two entries, never one;
- an ungrouped ledger is its OWN entry, never bundled with others by trading name;
- two rows with the same full name, one grouped and one not, are two entries.

Name matching stays for SEARCH only (what a typed word matches), never for joining ledgers.

The gate decides the customer picker for the domains whose matrix allows a customer (`order`:
DO and outstanding asks, `sales`); the stock list's roster is the narrower's
(`turn/narrow.py`, the same builder the gate's picker prints through). Fake ZZT names only.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.services import ledger_family as lf
from app.services.chatbot.lanes.business import gate
from app.services.chatbot.lanes.business.gate import run_gate
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._pg_fixture import blank_session, unique_code
from tests.test_customer_header_echo import seed_ledgers

NAME = "ZZTFULL SANITARYWARE SDN BHD"
G1 = f"{NAME} - [A/C I]"  # SRT, grouped
G2 = f"{NAME} [A/C II]"  # SRT, grouped
U1 = f"{NAME} - [A/C III]"  # SRT, ungrouped
U2 = f"{NAME} - [IBORN]"  # SRT, ungrouped
DUP = f"{NAME} - [CERAMIC]"  # SRT, twice: once grouped, once not
M1 = f"{NAME} - [A/C I]"  # MCH, in MCH's own group of the same name (same full name as G1)
OTHER = "ZZTFULL TILES SDN BHD - [A/C I]"  # SRT, ungrouped, another trading name


@pytest.fixture(scope="module")
def world():
    """The ledgers in two companies, the turn's group maps as the engine loads them, and one
    resolver match per ledger. Read once; the maps are plain dicts."""
    from app.services.customer_group_service import family_ids, family_overrides

    with blank_session() as db:
        mch = str(uuid.uuid4())
        db.execute(
            text("INSERT INTO companies (id, name, code, is_active) VALUES (:i, 'ZZT MCH', :c, true)"),
            {"i": mch, "c": unique_code("ZM")[:10]},
        )
        srt_code = db.execute(text("SELECT code FROM companies WHERE id = :i"), {"i": DEFAULT_COMPANY_ID}).scalar()
        mch_code = db.execute(text("SELECT code FROM companies WHERE id = :i"), {"i": mch}).scalar()
        srt_ids = seed_ledgers(
            db, [(G1, NAME), (G2, NAME), (U1, None), (U2, None), (DUP, NAME), (DUP, None), (OTHER, None)]
        )
        (m1_id,) = seed_ledgers(db, [(M1, NAME)], company_id=mch)
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, mch}))
        names, ids = family_overrides(db), family_ids(db)

    def match(uid: str, name: str, code: str) -> dict[str, Any]:
        return {
            "entity_type": "customer",
            "uuid": uid,
            "canonical_code": f"ZZT-{uid[:6]}",
            "company_code": code,
            "display": {"customer_name": name},
        }

    labels = ["G1", "G2", "U1", "U2", "DUP_G", "DUP_U", "OTHER"]
    rows = {k: match(u, n, srt_code) for k, u, n in zip(labels, srt_ids, (G1, G2, U1, U2, DUP, DUP, OTHER))}
    rows["M1"] = match(m1_id, M1, mch_code)
    return {"names": names, "ids": ids, "rows": rows, "srt": srt_code, "mch": mch_code}


EXPECTED = [{"G1", "G2", "DUP_G"}, {"M1"}, {"U1"}, {"U2"}, {"DUP_U"}, {"OTHER"}]


def _norm(families: list[set[str]]) -> list[frozenset[str]]:
    return sorted((frozenset(f) for f in families), key=sorted)


# ============================================================ the loaders


def test_the_id_map_holds_every_grouped_ledger_and_no_ungrouped_one(world):
    ids, rows = world["ids"], world["rows"]
    for k in ("G1", "G2", "DUP_G", "M1"):
        assert rows[k]["uuid"] in ids, k
    for k in ("U1", "U2", "DUP_U", "OTHER"):
        assert rows[k]["uuid"] not in ids, k


def test_a_group_name_in_two_companies_is_two_groups(world):
    ids, rows = world["ids"], world["rows"]
    assert ids[rows["G1"]["uuid"]] != ids[rows["M1"]["uuid"]]
    assert world["srt"] in ids[rows["G1"]["uuid"]]
    assert world["mch"] in ids[rows["M1"]["uuid"]]


def test_a_full_name_in_two_groups_or_in_a_group_and_none_is_left_out_of_the_name_map(world):
    names = world["names"]
    assert lf.normalise_customer_name(G1) not in names  # SRT group and MCH group
    assert lf.normalise_customer_name(DUP) not in names  # a group and none
    assert names[lf.normalise_customer_name(G2)]


# ============================================================ the grouping key


def test_cust_base_finds_the_group_of_a_suffixed_ledger_by_its_full_name():
    with lf.customer_groups({G2: NAME}):
        assert gate._cust_base({"display": {"customer_name": G2}}) == lf.group_key(NAME)


def test_ungrouped_ledgers_of_one_trading_name_are_not_joined_without_any_groups():
    keys = {gate._cust_base({"display": {"customer_name": n}}) for n in (G1, G2, U1, U2)}
    assert len(keys) == 4


def test_cust_base_and_ledger_family_key_agree_on_every_row(world):
    with lf.customer_groups(world["names"], ids=world["ids"]):
        for k, m in world["rows"].items():
            assert gate._cust_base(m) == lf.ledger_family_key(m["display"]["customer_name"], m["uuid"]), k


def test_the_trading_name_key_still_matches_what_a_user_typed():
    """Search keeps the name rule: "zztfull sanitaryware" names every ledger of that name."""
    assert {lf.trading_name_key(n) for n in (G1, G2, U1, U2, DUP)} == {lf.trading_name_key("zztfull sanitaryware")}


# ============================================================ per domain's which-one list


def _gate(world, domain: str, intent: str, **parser_extra: Any) -> dict[str, Any]:
    rows = list(world["rows"].values())
    resolver = {"resolutions": [{"token": "zztfull", "matches": rows}], "unresolved_tokens": []}
    parser = {
        "domain_hint": domain,
        "intent_hint": intent,
        "entities": [{"raw": "zztfull", "hint": "customer", "current_message": True, "confident": True}],
        **parser_extra,
    }
    with lf.customer_groups(world["names"], ids=world["ids"]):
        return run_gate(dict(resolver), parser=parser, resolver=resolver)


@pytest.mark.parametrize(
    ("domain", "intent", "extra"),
    [
        pytest.param("order", "check_order", {}, id="do"),
        pytest.param("order", "check_order", {"order_status": "outstanding"}, id="outstanding"),
        pytest.param("sales", "sales_report", {}, id="sales"),
    ],
)
def test_gate_which_one_list_has_one_entry_per_group_and_per_ungrouped_ledger(world, domain, intent, extra):
    out = _gate(world, domain, intent, **extra)
    key_of = {m["uuid"]: k for k, m in world["rows"].items()}
    families = [{key_of[u] for u in uuids} for uuids in (out.get("picker_families") or {}).values()]
    assert _norm(families) == _norm(EXPECTED), families
    assert out.get("require_specific") is True


def _roster(world) -> list[dict[str, Any]]:
    from app.services.chatbot.turn.narrow import customer_options

    cands = [
        {
            "raw": m["display"]["customer_name"],
            "name": m["display"]["customer_name"],
            "uuid": m["uuid"],
            "canonical_code": m["canonical_code"],
            "company_codes": [m["company_code"]],
        }
        for m in world["rows"].values()
    ]
    with lf.customer_groups(world["names"], ids=world["ids"]):
        return customer_options(cands, cap=50)


def test_stock_which_one_list_has_one_entry_per_group_and_per_ungrouped_ledger(world):
    options = _roster(world)
    key_of = {m["uuid"]: k for k, m in world["rows"].items()}
    families = [{key_of[u] for u in o["uuids"]} for o in options]
    assert _norm(families) == _norm(EXPECTED), [o["label"] for o in options]


def test_the_list_names_each_group_once_per_company_and_each_ungrouped_ledger_in_full(world):
    labels = [o["label"] for o in _roster(world)]
    srt, mch = world["srt"], world["mch"]
    assert f"{NAME} ({srt})" in labels, labels
    assert f"{NAME} ({mch})" in labels, labels
    for name in (U1, U2, OTHER):
        assert f"{name} ({srt})" in labels, labels
    # a company tag is printed once, never twice
    assert not any(label.endswith(f"({srt}) ({srt})") or label.endswith(f"({mch}) ({mch})") for label in labels)
