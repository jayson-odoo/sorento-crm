"""CUSTOMER-GROUP-GATE: the chatbot gate applies the office's explicit customer groups.

Bug (found by SALES-ACCOUNT-TYPE, #2105): `gate._cust_base` stripped the `[A/C ..]` account
suffix BEFORE asking `customer_group_of`, which answers only by the exact FULL ledger name
(owner ruling (b), 2 Oct 2026). So no suffixed ledger ever reached its group and every ledger
fell to the name rule: on the dev copy all 8 FULLSHUN ledgers, grouped or not, became the one
name-rule family "FULLSHUN SANITARYWARE (NO GROUP)".

Owner rules: "no auto name-matching - explicit links only", "bot asks less, never a wrong
figure". Contract pinned here, per domain's which-one list:
- the ledgers the office grouped form the GROUP's family;
- an ungrouped ledger of the same trading name stays apart (its own family, never joined);
- an unrelated customer is its own family.

The gate decides the customer picker for the domains whose matrix allows a customer
(`order`: DO and outstanding asks, `sales`). The stock list (`inventory`) has no customer in
the gate matrix; its roster is the narrower's (`turn/narrow.py`), pinned here too so all four
lists stay on the one rule. Fake ZZT names only; no database.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import ledger_family as lf
from app.services.chatbot.lanes.business import gate
from app.services.chatbot.lanes.business.gate import run_gate

GROUP = "ZZTFULL SANITARYWARE SDN BHD"
GROUPED_I = f"{GROUP} - [A/C I]"
GROUPED_II = f"{GROUP} [A/C II]"
UNGROUPED = f"{GROUP} - [A/C III]"
OTHER = "ZZTFULL TILES SDN BHD - [A/C I]"

#: what `customer_group_service.family_overrides` loads: full ledger name -> group name.
GROUPS = {GROUPED_I: GROUP, GROUPED_II: GROUP}

GROUP_KEY = lf.group_key(GROUP)


def _match(name: str, company: str = "SRT") -> dict[str, Any]:
    uid = str(uuid.uuid4())
    return {
        "entity_type": "customer",
        "uuid": uid,
        "canonical_code": f"ZZT-{uid[:6]}",
        "company_code": company,
        "display": {"customer_name": name},
    }


def _rows() -> list[dict[str, Any]]:
    return [_match(GROUPED_I), _match(GROUPED_II, "MCH"), _match(UNGROUPED), _match(OTHER)]


def _gate(domain: str, intent: str, rows: list[dict[str, Any]], **parser_extra: Any) -> dict[str, Any]:
    resolver = {
        "resolutions": [{"token": "zztfull", "matches": rows}],
        "unresolved_tokens": [],
    }
    parser = {
        "domain_hint": domain,
        "intent_hint": intent,
        "entities": [{"raw": "zztfull", "hint": "customer", "current_message": True, "confident": True}],
        **parser_extra,
    }
    with lf.customer_groups(GROUPS):
        return run_gate(dict(resolver), parser=parser, resolver=resolver)


def _families_by_name(out: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    name_of = {r["uuid"]: r["display"]["customer_name"] for r in rows}
    fams = out.get("picker_families") or {}
    return {key: {name_of[u] for u in uuids} for key, uuids in fams.items()}


# ============================================================ the grouping key itself


def test_cust_base_finds_the_group_of_a_suffixed_ledger_by_its_full_name():
    with lf.customer_groups(GROUPS):
        assert gate._cust_base(_match(GROUPED_I)) == GROUP_KEY
        assert gate._cust_base(_match(GROUPED_II)) == GROUP_KEY


def test_cust_base_keeps_an_ungrouped_ledger_of_the_same_name_apart_from_the_group():
    with lf.customer_groups(GROUPS):
        assert gate._cust_base(_match(UNGROUPED)) != GROUP_KEY
        assert gate._cust_base(_match(UNGROUPED)) == lf.ledger_family_key(UNGROUPED)


def test_cust_base_matches_ledger_family_key_for_every_row():
    """The gate's families and the narrower's printed lines group by the same rule."""
    with lf.customer_groups(GROUPS):
        for name in (GROUPED_I, GROUPED_II, UNGROUPED, OTHER):
            assert gate._cust_base(_match(name)) == lf.ledger_family_key(name), name


def test_cust_base_without_groups_is_the_name_rule():
    assert gate._cust_base(_match(GROUPED_I)) == gate._cust_base(_match(UNGROUPED)) == "ZZTFULL SANITARYWARE"


# ============================================================ per domain's which-one list


@pytest.mark.parametrize(
    ("domain", "intent", "extra"),
    [
        pytest.param("order", "check_order", {}, id="do"),
        pytest.param("order", "check_order", {"order_status": "outstanding"}, id="outstanding"),
        pytest.param("sales", "sales_report", {}, id="sales"),
    ],
)
def test_gate_which_one_list_puts_grouped_ledgers_in_their_group(domain, intent, extra):
    rows = _rows()
    out = _gate(domain, intent, rows, **extra)
    families = _families_by_name(out, rows)
    assert families.get(GROUP_KEY) == {GROUPED_I, GROUPED_II}, families
    ungrouped = [k for k, names in families.items() if UNGROUPED in names]
    assert ungrouped and ungrouped[0] != GROUP_KEY, families
    assert families[ungrouped[0]] == {UNGROUPED}, families
    assert any(names == {OTHER} for names in families.values()), families
    assert out.get("require_specific") is True


def test_stock_which_one_list_puts_grouped_ledgers_in_their_group():
    """`inventory` has no customer in the gate matrix: the stock roster is the narrower's,
    keyed by `ledger_family_key` on the full name."""
    from app.services.chatbot.turn.narrow import _options

    def cand(name: str) -> dict[str, Any]:
        uid = str(uuid.uuid4())
        return {"raw": name, "name": name, "uuid": uid, "canonical_code": f"ZZT-{uid[:6]}"}

    with lf.customer_groups(GROUPS):
        options = _options([cand(n) for n in (GROUPED_I, GROUPED_II, UNGROUPED, OTHER)], "customer", "ledger_family")
    labels = [o["label"] for o in options]
    assert labels == [GROUP, UNGROUPED, OTHER], labels
    by_label = {o["label"]: o for o in options}
    assert len(set(by_label[GROUP]["uuids"])) == 2
