"""RED (live defect, 2 Oct 2026): staff "account N" narrowing through the REAL resolver.

`documentation/plans/chatbot/account-ledger-acceptance-criteria.md` AC-8, AC-9.

The staff tests in `test_account_ledger_staff.py` / `test_account_ledger_fix2.py` hand the turn
a FAKE resolver that answers in the OR shape (`resolutions[].matches`). The live turn asks the
resolver in AND mode (`resolve_entity_body` defaults `match_mode` to "and"), and the AND answer
carries `intersection` + `by_entity_type` and NO `resolutions` at all, so
`resolve_gate.narrow_by_account` returned at its `not resolutions` guard and narrowed nothing:
the crew console dry run (prompt v56, staff contact) showed the un-narrowed picker for
"Soon Heng account 1 outstanding" and for "Soon Heng Trading account 2 outstanding".

These tests leave the resolver alone (`real_resolver=True`: the in-process
`POST /api/v1/system/references/resolve` route over the customers seeded here). Only the
parser, access and MCP are faked.

Data mirrors the crew copy's shape (levels are the setting):
  * SOON HENG TRADING [A/C III] (3), [A/C IV] (4), [A/C I] (1)
  * SOON GUAN HENG TRADING SDN BHD [A/C I] (1), [A/C III] (3) - every word of
    "Soon Heng Trading" is in it, so the AND resolver returns it beside the family typed
  * SOON HENG HARDWARE CO.SDN.BHD. bare rows with no level (enough of them to pass the
    resolver body's 15-row cap) and its [A/C I] (1), [A/C II] (2)
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import customer as seed_customer
from tests.chatbot.test_account_ledger_staff import _acct, _picker_lines
from tests.chatbot.test_customer_scope_lane import _ask, _turn
from tests.chatbot.test_outstanding_lane import REPORT_HIT, _seed_contact

T_3 = "SOON HENG TRADING [A/C III]"
T_4 = "SOON HENG TRADING [A/C IV]"
T_1 = "SOON HENG TRADING [A/C I]"
G_1 = "SOON GUAN HENG TRADING SDN BHD [A/C I]"
G_3 = "SOON GUAN HENG TRADING SDN BHD [A/C III]"
H_1 = "SOON HENG HARDWARE CO.SDN.BHD. [A/C I]"
H_2 = "SOON HENG HARDWARE CO.SDN.BHD. [A/C II]"
#: Bare, level-less rows seeded FIRST so the leveled rows sit past the body's 15-row cap.
H_BARE = [f"SOON HENG HARDWARE CO.SDN.BHD. (OUTLET {n})" for n in range(1, 17)]

BOOK: list[tuple[str, int | None]] = (
    [(n, None) for n in H_BARE]
    + [(T_3, 3), (T_4, 4), (G_3, 3), (H_2, 2), (G_1, 1), (H_1, 1), (T_1, 1)]
)


def _seed_book(session_factory) -> dict[str, str]:
    db = session_factory()
    ids: dict[str, str] = {}
    for name, level in BOOK:
        row = seed_customer(db, company_id=DEFAULT_COMPANY_ID, name=name)
        if level is not None:
            db.execute(text("UPDATE customers SET account_level = :n WHERE id = :i"), {"n": level, "i": str(row.id)})
        ids[name] = str(row.id)
    db.commit()
    return ids


def _real(session_factory, monkeypatch, entity: dict[str, Any], body: str) -> tuple[str, list]:
    return _turn(
        session_factory, monkeypatch, _ask([entity]), body, real_resolver=True, mcp_response=REPORT_HIT,
    )


def test_real_resolver_level_the_name_lacks_is_refused_naming_its_levels(session_factory, monkeypatch) -> None:
    """AC-9: the trading name typed has Account 1, 3 and 4; the word-bag sibling the AND
    resolver also returns (SOON GUAN HENG TRADING) does not turn it into "None of ..."."""
    _seed_contact(session_factory, variables={})
    _seed_book(session_factory)
    reply, captured = _real(
        session_factory, monkeypatch, _acct("Soon Heng Trading", 2), "soon heng trading account 2 outstanding"
    )
    assert reply.strip() == "SOON HENG TRADING has no Account 2. It has Account 1, Account 3 and Account 4.", reply
    assert captured == [], captured


def test_real_resolver_account_1_lists_only_level_one_ledgers(session_factory, monkeypatch) -> None:
    """AC-8: only level-one ledgers in the which-customer list, including the ones the
    resolver body's 15-row cap would have cut."""
    _seed_contact(session_factory, variables={})
    _seed_book(session_factory)
    reply, captured = _real(session_factory, monkeypatch, _acct("Soon Heng", 1), "soon heng account 1 outstanding")
    assert captured == [], captured
    assert "Which customer do you mean?" in reply, reply
    lines = _picker_lines(reply)
    for wanted in ("SOON HENG TRADING [A/C I]", "SOON HENG HARDWARE CO.SDN.BHD. [A/C I]"):
        assert any(wanted in line for line in lines), (wanted, reply)
    for other in ("[A/C II]", "[A/C III]", "[A/C IV]", "OUTLET"):
        assert other not in reply, (other, reply)
