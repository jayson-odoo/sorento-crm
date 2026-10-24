"""REPORT-SMART-L one ranking, round R3a (AC-OR3), backend half: the item ranking's reply is localized
for a contact whose chat language is not English, and a category row shows the category's code.
The presenter half (WhatsApp split, the no-sale line) is in
`sorento_crm_mcp/tests/test_one_ranking_r3a_presenter.py`. Fake names only."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.chatbot import label_catalog
from app.services.chatbot.label_catalog import Localizer
from app.services.chatbot.lanes.business import fetch

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL = "crm_report_ask"


def _presenters():
    mcp_root = REPO_ROOT / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    try:
        from sorento_crm_mcp import presenters
    except ImportError:  # pragma: no cover
        pytest.skip("sorento_crm_mcp is not importable in this environment")
    return presenters


def _body(group_by: str = "product", **over: Any) -> dict[str, Any]:
    body = {
        "status": "ok", "message": None, "basis": "delivered", "basis_label": "delivered sales", "measure": "qty",
        "group_by": group_by, "group_label": group_by.title(), "sort": "desc",
        "date_from": "2026-09-01", "date_to": "2026-09-30",
        "filters": [{"key": "brand", "label": "Brand", "values": ["SORENTO"]}],
        "rows": [{"rank": 1, "name": "ZZT-ITEM-1", "qty": 30, "amount": 1200.0},
                 {"rank": 2, "name": "ZZT-ITEM-2", "qty": 15, "amount": 600.0}],
        "more": 0, "total_count": 2, "total": {"qty": 45, "amount": 1800.0},
    }
    body.update(over)
    return body


def _structure(body: dict[str, Any], lang: str | None) -> dict[str, Any]:
    envelope = json.loads(_presenters().present_response(TOOL, json.dumps(body)))
    ctx: dict[str, Any] = {"tool": TOOL, "semantic_input": {}, "entities": []}
    if lang:
        ctx["localizer"] = Localizer(lang, label_catalog.defaults(lang))
    return fetch.output_structurer(copy.deepcopy(envelope), ctx)


@pytest.mark.parametrize("lang, label", [("ms", "Jenama: SORENTO"), ("zh", "品牌: SORENTO")])
def test_r3a_3_an_item_ranking_fixed_lines_are_in_the_contacts_language(lang, label) -> None:
    english = _structure(_body(), None)["response"]
    translated = _structure(_body(), lang)["response"]
    assert translated != english, translated
    assert label in translated.split("\n"), translated


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3a_3_guard_the_rank_lines_and_figures_are_unchanged_by_localization(lang) -> None:
    english = _structure(_body(), None)["response"].split("\n")
    translated = _structure(_body(), lang)["response"].split("\n")
    rows = [ln for ln in english if ln.startswith(("1. ", "2. "))]
    assert rows and all(r in translated for r in rows), translated


def test_r3a_3_guard_english_with_the_localizer_is_byte_identical_to_no_localizer() -> None:
    assert _structure(_body(), "en")["response"] == _structure(_body(), None)["response"]


# ---------------------------------------------------------------- 4. category code beside the name (route)


def test_r3a_4_a_category_ranking_row_carries_the_categorys_code(client, db) -> None:
    from tests.test_report_ask_route import _category, _ok, _prod, _sale, seed_customer, unique_code, warehouse
    from tests._sales_report_do_seed import seed_agent
    from app.services.company_scope import DEFAULT_COMPANY_ID

    cat = _category(db, "ZZT Cat Name")
    code = cat.category_code
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    agent = seed_agent(db, code=unique_code("Agent"))
    prod = _prod(db, unique_code("ZZTP", alpha=True), category=cat)
    _sale(db, cust=cust, wh=wh, agent=agent, prod=prod, qty=3, total="300.00")
    from tests._chat_asker_seed import link_user
    from tests.test_top_selling_report import _access
    from tests._sales_report_do_seed import _contact

    contact = _contact(db, granted=True)
    link_user(db, contact)
    _access(db, contact, "Sorento Office")  # staff: item rankings are open to them
    db.commit()
    body = _ok(client, contact, group_by="category", top_n=5)
    row = body["rows"][0]
    assert code in json.dumps(row), (code, row)  # the code beside the name, as top selling printed it


def _staff_and_world(db):
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._chat_asker_seed import link_user
    from tests._sales_report_do_seed import _contact, seed_agent
    from tests.test_report_ask_route import _category, _prod, _sale, seed_customer, unique_code, warehouse
    from tests.test_top_selling_report import _access

    cat = _category(db, "ZZT Cat Name")
    cust = seed_customer(db, name=unique_code("Cust"))
    wh = warehouse(db, company_id=DEFAULT_COMPANY_ID)
    agent = seed_agent(db, code=unique_code("Agent"))
    prod = _prod(db, unique_code("ZZTP", alpha=True), category=cat)
    _sale(db, cust=cust, wh=wh, agent=agent, prod=prod, qty=3, total="300.00")
    contact = _contact(db, granted=True)
    link_user(db, contact)
    _access(db, contact, "Sorento Office")
    db.commit()
    return contact


@pytest.mark.parametrize("group_by", ["sales_agent", "customer"])
def test_r3a_review_1_a_non_category_ranking_row_has_no_code_key(client, db, group_by) -> None:
    from tests.test_report_ask_route import _ok

    body = _ok(client, _staff_and_world(db), group_by=group_by, top_n=5)
    assert body["rows"] and all("code" not in row for row in body["rows"]), body["rows"]


def test_r3a_review_1_guard_a_category_ranking_row_keeps_its_code_key(client, db) -> None:
    from tests.test_report_ask_route import _ok

    body = _ok(client, _staff_and_world(db), group_by="category", top_n=5)
    assert body["rows"] and all("code" in row for row in body["rows"]), body["rows"]


from tests.test_report_ask_route import client, db  # noqa: E402,F401 - fixtures of the route tests
