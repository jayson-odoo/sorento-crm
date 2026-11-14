"""CUSTOMER-GROUP-GATE (re-landed with the owner's 9 Nov 2026 ruling): the chatbot's lists apply the
office's explicit customer groups, and same-name ledgers are one customer.

Bug (found by SALES-ACCOUNT-TYPE, #2105): `gate._cust_base` stripped the `[A/C ..]` account
suffix BEFORE asking `customer_group_of`, which answers only by the exact FULL ledger name. So no
suffixed ledger ever reached its group and every ledger fell to the name rule: on the dev copy
all 8 FULLSHUN ledgers, grouped or not, became one name-rule family.

Owner ruling, 9 Nov 2026 (replacing the 3 Nov "explicit links only" reading for answers): "it should
just answer by the group, the user doesn't care about which account la, we should just return all
accounts"; Q1: "we should treat it as part of group also ... we should be more lenient"; crew Q2 (a).
So, for every list:
- the ledgers the office put in ONE group are one entry (looked up by the customer's id, or its
  exact full name when no id is at hand: #2144's fix);
- ledgers of one trading name are one entry, grouped or not, and an ungrouped ledger of a group's
  trading name is that group's entry (answer-time only: no data link is written);
- a group name in both companies is one entry (the bot never asks "Sorento or Mocha?");
- different trading names stay different entries, so the bot still asks between two shops;
- scope is the asker's: an entry covers only the rows the resolver returned for this asker.

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


EXPECTED = [{"G1", "G2", "DUP_G", "M1", "U1", "U2", "DUP_U"}, {"OTHER"}]


def _norm(families: list[set[str]]) -> list[frozenset[str]]:
    return sorted((frozenset(f) for f in families), key=sorted)


# ============================================================ the loaders


def test_the_id_map_holds_every_grouped_ledger_and_no_ungrouped_one(world):
    ids, rows = world["ids"], world["rows"]
    for k in ("G1", "G2", "DUP_G", "M1"):
        assert rows[k]["uuid"] in ids, k
    for k in ("U1", "U2", "DUP_U", "OTHER"):
        assert rows[k]["uuid"] not in ids, k


def test_a_group_name_in_two_companies_is_one_group_name(world):
    """Crew Q2 (a), 9 Nov 2026: no company tag on the group's name, so the two groups are one customer."""
    ids, rows = world["ids"], world["rows"]
    assert ids[rows["G1"]["uuid"]] == ids[rows["M1"]["uuid"]] == NAME


def test_a_full_name_in_two_groups_or_in_a_group_and_none_is_left_out_of_the_name_map(world):
    names = world["names"]
    assert lf.normalise_customer_name(G1) not in names  # SRT group and MCH group
    assert lf.normalise_customer_name(DUP) not in names  # a group and none
    assert names[lf.normalise_customer_name(G2)]


# ============================================================ the grouping key


def test_cust_base_finds_the_group_of_a_suffixed_ledger_by_its_full_name():
    with lf.customer_groups({G2: NAME}):
        assert gate._cust_base({"display": {"customer_name": G2}}) == lf.group_key(NAME)


def test_ungrouped_ledgers_of_one_trading_name_are_one_entry_without_any_groups():
    keys = {gate._cust_base({"display": {"customer_name": n}}) for n in (G1, G2, U1, U2)}
    assert len(keys) == 1
    assert gate._cust_base({"display": {"customer_name": OTHER}}) not in keys


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
def test_gate_which_one_list_has_one_entry_per_trading_name_or_group(world, domain, intent, extra):
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


def test_stock_which_one_list_has_one_entry_per_trading_name_or_group(world):
    options = _roster(world)
    key_of = {m["uuid"]: k for k, m in world["rows"].items()}
    families = [{key_of[u] for u in o["uuids"]} for o in options]
    assert _norm(families) == _norm(EXPECTED), [o["label"] for o in options]


def test_the_list_names_the_group_once_with_both_company_codes_and_the_other_shop(world):
    labels = [o["label"] for o in _roster(world)]
    srt, mch = world["srt"], world["mch"]
    assert len(labels) == 2, labels
    (group_line,) = [label for label in labels if label.startswith(NAME)]
    assert srt in group_line and mch in group_line, labels
    assert any(label.startswith(OTHER) for label in labels), labels
    # a company tag is printed once, never twice
    assert not any(label.endswith(f"({srt}) ({srt})") or label.endswith(f"({mch}) ({mch})") for label in labels)


# ============================================================ identical vs near-identical names across companies


def test_identical_and_near_identical_names_across_companies_are_one_customer_never_asked():
    """Owner 3 Nov R2 on #2105 (never ask "Sorento or Mocha?") and the 9 Nov ruling ("return all accounts", "be more
    lenient"): the same name in both books, another marker or other punctuation are ONE customer. No question; the
    answer covers all four ledgers."""
    srt, mch, near_a, near_b = (str(uuid.uuid4()) for _ in range(4))
    rows = [
        {"entity_type": "customer", "uuid": srt, "company_code": "SRT", "display": {"customer_name": "ZZT CRAFT SDN BHD"}},
        {"entity_type": "customer", "uuid": mch, "company_code": "MCH", "display": {"customer_name": "ZZT  craft sdn bhd"}},
        {"entity_type": "customer", "uuid": near_a, "company_code": "MCH", "display": {"customer_name": "ZZT CRAFT SDN. BHD."}},
        {"entity_type": "customer", "uuid": near_b, "company_code": "SRT", "display": {"customer_name": "ZZT CRAFT SDN BHD - [A/C I]"}},
    ]
    resolver = {"resolutions": [{"token": "zzt craft", "matches": rows}], "unresolved_tokens": []}
    parser = {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [{"raw": "zzt craft", "hint": "customer", "current_message": True, "confident": True}],
    }
    out = run_gate(dict(resolver), parser=parser, resolver=resolver)
    assert out.get("require_specific") is not True, out.get("gate_reason")
    assert not out.get("picker_families"), out.get("picker_families")
    customers = {c["uuid"] for c in out["compatible_entities"] if c["entity_type"] == "customer"}
    assert customers == {srt, mch, near_a, near_b}, out["compatible_entities"]


# ============================================================ review B1: near-identical GROUP names


def test_groups_whose_names_differ_only_by_punctuation_or_legal_form_are_one_customer():
    """Review B1 of #2144, reversed by the 9 Nov ruling ("be more lenient"): "ZZT CRAFT SDN BHD" (SRT),
    "ZZT CRAFT SDN. BHD." (MCH) and "ZZT CRAFT" (MCH) share one trading name, so they are one customer: no question,
    the answer covers all three groups' ledgers."""
    from app.services.chatbot.turn.narrow import customer_options

    a, b, c = (str(uuid.uuid4()) for _ in range(3))
    ids = {a: "ZZT CRAFT SDN BHD", b: "ZZT CRAFT SDN. BHD.", c: "ZZT CRAFT"}
    rows = [
        {"entity_type": "customer", "uuid": a, "company_code": "SRT", "display": {"customer_name": "ZZT CRAFT SDN BHD [A/C I]"}},
        {"entity_type": "customer", "uuid": b, "company_code": "MCH", "display": {"customer_name": "ZZT CRAFT SDN. BHD. - [IBORN]"}},
        {"entity_type": "customer", "uuid": c, "company_code": "MCH", "display": {"customer_name": "ZZT CRAFT - [CERAMIC]"}},
    ]
    resolver = {"resolutions": [{"token": "zzt craft", "matches": rows}], "unresolved_tokens": []}
    parser = {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [{"raw": "zzt craft", "hint": "customer", "current_message": True, "confident": True}],
    }
    with lf.customer_groups({}, ids=ids):
        out = run_gate(dict(resolver), parser=parser, resolver=resolver)
        options = customer_options(
            [{"raw": r["display"]["customer_name"], "name": r["display"]["customer_name"], "uuid": r["uuid"],
              "canonical_code": r["uuid"][:6], "company_codes": [r["company_code"]]} for r in rows],
            cap=50,
        )
    assert out.get("require_specific") is not True and not out.get("picker_families"), out.get("picker_families")
    assert {c["uuid"] for c in out["compatible_entities"] if c["entity_type"] == "customer"} == {a, b, c}
    assert len(options) == 1 and sorted(options[0]["uuids"]) == sorted([a, b, c]), options


# ============================================================ review 2: the "has DO" stamp follows the list rule


def _do_row(customer: str, delivered: bool) -> dict[str, Any]:
    return {"customer_name": customer, "actual_delivery_date": "2026-10-01" if delivered else None}


def test_the_has_do_stamp_follows_the_customer_entry_not_the_ledger():
    """9 Nov ruling: one customer entry is every ledger of one trading name (or one group), so the entry reads
    "has DO" when any of its ledgers has one; another shop never borrows it."""
    from app.services.chatbot.lanes.business import pickers

    rows = [_do_row(G1, True), _do_row(U1, False), _do_row(OTHER, False)]
    bases = pickers._bases_with_do(rows)
    assert pickers.customer_stamp(G1, bases) == "has DO"
    assert pickers.customer_stamp(U1, bases) == "has DO"
    assert pickers.customer_stamp(OTHER, bases) == "no DO"

    with lf.customer_groups({G1: NAME, G2: NAME}):
        bases = pickers._bases_with_do([_do_row(G2, True), _do_row(OTHER, False)])
        assert pickers.customer_stamp(G1, bases) == "has DO"  # its group's other ledger has one
        assert pickers.customer_stamp(U1, bases) == "has DO"  # ungrouped, the group's name (Q1)
        assert pickers.customer_stamp(OTHER, bases) == "no DO"


# ============================================================ access scope: "all accounts" = all the asker may see


def test_an_entry_covers_only_the_ledgers_the_resolver_returned_for_this_asker(world):
    """Owner 9 Nov: "all accounts" means all the accounts this asker may see. The resolver returns only the asker's
    rows (company scope, a dealer's own links); the group maps hold every grouped ledger, and must never add one the
    resolver left out. Here the asker sees two of the group's seven ledgers: the answer covers those two only."""
    seen = [world["rows"]["G1"], world["rows"]["U1"]]
    resolver = {"resolutions": [{"token": "zztfull", "matches": seen}], "unresolved_tokens": []}
    parser = {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [{"raw": "zztfull", "hint": "customer", "current_message": True, "confident": True}],
    }
    with lf.customer_groups(world["names"], ids=world["ids"]):
        out = run_gate(dict(resolver), parser=parser, resolver=resolver)
    assert out.get("require_specific") is not True, out.get("gate_reason")
    customers = {c["uuid"] for c in out["compatible_entities"] if c["entity_type"] == "customer"}
    assert customers == {world["rows"]["G1"]["uuid"], world["rows"]["U1"]["uuid"]}, out["compatible_entities"]


# ============================================================ re-land review (9 Nov 2026)


def _order_gate(rows: list[dict[str, Any]], token: str = "zzt") -> dict[str, Any]:
    resolver = {"resolutions": [{"token": token, "matches": rows}], "unresolved_tokens": []}
    parser = {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [{"raw": token, "hint": "customer", "current_message": True, "confident": True}],
    }
    return run_gate(dict(resolver), parser=parser, resolver=resolver)


def _cust(uid: str, name: str) -> dict[str, Any]:
    return {"entity_type": "customer", "uuid": uid, "company_code": "SRT", "display": {"customer_name": name}}


def test_an_ungrouped_sibling_of_a_grouped_ledger_joins_the_group_even_when_the_group_has_another_name():
    """Re-land review B1: "[A/C I]" sits in a group named after another shop, its "[A/C II]" sibling in none. Same
    trading name, so one customer (owner 9 Nov, Q1): no question, one line by the group's name, both ledgers."""
    from app.services.chatbot.turn.narrow import customer_options

    grouped, stray = str(uuid.uuid4()), str(uuid.uuid4())
    names = {grouped: "ZZT CHIN HOMEMART SDN BHD [A/C I]", stray: "ZZT CHIN HOMEMART SDN BHD [A/C II]"}
    rows = [_cust(u, n) for u, n in names.items()]
    with lf.customer_groups({names[grouped]: "ZZT CHIN HARDWARE SDN BHD"}, ids={grouped: "ZZT CHIN HARDWARE SDN BHD"}):
        out = _order_gate(rows)
        options = customer_options(
            [{"raw": n, "name": n, "uuid": u, "canonical_code": u[:6]} for u, n in names.items()], cap=50
        )
    assert out.get("require_specific") is not True and not out.get("picker_families"), out.get("gate_reason")
    assert len(options) == 1 and sorted(options[0]["uuids"]) == sorted([grouped, stray]), options
    assert options[0]["label"] == "ZZT CHIN HARDWARE SDN BHD", options


def test_a_group_whose_name_is_only_a_marker_still_keys_its_ledgers():
    """Re-land review S3: a group named "(PROJECT)" has no trading name; its ledgers still key (by their own name)
    and so still reach the list."""
    uid = str(uuid.uuid4())
    with lf.customer_groups({}, ids={uid: "(PROJECT)"}):
        assert lf.ledger_family_key("ZZT PROJECT HOUSE SDN BHD [A/C I]", uid) == "ZZT PROJECT HOUSE"


def test_the_picker_line_of_an_ungrouped_family_keeps_an_inner_parenthesis():
    """Re-land review S1: with no group, a several-ledger line is named as n8n (and pre-#2144) named it: the markers
    and the TRAILING parentheses go, an inner "(JB)" stays."""
    a, b, other = (str(uuid.uuid4()) for _ in range(3))
    rows = [
        _cust(a, "ZZT HANLIM TRADING (JB) SDN BHD [A/C I]"),
        _cust(b, "ZZT HANLIM TRADING (JB) SDN BHD [A/C II]"),
        _cust(other, "ZZT HANLIM TILES SDN BHD"),
    ]
    out = _order_gate(rows)
    titles = [c.get("title") for c in out["compatible_entities"] if c["entity_type"] == "customer"]
    assert "ZZT HANLIM TRADING (JB) SDN BHD (SRT)" in titles, titles


def test_the_report_widens_a_held_group_member_to_a_stray_of_another_members_name():
    """Re-land review round 3: the report path (`report_ask.with_customer_groups`) holds ONE ledger of a group; the
    group's other member has another trading name, and an ungrouped ledger of THAT name joins the group's answer (Q1).
    The report covers the whole group and the stray, as the typed path does; another shop is never added."""
    from app.services.chatbot.lanes.business import report_ask
    from app.services.customer_group_service import family_maps

    hardware, homemart = "ZZTRW CHIN HARDWARE SDN BHD", "ZZTRW CHIN HOMEMART SDN BHD"
    with blank_session() as db:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        held, member, stray, other = seed_ledgers(
            db,
            [
                (f"{hardware} [A/C I]", hardware),
                (f"{homemart} [A/C I]", hardware),
                (f"{homemart} [A/C II]", None),
                ("ZZTRW CHIN TILES SDN BHD", None),
            ],
        )
        names, ids = family_maps(db)
        with lf.customer_groups(names, ids=ids):
            out = report_ask.with_customer_groups(db, {"customer_ids": [str(held)]})
    assert set(out["customer_ids"]) == {str(held), str(member), str(stray)}, out
    assert str(other) not in out["customer_ids"]
