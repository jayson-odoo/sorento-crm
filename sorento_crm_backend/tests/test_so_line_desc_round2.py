"""SO-LINE-DESC round 2: the Confirm path's other queue sites (saved decision lines, cancel,
product moves, split rows) print the same decorated ITEM CODE, and a hostile description cannot
break the ingest, the Excel or the HTML."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from .scm.test_line_splits_api import _put, _sp, _url
from .test_oi_handover_email_excel_parity import _render_current, _sheet, sent  # noqa: F401
from .test_oi_product_follow_apply import _apply, _swap_fixture
from .test_planning_change_apply_on_board import _confirm
from .test_oi_saved_line_email import _order, _post
from .test_planning_change_apply_on_board import BASE, api, world  # noqa: F401 - fixtures
from .test_planning_changes import _line_payload
from .test_so_line_desc_oi_handover import (
    PUSH,
    RPACC,
    _describe,
    _email_item_cells,
    _oi_world,
    _preview_html,
    _tick,
    rs,
    stored,
)
from .test_so_line_desc_ingest import _push, _stored, _so_line, _so_record, env  # noqa: F401
from .test_so_supply_confirmation import _stock

__all__ = ["api", "world", "sent", "rs", "stored", "env"]


def _prints(context, uploads):
    """`(item cells of the rendered email body, its plain text, Excel ITEM CODE cells)`."""
    rendered = _render_current(context["handover"]["lines"])
    _headings, body = _sheet(context, uploads)
    return (
        _email_item_cells(rendered["body_html"]),
        rendered["body_text"],
        [row["ITEM CODE"] for row in body],
    )


def _expect_everywhere(context, uploads, *, present, absent=()):
    cells, text, excel = _prints(context, uploads)
    for want in present:
        assert want in cells, (want, cells)
        assert want in text, (want, text)
        assert want in excel, (want, excel)
    for bad in absent:
        assert bad not in cells and bad not in excel, (bad, cells, excel)


# ------------------------------------------------------------------ 1. saved decision lines


@pytest.mark.parametrize("ticked", [True, False])
def test_saved_decision_line_prints_the_decorated_code_in_body_text_and_excel(api, sent, ticked):
    _client, world = api
    contexts, uploads = sent
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line_a, line_b = _order(api)
    _post(api, order, [
        _line_payload(line_a.id, buy_qty="10"),
        _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}]),
    ])
    contexts.clear()
    _tick(world.db, world.product.id, ticked)
    _describe(world.db, line_b.core_sales_order_line_id, PUSH)
    world.db.commit()

    _post(api, order, [_line_payload(line_b.id, buy_qty="6", amend_reason="Keep BRW free.")])

    [context] = contexts
    code = world.product.product_code
    want = f"{code} - {PUSH}" if ticked else code
    _expect_everywhere(context, uploads, present=[want])
    if not ticked:
        assert PUSH not in str(context["handover"]["lines"])


@pytest.mark.parametrize("ticked", [True, False])
def test_cancel_so_line_prints_the_decorated_code_in_body_text_and_excel(api, sent, ticked):
    client, world = api
    contexts, uploads = sent
    order, line_a, line_b = _order(api)
    _tick(world.db, world.product.id, ticked)
    _describe(world.db, line_b.core_sales_order_line_id, PUSH)
    world.db.commit()

    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json={
        "lines": [_line_payload(line_a.id, buy_qty="10")],
        "cancelled_lines": [{"project_line_id": str(line_b.id), "reason": "Customer dropped it."}],
    })
    assert response.status_code == 200, response.text
    world.db.commit()

    [context] = contexts
    [cancel] = [l for l in context["handover"]["lines"] if l["remark"] == "CANCEL"]
    code = world.product.product_code
    want = f"{code} - {PUSH}" if ticked else code
    assert cancel["item_code"] == want
    _expect_everywhere(context, uploads, present=[want])


@pytest.mark.parametrize("new_qty", ["10", "12", "8"])
@pytest.mark.parametrize("ticked", [True, False])
def test_declined_product_move_prints_the_decorated_new_code_in_body_text_and_excel(
    api, sent, ticked, new_qty
):
    contexts, uploads = sent
    fx = _swap_fixture(api, acknowledged=True, placed_unlinked=True, new_qty=new_qty)
    db = fx["world"].db
    _tick(db, fx["new"].id, ticked)
    _describe(db, fx["line"].core_sales_order_line_id, PUSH)
    db.commit()
    contexts.clear()

    response = _confirm(
        fx["client"], fx["order"].id, [_line_payload(fx["line"].id, buy_qty=new_qty)],
        batch_id=str(fx["batch"].id),
    )
    assert response.status_code == 200, response.text
    db.commit()

    [context] = contexts
    new, old = fx["new"].product_code, fx["old"].product_code
    want = f"{new} - {PUSH}" if ticked else new
    [line] = [l for l in context["handover"]["lines"] if "NEW ITEM CODE" in (l["remark"] or "")]
    assert line["item_code"] == want
    assert line["was"]["item_code"] == old
    _, headings_body = _sheet(context, uploads)
    assert [r["NEW ITEM CODE"] for r in headings_body] == [want]
    cells, text, _excel = _prints(context, uploads)
    assert want in text


# ------------------------------------------------------------------ 2. split swapped line, old side


def test_split_swapped_line_prints_the_old_code_decorated_when_its_product_is_ticked(api, sent):
    contexts, uploads = sent
    fx = _swap_fixture(api, acknowledged=True)
    db = fx["world"].db
    old, new = fx["old"].product_code, fx["new"].product_code
    _tick(db, fx["old"].id)
    _tick(db, fx["new"].id)
    _describe(db, fx["line"].core_sales_order_line_id, PUSH)
    db.commit()
    line_id = str(fx["line"].id)
    s = SimpleNamespace(client=fx["client"], order=fx["order"])
    saved = _put(s, [{"line_id": line_id, "splits": [
        _sp(6, date(2026, 11, 20), on=line_id),
        _sp(4, date(2026, 12, 4), on=line_id),
    ]}])
    assert saved.status_code == 200, saved.text
    contexts.clear()

    response = _apply(fx)
    assert response.status_code == 200, response.text
    db.commit()

    [context] = contexts
    lines = [l for l in context["handover"]["lines"] if l["item_code"].startswith(new)]
    assert [l["qty"] for l in lines] == ["6", "4"], lines
    assert all(l["item_code"] == f"{new} - {PUSH}" for l in lines)
    assert all(l["was"]["item_code"] == f"{old} - {PUSH}" for l in lines), lines
    _headings, body = _sheet(context, uploads)
    assert body[0]["ITEM CODE"] == f"{old} - {PUSH}", body


# ------------------------------------------------------------------ 3. control characters


def test_a_vertical_tab_in_product_name_is_not_stored(env):
    record = _so_record(
        env, lines=[_so_line(env, product_name="SORENTO ACCESSORIES\x0bSRTWC8320 PUSH BUTTON ONLY")]
    )

    _push(env, record)

    stored_description = _stored(env, record)["description"]
    assert stored_description and stored_description.startswith("SORENTO ACCESSORIES")
    assert stored_description.endswith("SRTWC8320 PUSH BUTTON ONLY")
    assert not any(ord(c) < 32 and c not in "\t\n\r" for c in stored_description), repr(
        stored_description
    )


def test_a_description_with_a_control_character_still_sends_the_handover_with_its_excel(
    api, sent
):
    """The text comes in the way it does in production, through the sales order ingest push
    (`product_name` with a vertical tab, as a Word Shift+Enter paste). The Excel must still be
    attached to the handover (`IllegalCharacterError` used to cost the email its Excel)."""
    import uuid

    from app.models.order import SalesOrder, SalesOrderLine
    from app.services.document_ingest_service import DocumentIngestService
    from app.services.integration_reference_service import IntegrationReferenceService

    from .test_planning_changes import _project_line, _project_so

    _client, world = api
    contexts, uploads = sent
    db = world.db
    refs = IntegrationReferenceService(db, company_id=world.company_id)
    tag = uuid.uuid4().hex[:8]
    refs.link(entity_type="products", entity_id=str(world.product.id), source_ref=f"ZZT:P:{tag}")
    refs.link(entity_type="warehouses", entity_id=str(world.own_wh.id), source_ref=f"ZZT:W:{tag}")
    _tick(db, world.product.id)
    record = {
        "source_ref": f"ZZT:SO:{tag}", "so_number": f"ZZT-ING-{tag}", "status": "open",
        "lines": [{
            "source_ref": f"ZZT:SOL:{tag}", "product_ref": f"ZZT:P:{tag}",
            "product_code": world.product.product_code, "warehouse_ref": f"ZZT:W:{tag}",
            "qty_ordered": 10,
            "product_name": "SORENTO ACCESSORIES\x0bSRTWC8320 PUSH BUTTON ONLY",
        }],
    }
    result = DocumentIngestService(db, company_id=world.company_id).ingest(
        "sales_orders", [record]
    )
    assert result.records[0].outcome.value in {"created", "updated"}, result.records[0]
    db.commit()
    core_so = db.query(SalesOrder).filter(SalesOrder.so_number == f"ZZT-ING-{tag}").one()
    core_line = db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == core_so.id).one()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    mirror = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    _post(api, order, [_line_payload(mirror.id, buy_qty="10")])

    [context] = contexts
    attached = [a for a in context.get("email_attachments") or [] if a["filename"].endswith(".xlsx")]
    assert len(attached) == 1, context.get("email_attachments")
    _headings, body = _sheet(context, uploads)
    assert all("\x0b" not in (row["ITEM CODE"] or "") for row in body)


# ------------------------------------------------------------------ 4. NUL


def test_a_nul_in_product_name_does_not_fail_the_upsert(env):
    record = _so_record(env, lines=[_so_line(env, product_name="PUSH\x00BUTTON ONLY")])

    from .test_ingest_documents import INGEST_SO

    res = env.post(INGEST_SO, [record])

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    description = _stored(env, record)["description"]
    assert description and "\x00" not in description
    assert description.startswith("PUSH") and description.endswith("BUTTON ONLY")


# ------------------------------------------------------------------ 5. HTML escaping (guard)


def test_a_description_with_markup_is_escaped_in_the_email_body(rs):
    from .test_so_line_desc_oi_handover import _automation_at_head

    client, world = rs
    _automation_at_head(world)
    inquiry = _oi_world(world, [("RPACC", True, "<img src=x onerror=alert(1)>")])

    html = _preview_html(client, inquiry)

    assert "&lt;img" in html
    assert "<img src=x" not in html
