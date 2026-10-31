"""Reserve request / reserved emails as ONE flat full table (RESERVE-EMAIL-FULL-TABLE).

Contract: `documentation/plans/scm/reserve-email-full-table-acceptance-criteria.md`
(AC-RF-01..AC-RF-70). TEST-FIRST (Phase 2): written before the implementation, so a red is a
missing migration (`oisn_0002_full_table`), a missing query param or a wrong rendered
string, never a fixture bug.

Postgres only (`blank_session()` through the reserve suite's own `_api` world). Every chain
is seeded here; nothing is borrowed from a shared table. Dispatch is always captured
(`_captured_dispatches`), never sent. All names are fake.

What is asserted is the RENDERED email: subject, the HTML table (headings and cells), Cc
lists, the button URL and the plain text. The context shape is the coder's choice; the only
context keys named here are the ones AC-RF-51 lists. For the immediate (not parked) path
the captured dispatch context is rendered through the same template path
`park_send.render_preview` uses (`EmailTemplateService.render`).

Tests that pass before the implementation on purpose (the AC states existing behaviour or
guards against over-merging): AC-RF-36, AC-RF-42, AC-RF-43, AC-RF-70.
"""
from __future__ import annotations

import html as htmllib
import re
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.order import SalesOrder
from app.models.project_so import (
    OrderInquiry,
    OrderInquiryReleasedLink,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
    ProjectSalesOrder,
)
from app.services.company_scope import company_scope
from app.services.certificate_service import today_malaysia

from .test_email_layout_migrations import _run, _scripts, _seed
from .test_oi_staged_notify import (
    HEADERS_URL,
    NOTE_PREVIEW,
    NOTE_SEND,
    REQ_PREVIEW,
    REQ_SEND,
    _commit,
    _name,
    _names,
    _new_oi,
    _oi_row,
    _ok,
    _reserve,
    _rr,
    _set_automation,
    sn,  # noqa: F401  (fixture)
)
from .test_order_inquiry_reserve import (
    COMMIT_URL,
    REQUEST_URL,
    RESERVER_PERMISSIONS,
    _as,
    _captured_dispatches,
    _register,
    _requested_calls,
    _reserved_calls,
)
from .test_order_inquiry_reserve_round2 import _foreign_reserve_request
from .test_order_inquiry_worklist import _customer, _purchase_order, _uid, _user

MARKER = "zzt-oi-rf"
REQUEST_TRIGGER = "order_inquiry_reserve_requested"
RESERVED_TRIGGER = "order_inquiry_reserved"
# Built from two halves: other OI tests scan the migrations folder for the full token.
REQUEST_CODE = "order_inquiry_reserve_requested" + "_default"
RESERVED_CODE = "order_inquiry_reserved" + "_default"
NEW_REV = "oisn_0002_full_table"

REQUEST_HEADINGS = [
    "OI NO", "SO DATE", "S/O NO", "ITEM CODE", "QTY", "REQUESTED RESERVE",
    "DELIVERY DATE", "PROJECT/CUSTOMER",
]
RESERVED_HEADINGS = [
    "OI NO", "SO DATE", "S/O NO", "ITEM CODE", "QTY", "REQUESTED RESERVE", "STATUS",
    "DELIVERY DATE", "PROJECT/CUSTOMER",
]


# --------------------------------------------------------------------------------- #
# harness                                                                            #
# --------------------------------------------------------------------------------- #


def _chain_to_0001(world) -> dict:
    db = world.db
    mods = _seed(db)
    _run(mods["eml_0002_seed_layouts"], db)
    _run(mods["oisn_0001_staged_notify"], db)
    db.commit()
    return mods


def _full_automations(world) -> dict:
    """eml_0002, oisn_0001, then the new migration; fails clearly when it is missing."""
    mods = _chain_to_0001(world)
    assert NEW_REV in mods, f"migration {NEW_REV} does not exist yet"
    _run(mods[NEW_REV], world.db)
    world.db.commit()
    return mods


class _Tables(HTMLParser):
    """Every <table>, own rows only (the shell nests layout tables around the email's)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self.stack: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            t = {"head": [], "rows": [], "cur": None, "cell": None, "colspan": False}
            self.tables.append(t)
            self.stack.append(t)
        elif not self.stack:
            return
        elif tag == "tr":
            self.stack[-1]["cur"] = []
        elif tag in ("td", "th"):
            t = self.stack[-1]
            if "colspan" in a:
                t["colspan"] = True
            t["cell"] = {"tag": tag, "attrs": a, "text": ""}

    def handle_endtag(self, tag):
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td", "th") and t["cell"] is not None and t["cur"] is not None:
            t["cell"]["text"] = " ".join(t["cell"]["text"].split())
            t["cur"].append(t["cell"])
            t["cell"] = None
        elif tag == "tr" and t["cur"] is not None:
            cells = t["cur"]
            if cells and all(c["tag"] == "th" for c in cells):
                t["head"] = [c["text"] for c in cells]
            elif cells:
                t["rows"].append(cells)
            t["cur"] = None
        elif tag == "table":
            self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"] += data


def _table(body_html: str) -> dict:
    parser = _Tables()
    parser.feed(body_html)
    with_head = [t for t in parser.tables if t["head"]]
    assert with_head, "the email has no data table with headings"
    t = with_head[0]
    return {
        "headings": t["head"],
        "cells": t["rows"],
        "rows": [[c["text"] for c in row] for row in t["rows"]],
        "colspan": t["colspan"],
    }


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "title"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title") and self.skip:
            self.skip -= 1
        elif tag in ("td", "th", "p", "div", "tr", "h1", "h2", "h3", "br"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _visible(body_html: str) -> str:
    p = _Visible()
    p.feed(body_html)
    return " ".join("".join(p.parts).replace("‌", " ").replace("\xa0", " ").split())


def _anchors(body_html: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r'<a\b[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', body_html, re.DOTALL | re.IGNORECASE):
        label = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
        out.append((htmllib.unescape(m.group(1)), htmllib.unescape(label)))
    return out


def _button(body_html: str) -> tuple[str, str]:
    """(href, label) of the one link into the order inquiries."""
    found = [(h, l) for h, l in _anchors(body_html) if "/project-sales/order-inquiries" in h]
    assert len(found) == 1, found
    return found[0]


def _dmy(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _today() -> str:
    return today_malaysia().strftime("%d/%m/%Y")


def _link_base() -> str:
    from app.services.automation_triggers import build_order_inquiry_link

    return build_order_inquiry_link(None)


def _dress(world, inquiry, *, so_no, customer="CUSTOMER A", project="PROJECT X", so_date=date(2026, 9, 5)):
    """Give the OI's order a SO number, SO date, customer and project the email can print."""
    db = world.db
    cust = _customer(db, world.company_id, customer)
    core = SalesOrder(
        id=_uid(), company_id=world.company_id, so_number=so_no, customer_id=cust.id,
        order_date=so_date, project_label=project,
    )
    db.add(core)
    db.flush()
    pso = db.get(ProjectSalesOrder, inquiry.project_sales_order_id)
    pso.so_id = core.id
    pso.autocount_doc_no = so_no
    db.commit()


def _line(item="A", qty="50", ask=None, delivery=date(2027, 1, 25)):
    return {"item": f"{MARKER}-{item}", "qty": qty, "ask": ask or qty, "delivery": delivery}


def _oi(world, raiser_id, lines=None, *, so_no=None, **dress):
    """One OI raised by `raiser_id` (may be None) with its rows; returns (inquiry, rows)."""
    inquiry = _new_oi(world, raiser_id)
    _dress(world, inquiry, so_no=so_no or f"SO-RF-{_uid()[:6].upper()}", **dress)
    rows = [
        _oi_row(world, inquiry, qty=l["qty"], item_code=l["item"], delivery_date=l["delivery"])
        for l in (lines or [_line()])
    ]
    return inquiry, rows


def _ask(client, world, inquiry, rows, lines=None, *, park=True, note=None):
    """Request every row in `rows` (ask = the line's `ask`); returns the request id."""
    lines = lines or [_line()] * len(rows)
    body = {
        "rows": [
            {"row_id": r.id, "qty_requested": l["ask"], "warehouse_id": world.site.id}
            for r, l in zip(rows, lines)
        ],
        "park": park,
    }
    if note:
        body["note"] = note
    response = client.post(REQUEST_URL(inquiry.id), json=body)
    assert response.status_code == 201, response.text
    world.db.commit()
    return response.json()["id"]


def _parked(client, world, raiser_id, lines=None, **kw):
    """OI + rows + one parked request. Returns (inquiry, rows, request_id)."""
    lines = lines or [_line()]
    inquiry, rows = _oi(world, raiser_id, lines, **kw)
    return inquiry, rows, _ask(client, world, inquiry, rows, lines)


def _answered(client, world, raiser_id, answers, **kw):
    """OI whose request is answered with a PARKED notice. `answers` = [(ask, reserved, reason)]."""
    lines = [_line(item=chr(65 + i), qty="100", ask=ask) for i, (ask, _r, _why) in enumerate(answers)]
    inquiry, rows = _oi(world, raiser_id, lines, **kw)
    _ask(client, world, inquiry, rows, lines, park=False)
    reserves = []
    for row, (_ask_qty, got, why) in zip(rows, answers):
        entry = _reserve(world, row, got)
        if why:
            entry["reason"] = why
        reserves.append(entry)
    _commit(world, inquiry, reserves=reserves, park_notice=True)
    return inquiry, rows


def _req_mails(client) -> list:
    return _ok(client.post(REQ_PREVIEW))["emails"]


def _note_mails(world) -> list:
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as cs:
        return _ok(cs.post(NOTE_PREVIEW))["emails"]


def _render(world, call: dict) -> dict:
    """A captured dispatch context through the trigger's own template: `{subject, body_html, body_text}`."""
    from app.models.email_template import EmailTemplate
    from app.services import park_send
    from app.services.email_template_service import EmailTemplateService

    automation = park_send.first_automation(world.db, call["trigger_type"])
    template = world.db.query(EmailTemplate).filter(EmailTemplate.id == automation.email_template_id).first()
    ctx = {**call["context"], "recipient": {"name": "Fake Recipient", "email": "recipient@zzt.test"}}
    return EmailTemplateService(world.db).render(template, ctx)


def _set_fixed_request_to(world):
    """The request automation's To = one fixed CS user, so every raiser lands on Cc."""
    cs_fixed = _user(world.db, f"{MARKER} CS Fixed")
    _set_automation(world, REQUEST_TRIGGER, config={"user_ids": [cs_fixed]})
    return cs_fixed


def _raiser(world, label):
    return _user(world.db, f"{MARKER} {label}")


def _setup(sn, monkeypatch):
    client, world = sn
    _full_automations(world)
    _register()
    calls = _captured_dispatches(monkeypatch)
    return client, world, calls


# --------------------------------------------------------------------------------- #
# A. Table                                                                           #
# --------------------------------------------------------------------------------- #


def test_ac_rf_01_request_table_columns_in_order(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _parked(client, world, one, [_line("A"), _line("B")])
    mail = _req_mails(client)[0]
    assert _table(mail["body_html"])["headings"] == REQUEST_HEADINGS


def test_ac_rf_02_reserved_table_columns_in_order_reason_only_when_needed(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _answered(client, world, one, [("50", "50", None)])
    mail = _note_mails(world)[0]
    assert _table(mail["body_html"])["headings"] == RESERVED_HEADINGS, "no reason, no REASON column"


def test_ac_rf_03_headings_follow_export_headings(sn, monkeypatch):
    from app.services.order_inquiry_worklist_service import EXPORT_HEADINGS

    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _parked(client, world, one)
    _answered(client, world, one, [("50", "20", "only 20 on hand")])
    for mail in (_req_mails(client)[0], _note_mails(world)[0]):
        headings = _table(mail["body_html"])["headings"]
        mapped = ["RESERVED" if h == "STATUS" else h for h in headings if h not in ("OI NO", "REASON")]
        assert all(h in EXPORT_HEADINGS for h in mapped), (headings, EXPORT_HEADINGS)
        positions = [EXPORT_HEADINGS.index(h) for h in mapped]
        assert positions == sorted(positions), f"order drifted from the export: {headings}"


def test_ac_rf_04_table_is_flat_oi_no_on_every_row(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    a, _ra, _ = _parked(client, world, one, [_line("A"), _line("B")])
    b, _rb, _ = _parked(client, world, one, [_line("A"), _line("B")])
    single, _rs, _ = _parked(client, world, _raiser(world, "CS Two"), [_line("C")])
    mails = {len(_table(m["body_html"])["rows"]): m for m in _req_mails(client)}
    batch = _table(mails[4]["body_html"])
    assert not batch["colspan"], "no group rows, no colspan"
    assert all(len(r) == len(REQUEST_HEADINGS) for r in batch["rows"])
    assert sorted(r[0] for r in batch["rows"]) == sorted([a.inquiry_no] * 2 + [b.inquiry_no] * 2)
    one_oi = _table(mails[1]["body_html"])
    assert one_oi["headings"] == batch["headings"], "one OI and a batch share the table"
    assert one_oi["rows"][0][0] == single.inquiry_no and not one_oi["colspan"]


def test_ac_rf_05_no_cap_seven_ois_all_lines_print(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    made = [_parked(client, world, one, [_line("A"), _line("B")])[0] for _ in range(7)]
    mail = _req_mails(client)[0]
    table = _table(mail["body_html"])
    assert len(table["rows"]) == 14
    assert {r[0] for r in table["rows"]} == {i.inquiry_no for i in made}
    assert not re.search(r"\bmore order inquir", _visible(mail["body_html"]))
    assert not re.search(r"\band \d+ more\b", _visible(mail["body_html"]))


def test_ac_rf_06_rows_sort_item_then_real_date_then_oi_no(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    d_jan, d_mar = date(2027, 1, 25), date(2027, 3, 2)
    oi1, _r1, _ = _parked(client, world, one, [_line("B", delivery=d_jan), _line("A", delivery=d_mar)])
    oi2, _r2, _ = _parked(client, world, one, [_line("A", delivery=d_jan), _line("A", delivery=None)])
    oi3, _r3, _ = _parked(client, world, one, [_line("A", delivery=d_jan)])
    expect = sorted(
        [
            ("A", d_mar, oi1.inquiry_no), ("B", d_jan, oi1.inquiry_no),
            ("A", d_jan, oi2.inquiry_no), ("A", None, oi2.inquiry_no),
            ("A", d_jan, oi3.inquiry_no),
        ],
        key=lambda t: (t[0], t[1] or date.max, t[2]),
    )
    table = _table(_req_mails(client)[0]["body_html"])
    idx = {h: i for i, h in enumerate(table["headings"])}
    got = [(r[idx["ITEM CODE"]], r[idx["DELIVERY DATE"]], r[idx["OI NO"]]) for r in table["rows"]]
    assert got == [(f"{MARKER}-{i}", _dmy(d), no) for i, d, no in expect]


def test_ac_rf_07_cell_values(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    lines = [
        _line("A", qty="80", ask="30", delivery=date(2027, 1, 25)),
        _line("B", qty="12.5", ask="2.5", delivery=None),
    ]
    inquiry, _rows, _rid = _parked(
        client, world, one, lines, so_no="SO-RF-0007", customer="CUSTOMER A", project="PROJECT X",
        so_date=date(2026, 9, 5),
    )
    mail = _req_mails(client)[0]
    table = _table(mail["body_html"])
    first, second = table["rows"]
    assert first == [
        inquiry.inquiry_no, "05/09/2026", "SO-RF-0007", f"{MARKER}-A", "80", "30", "25/01/2027",
        "CUSTOMER A / PROJECT X",
    ]
    assert second[4:7] == ["12.5", "2.5", ""], "fractions print as is, a missing date is empty"
    assert "None" not in _visible(mail["body_html"]) and ".0000" not in mail["body_html"]


def test_ac_rf_08_retired_columns_and_request_number_appear_nowhere(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _parked(client, world, one, [_line("A")])
    _answered(client, world, one, [("50", "20", "short")])
    # Immediate emails too (plain text is only reachable here).
    _oi_i, rows_i = _oi(world, one, [_line("Z")])
    _ask(client, world, _oi_i, rows_i, park=False)
    _commit(world, _oi_i, reserves=[_reserve(world, rows_i[0], "50")])
    outputs = []
    for mail in (_req_mails(client)[0], _note_mails(world)[0]):
        outputs.append((mail["subject"], _visible(mail["body_html"])))
    for call in list(_requested_calls(calls)) + list(_reserved_calls(calls)):
        rendered = _render(world, call)
        outputs.append((rendered["subject"], _visible(rendered["body_html"])))
        outputs.append(("", rendered["body_text"]))
    assert len(outputs) >= 4
    for subject, text in outputs:
        for token in ("BALANCE", "REMAINING", "TOTAL QTY", "LOCATION"):
            assert token not in text and token not in subject, (token, text[:300])
        assert not re.search(r"\bRESERVED\b", text), text[:300]
        assert not re.search(r"#\d", subject + " " + text), (subject, text[:300])
        assert "Check the balance still to buy" not in text


def test_ac_rf_09_plain_text_has_same_lines_in_column_order_and_the_button_url(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _oi(world, one, [_line("A", qty="80", ask="30")], so_no="SO-RF-0009")
    _ask(client, world, inquiry, rows, [_line("A", qty="80", ask="30")], park=False)
    text = _render(world, _requested_calls(calls)[0])["body_text"]
    for heading_pair in zip(REQUEST_HEADINGS, REQUEST_HEADINGS[1:]):
        assert text.index(heading_pair[0]) < text.index(heading_pair[1]), heading_pair
    line = next(l for l in text.splitlines() if inquiry.inquiry_no in l and "SO-RF-0009" in l)
    wanted = [inquiry.inquiry_no, "05/09/2026", "SO-RF-0009", f"{MARKER}-A", "80", "30", "25/01/2027", "CUSTOMER A / PROJECT X"]
    positions = [line.index(w) for w in wanted]
    assert positions == sorted(positions), line
    assert f"{_link_base()}/{inquiry.id}" in text, "the button URL is in the text body"

    _commit(world, inquiry, reserves=[_reserve(world, rows[0], "30")])
    reserved_text = _render(world, _reserved_calls(calls)[0])["body_text"]
    assert reserved_text.index("REQUESTED RESERVE") < reserved_text.index("STATUS") < reserved_text.index("DELIVERY DATE")
    row_line = next(l for l in reserved_text.splitlines() if inquiry.inquiry_no in l and "SO-RF-0009" in l)
    assert row_line.index("30") < row_line.index("Reserved 30") < row_line.index("25/01/2027")
    assert f"{_link_base()}/{inquiry.id}" in reserved_text


def test_ac_rf_10_wide_layout_and_nowrap_cells(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _parked(client, world, one)
    _answered(client, world, one, [("50", "50", None)])
    for code in (REQUEST_CODE, RESERVED_CODE):
        layout = world.db.execute(
            sa.text("SELECT layout_json FROM email_templates WHERE code = :c"), {"c": code}
        ).scalar()
        assert layout["width"] == "wide", code
    req, res = _req_mails(client)[0], _note_mails(world)[0]
    assert "900" in req["body_html"] and "900" in res["body_html"], "the 900px card is rendered"
    req_t, res_t = _table(req["body_html"]), _table(res["body_html"])
    assert "nowrap" in str(req_t["cells"][0][0]["attrs"]).lower(), "OI NO cell"
    assert "nowrap" in str(res_t["cells"][0][0]["attrs"]).lower(), "OI NO cell"
    status_at = res_t["headings"].index("STATUS")
    assert "nowrap" in str(res_t["cells"][0][status_at]["attrs"]).lower(), "STATUS cell"


# --------------------------------------------------------------------------------- #
# B. STATUS and REASON                                                               #
# --------------------------------------------------------------------------------- #


def _status_cells(world):
    table = _table(_note_mails(world)[0]["body_html"])
    at = table["headings"].index("STATUS")
    return table, [r[at] for r in table["rows"]]


def test_ac_rf_11_12_13_status_reserved_partial_rejected(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _answered(client, world, one, [("50", "50", None), ("50", "20", "only 20"), ("50", "0", "none left")])
    table, cells = _status_cells(world)
    by_item = dict(zip([r[table["headings"].index("ITEM CODE")] for r in table["rows"]], cells))
    assert by_item[f"{MARKER}-A"] == "Reserved 50"
    assert by_item[f"{MARKER}-B"] == "Partial 20 of 50"
    assert by_item[f"{MARKER}-C"] == "Rejected"


def test_ac_rf_14_amendment_to_zero_is_rejected_above_the_ask_is_reserved(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    lines = [_line("A", qty="100", ask="50"), _line("B", qty="100", ask="50")]
    inquiry, rows = _oi(world, one, lines)
    _ask(client, world, inquiry, rows, lines, park=False)
    _commit(
        world, inquiry,
        reserves=[_reserve(world, rows[0], "50"), _reserve(world, rows[1], "50")],
        park_notice=True,
    )
    _commit(
        world, inquiry,
        amendments=[
            {"row_id": rows[0].id, "qty_reserved": "0", "reason": "none left"},
            {"row_id": rows[1].id, "qty_reserved": "60", "reason": "more arrived"},
        ],
        park_notice=True,
    )
    table, cells = _status_cells(world)
    by_item = dict(zip([r[table["headings"].index("ITEM CODE")] for r in table["rows"]], cells))
    assert by_item[f"{MARKER}-A"] == "Rejected"
    assert by_item[f"{MARKER}-B"] == "Reserved 60"


def test_ac_rf_15_reason_column_only_when_a_line_has_one_released_text_first(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _answered(client, world, one, [("50", "50", None), ("50", "20", "only 20 on hand")])
    table = _table(_note_mails(world)[0]["body_html"])
    assert table["headings"] == RESERVED_HEADINGS + ["REASON"], "REASON is last"
    by_item = {r[3]: r for r in table["rows"]}
    assert by_item[f"{MARKER}-B"][-1] == "only 20 on hand"
    assert by_item[f"{MARKER}-A"][-1] == "", "a fully reserved line with no reason is empty"

    # A received document released on the line puts "Released ... (received)." first.
    rr = _rr(world, rows[1])
    world.db.add(
        OrderInquiryReleasedLink(
            id=_uid(), company_id=world.company_id, row_id=rows[1].id,
            reserve_request_row_id=rr.id, po_line_id=_purchase_order(world.db, world.company_id)["line"].id,
            document="ZZT-PO-RF1", qty=Decimal("5"),
        )
    )
    world.db.commit()
    table = _table(_note_mails(world)[0]["body_html"])
    reason = {r[3]: r for r in table["rows"]}[f"{MARKER}-B"][-1]
    assert reason.startswith("Released ZZT-PO-RF1 (received)."), reason
    assert reason.endswith("only 20 on hand"), reason


def test_ac_rf_16_no_reason_given_for_short_lines_without_one(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _answered(
        client, world, one, [("50", "50", None), ("50", "20", "placeholder"), ("50", "0", "placeholder")]
    )
    legacy = [_rr(world, row) for row in rows[1:]]
    for rr in legacy:
        rr.reason = None  # a legacy answer with no reason
    world.db.commit()
    table = _table(_note_mails(world)[0]["body_html"])
    assert table["headings"][-1] == "REASON"
    by_item = {r[3]: r[-1] for r in table["rows"]}
    assert by_item[f"{MARKER}-A"] == ""
    assert by_item[f"{MARKER}-B"] == "No reason given"
    assert by_item[f"{MARKER}-C"] == "No reason given"


def test_ac_rf_17_rejected_red_partial_amber_bold(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    _answered(client, world, one, [("50", "50", None), ("50", "20", "short"), ("50", "0", "none")])
    table = _table(_note_mails(world)[0]["body_html"])
    at = table["headings"].index("STATUS")
    styles = {row[at]["text"]: str(row[at]["attrs"].get("style", "")).lower().replace(" ", "") for row in table["cells"]}
    assert "#b91c1c" in styles["Rejected"] and ("font-weight:600" in styles["Rejected"] or "bold" in styles["Rejected"])
    assert "#92400e" in styles["Partial 20 of 50"] and ("font-weight:600" in styles["Partial 20 of 50"] or "bold" in styles["Partial 20 of 50"])
    assert "#b91c1c" not in styles["Reserved 50"] and "#92400e" not in styles["Reserved 50"]


# --------------------------------------------------------------------------------- #
# C. Words                                                                           #
# --------------------------------------------------------------------------------- #


def test_ac_rf_18_request_words_one_oi_and_batch(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    raiser = _raiser(world, "CS One")
    joey = _name(world, world.requester)
    inquiry, _rows, _ = _parked(
        client, world, raiser, [_line("A"), _line("B"), _line("C")], so_no="SO-RF-0018"
    )
    mail = _req_mails(client)[0]
    what = f"{inquiry.inquiry_no} - SO-RF-0018, raised by {_name(world, raiser)}"
    short = f"{inquiry.inquiry_no} raised by {_name(world, raiser)}"
    assert mail["subject"] == f"Reserve request: {what} ({joey})"
    text = _visible(mail["body_html"])
    assert f"{short} needs your reserve" in text
    assert f"{joey} asks CS to reserve stock on {short} (3 lines)." in text

    second, _r2, _ = _parked(client, world, raiser, [_line("A")])
    mail = _req_mails(client)[0]
    batch = f"2 order inquiries raised by {_name(world, raiser)}"
    assert mail["subject"] == f"Reserve requests: {batch} ({joey})"
    text = _visible(mail["body_html"])
    assert f"{batch} need your reserve" in text
    assert f"{joey} asks CS to reserve stock on {batch} (4 lines)." in text
    assert second.inquiry_no in text


def test_ac_rf_18_request_words_unknown_raiser_drops_the_raised_by_part(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    _set_fixed_request_to(world)
    inquiry, _rows, _ = _parked(client, world, None, [_line("A")], so_no="SO-RF-0019")
    mail = _req_mails(client)[0]
    assert mail["subject"] == f"Reserve request: {inquiry.inquiry_no} - SO-RF-0019 ({_name(world, world.requester)})"
    text = _visible(mail["body_html"])
    assert f"{inquiry.inquiry_no} needs your reserve" in text
    assert "raised by" not in text and "raised by" not in mail["subject"]


def test_ac_rf_18_reserved_words_all_reserved_some_short_all_rejected(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    raiser = _raiser(world, "CS One")
    cs = _name(world, world.reserver)
    by = _name(world, raiser)

    # all reserved, 5 lines
    a, _ = _answered(client, world, raiser, [("50", "50", None)] * 5, so_no="SO-RF-0020")
    mail = _note_mails(world)[0]
    what, short = f"{a.inquiry_no} - SO-RF-0020, raised by {by}", f"{a.inquiry_no} raised by {by}"
    assert mail["subject"] == f"Reserved: {what} ({cs})"
    text = _visible(mail["body_html"])
    assert f"Reserved: {short}" in text and f"{cs} reserved all 5 lines on {short}." in text
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as c:
        _ok(c.post(NOTE_SEND))
    world.db.commit()

    # one line, singular
    b, _ = _answered(client, world, raiser, [("50", "50", None)], so_no="SO-RF-0021")
    text = _visible(_note_mails(world)[0]["body_html"])
    assert f"{cs} reserved 1 line on {b.inquiry_no} raised by {by}." in text
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as c:
        _ok(c.post(NOTE_SEND))
    world.db.commit()

    # 10 lines: 8 reserved, 1 partial, 1 rejected
    answers = [("50", "50", None)] * 8 + [("50", "20", "short")] + [("50", "0", "none")]
    c_, _ = _answered(client, world, raiser, answers, so_no="SO-RF-0022")
    mail = _note_mails(world)[0]
    what, short = f"{c_.inquiry_no} - SO-RF-0022, raised by {by}", f"{c_.inquiry_no} raised by {by}"
    assert mail["subject"] == f"Reserved: {what}, 1 partial, 1 rejected ({cs})"
    text = _visible(mail["body_html"])
    assert f"Reserved: {short}, 1 partial, 1 rejected" in text
    assert f"{cs} answered 10 lines on {short}: 8 reserved, 1 partial, 1 rejected." in text
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as c:
        _ok(c.post(NOTE_SEND))
    world.db.commit()

    # 5 lines, all rejected; 0 reserved is left out of a mixed email, "Rejected:" leads this one
    d, _ = _answered(client, world, raiser, [("50", "0", "none")] * 5, so_no="SO-RF-0023")
    mail = _note_mails(world)[0]
    what, short = f"{d.inquiry_no} - SO-RF-0023, raised by {by}", f"{d.inquiry_no} raised by {by}"
    assert mail["subject"] == f"Rejected: {what} ({cs})"
    text = _visible(mail["body_html"])
    assert f"Rejected: {short}" in text and f"{cs} rejected 5 lines on {short}." in text
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as c:
        _ok(c.post(NOTE_SEND))
    world.db.commit()

    # no 'reserved' count when nothing was reserved but something was partial
    e, _ = _answered(client, world, raiser, [("50", "20", "short"), ("50", "0", "none")], so_no="SO-RF-0024")
    text = _visible(_note_mails(world)[0]["body_html"])
    assert "0 reserved" not in text
    assert f"answered 2 lines on {e.inquiry_no} raised by {by}: 1 partial, 1 rejected." in text


def test_ac_rf_18_reserved_words_batch_and_unknown_raiser(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    raiser = _raiser(world, "CS One")
    cs, by = _name(world, world.reserver), _name(world, raiser)
    _answered(client, world, raiser, [("50", "50", None), ("50", "50", None)])
    _answered(client, world, raiser, [("50", "50", None)])
    mail = _note_mails(world)[0]
    batch = f"2 order inquiries raised by {by}"
    assert mail["subject"] == f"Reserved: {batch} ({cs})"
    text = _visible(mail["body_html"])
    assert f"Reserved: {batch}" in text and f"{cs} reserved all 3 lines on {batch}." in text
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as c:
        _ok(c.post(NOTE_SEND))
    world.db.commit()

    nobody, _ = _answered(client, world, None, [("50", "50", None)], so_no="SO-RF-0025")
    _set_automation(world, RESERVED_TRIGGER, config={"user_ids": [world.requester]})
    mail = _note_mails(world)[0]
    assert mail["subject"] == f"Reserved: {nobody.inquiry_no} - SO-RF-0025 ({cs})"
    assert "raised by" not in _visible(mail["body_html"])


def test_ac_rf_19_footer_lines_notes_and_still_to_reserve(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    raiser = _raiser(world, "CS One")
    joey, cs = _name(world, world.requester), _name(world, world.reserver)
    lines = [_line("A"), _line("B")]
    inquiry, rows = _oi(world, raiser, lines)
    _ask(client, world, inquiry, rows, lines, note="Need by Friday")
    text = _visible(_req_mails(client)[0]["body_html"])
    assert f"Requested by {joey} on {_today()}." in text
    assert f"Note ({inquiry.inquiry_no}): Need by Friday" in text

    other, other_rows = _oi(world, raiser, [_line("C")])
    _ask(client, world, other, other_rows, park=False)
    _commit(world, other, reserves=[_reserve(world, other_rows[0], "50")], park_notice=True)
    # an open row on the answered request: request 2 rows, answer 1
    inquiry2, rows2 = _oi(world, raiser, lines)
    _ask(client, world, inquiry2, rows2, lines, park=False)
    _commit(world, inquiry2, reserves=[_reserve(world, rows2[0], "50")], park_notice=True)
    text = _visible(_note_mails(world)[0]["body_html"])
    assert f"Answered by {cs} on {_today()}." in text
    assert "1 line still to reserve." in text


# --------------------------------------------------------------------------------- #
# D. Button                                                                          #
# --------------------------------------------------------------------------------- #


def test_ac_rf_20_batch_button_lists_exactly_this_emails_ois_sorted(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one, two = _raiser(world, "CS One"), _raiser(world, "CS Two")
    made = [_parked(client, world, one)[0] for _ in range(3)]
    _parked(client, world, two)  # another CS: a different email
    mails = _req_mails(client)
    batch = next(m for m in mails if len(_table(m["body_html"])["rows"]) == 3)
    href, label = _button(batch["body_html"])
    assert label == "View these 3 order inquiries"
    assert href == f"{_link_base()}?inquiry_no=" + ",".join(sorted(i.inquiry_no for i in made))

    _answered(client, world, one, [("50", "50", None)])
    _answered(client, world, one, [("50", "50", None)])
    href, label = _button(_note_mails(world)[0]["body_html"])
    assert label == "View these 2 order inquiries" and "?inquiry_no=" in href


def test_ac_rf_21_one_oi_button_goes_to_the_oi(sn, monkeypatch):
    from app.services.automation_triggers import build_order_inquiry_link

    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, _rows, request_id = _parked(client, world, one)
    href, label = _button(_req_mails(client)[0]["body_html"])
    assert label == "View this order inquiry"
    assert href == f"{build_order_inquiry_link(inquiry.id)}?reserve={request_id}"
    assert "inquiry_no=" not in href

    got, _ = _answered(client, world, one, [("50", "50", None)])
    href, label = _button(_note_mails(world)[0]["body_html"])
    assert label == "View this order inquiry"
    assert href.startswith(build_order_inquiry_link(got.id)) and "inquiry_no=" not in href


def test_ac_rf_22_headers_inquiry_no_filter_exact_match(sn):
    client, world = sn
    numbers = ["OI-2610-002", "OI-2610-0025", "OI-2610-003"]
    made = []
    for no in numbers:
        inquiry = _new_oi(world, world.requester)
        inquiry.inquiry_no = no
        made.append(inquiry)
    world.db.commit()
    foreign_inquiry_id = _foreign_reserve_request(world.db)[2]
    with company_scope(world.db, None):
        foreign = world.db.get(OrderInquiry, foreign_inquiry_id)
        foreign.inquiry_no = "OI-2610-007"
        world.db.commit()
    by_no = {i.inquiry_no: i.id for i in made}

    def listed(params):
        body = _ok(client.get(HEADERS_URL, params={"state": "all", "limit": 100, **params}))
        return {row["inquiry_no"] for row in body["data"]}

    assert listed({"inquiry_no": "OI-2610-002"}) == {"OI-2610-002"}, "exact, not a prefix"
    assert listed({"inquiry_no": "OI-2610-002,OI-2610-003"}) == {"OI-2610-002", "OI-2610-003"}
    both = _ok(
        client.get(
            HEADERS_URL,
            params=[("state", "all"), ("inquiry_no", "OI-2610-002"), ("inquiry_no", "OI-2610-0025")],
        )
    )
    assert {r["inquiry_no"] for r in both["data"]} == {"OI-2610-002", "OI-2610-0025"}, "repeated params"
    assert listed({"inquiry_no": "OI-2610-002,OI-9999-999"}) == {"OI-2610-002"}, "unknown adds nothing"
    assert listed({"inquiry_no": "OI-9999-999"}) == set()
    assert set(by_no) <= listed({"inquiry_no": ""}), "an empty value is ignored"
    assert len(listed({"inquiry_no": ""})) >= 4
    assert listed({"inquiry_no": "OI-2610-007"}) == set(), "another company's OI never shows"


def test_ac_rf_25_inquiry_no_has_no_200_value_cap_other_filters_keep_theirs(sn):
    client, world = sn
    inquiry = _new_oi(world, world.requester)
    inquiry.inquiry_no = "OI-2610-900"
    world.db.commit()
    numbers = ["OI-2610-900"] + [f"OI-9999-{n:03d}" for n in range(200)]
    assert len(numbers) == 201
    response = client.get(HEADERS_URL, params={"state": "all", "inquiry_no": ",".join(numbers)})
    assert response.status_code == 200, response.text
    assert [r["inquiry_no"] for r in response.json()["data"]] == ["OI-2610-900"]
    # Repeated params take the same path.
    repeated = client.get(HEADERS_URL, params=[("state", "all")] + [("inquiry_no", n) for n in numbers])
    assert repeated.status_code == 200, repeated.text
    # Another filter on the same route keeps its cap.
    capped = client.get(HEADERS_URL, params={"raised_by": ",".join(_uid() for _ in range(201))})
    assert capped.status_code == 422, capped.text


# --------------------------------------------------------------------------------- #
# E. One email per raising CS                                                        #
# --------------------------------------------------------------------------------- #


def test_ac_rf_30_two_raisers_two_emails(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    cs_fixed = _set_fixed_request_to(world)
    one, two = _raiser(world, "CS One"), _raiser(world, "CS Two")
    a, _ra, _ = _parked(client, world, one, [_line("A"), _line("B")])
    b, _rb, _ = _parked(client, world, two, [_line("C")])
    joey = _name(world, world.requester)
    mails = _req_mails(client)
    assert len(mails) == 2, [m["subject"] for m in mails]
    by_oi = {_table(m["body_html"])["rows"][0][0]: m for m in mails}
    mail_a, mail_b = by_oi[a.inquiry_no], by_oi[b.inquiry_no]
    assert {r[0] for r in _table(mail_a["body_html"])["rows"]} == {a.inquiry_no}
    assert {r[0] for r in _table(mail_b["body_html"])["rows"]} == {b.inquiry_no}
    assert mail_a["to"]["name"] == mail_b["to"]["name"] == f"{MARKER} CS Fixed"
    assert set(_names(mail_a["cc"])) == {_name(world, one), joey}
    assert set(_names(mail_b["cc"])) == {_name(world, two), joey}
    assert _name(world, two) not in _names(mail_a["cc"]) and _name(world, one) not in _names(mail_b["cc"])
    assert cs_fixed


def test_ac_rf_31_notices_two_raisers_two_emails(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one, two = _raiser(world, "CS One"), _raiser(world, "CS Two")
    a, _ = _answered(client, world, one, [("50", "50", None)])
    b, _ = _answered(client, world, two, [("50", "50", None)])
    mails = _note_mails(world)
    assert len(mails) == 2, [m["subject"] for m in mails]
    by_oi = {_table(m["body_html"])["rows"][0][0]: m for m in mails}
    mail_a, mail_b = by_oi[a.inquiry_no], by_oi[b.inquiry_no]
    joey = _name(world, world.requester)
    assert mail_a["to"]["name"] == mail_b["to"]["name"] == joey
    assert _name(world, one) in _names(mail_a["cc"]) and _name(world, two) not in _names(mail_a["cc"])
    assert _name(world, two) in _names(mail_b["cc"]) and _name(world, one) not in _names(mail_b["cc"])
    assert {r[0] for r in _table(mail_a["body_html"])["rows"]} == {a.inquiry_no}


def test_ac_rf_32_two_ois_one_raiser_stay_one_email(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    _set_fixed_request_to(world)
    one = _raiser(world, "CS One")
    _parked(client, world, one)
    _parked(client, world, one)
    mails = _req_mails(client)
    assert len(mails) == 1 and len(_table(mails[0]["body_html"])["rows"]) == 2
    _answered(client, world, one, [("50", "50", None)])
    _answered(client, world, one, [("50", "50", None)])
    assert len(_note_mails(world)) == 1


def test_ac_rf_33_legacy_owner_raiser_is_a_raiser_like_any_other(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    _set_fixed_request_to(world)
    one = _raiser(world, "CS One")
    owner = _raiser(world, "Owner Account")
    _parked(client, world, one)
    legacy, _r, _ = _parked(client, world, owner)
    mails = _req_mails(client)
    assert len(mails) == 2
    mine = next(m for m in mails if _table(m["body_html"])["rows"][0][0] == legacy.inquiry_no)
    assert _name(world, owner) in _names(mine["cc"]), "that account is on Cc"
    assert _name(world, one) not in _names(mine["cc"])
    assert "legacy" not in _visible(mine["body_html"]).lower()


def test_ac_rf_34_unknown_raiser_is_its_own_email_with_no_raiser_on_cc(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    _set_fixed_request_to(world)
    one = _raiser(world, "CS One")
    _parked(client, world, one)
    orphan, _r, _ = _parked(client, world, None)
    mails = _req_mails(client)
    assert len(mails) == 2, [m["subject"] for m in mails]
    mine = next(m for m in mails if _table(m["body_html"])["rows"][0][0] == orphan.inquiry_no)
    assert _names(mine["cc"]) == [_name(world, world.requester)], "no raiser on Cc"
    assert len(_table(mine["body_html"])["rows"]) == 1, "not merged into another CS's email"


def test_ac_rf_35_preview_equals_send_and_counts_agree(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    _set_fixed_request_to(world)
    one, two = _raiser(world, "CS One"), _raiser(world, "CS Two")
    _parked(client, world, one, [_line("A"), _line("B")])
    _parked(client, world, one)
    _parked(client, world, two)
    preview = _ok(client.post(REQ_PREVIEW))
    assert len(preview["emails"]) == 2 and preview["inquiry_total"] == 3
    sent = _ok(client.post(REQ_SEND))
    world.db.commit()
    assert sent["emails_sent"] == len(preview["emails"]) == 2
    assert sent["items_sent"] == preview["inquiry_total"] == 3
    rendered = sorted((_render(world, c)["subject"], _table(_render(world, c)["body_html"])["rows"]) for c in _requested_calls(calls))
    shown = sorted((m["subject"], _table(m["body_html"])["rows"]) for m in preview["emails"])
    assert rendered == shown, "the email sent is the email previewed"

    # notices too
    _answered(client, world, one, [("50", "50", None)])
    _answered(client, world, two, [("50", "50", None)])
    note_preview = None
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as cs:
        note_preview = _ok(cs.post(NOTE_PREVIEW))
        note_sent = _ok(cs.post(NOTE_SEND))
    world.db.commit()
    assert note_sent["emails_sent"] == len(note_preview["emails"]) == 2
    assert note_sent["items_sent"] == note_preview["inquiry_total"] == 2


def test_ac_rf_36_different_to_persons_get_separate_emails(sn, monkeypatch):
    """Existing behaviour (dev config: To = the raiser); must survive."""
    client, world, _calls = _setup(sn, monkeypatch)
    one, two = _raiser(world, "CS One"), _raiser(world, "CS Two")
    _parked(client, world, one)
    _parked(client, world, two)
    mails = _req_mails(client)
    assert {m["to"]["name"] for m in mails} == {_name(world, one), _name(world, two)}


# --------------------------------------------------------------------------------- #
# F. One OI, several requests                                                        #
# --------------------------------------------------------------------------------- #


def test_ac_rf_40_parked_one_oi_two_requests_one_email_all_stamped(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _oi(world, one, [_line("A"), _line("B")])
    r1 = _ask(client, world, inquiry, rows[:1], [_line("A")])
    r2 = _ask(client, world, inquiry, rows[1:], [_line("B")])
    mails = _req_mails(client)
    assert len(mails) == 1, [m["subject"] for m in mails]
    table = _table(mails[0]["body_html"])
    assert [r[3] for r in table["rows"]] == [f"{MARKER}-A", f"{MARKER}-B"]
    assert {r[0] for r in table["rows"]} == {inquiry.inquiry_no}
    sent = _ok(client.post(REQ_SEND))
    world.db.commit()
    assert sent["emails_sent"] == 1 and sent["items_sent"] == 1
    assert len(_requested_calls(calls)) == 1
    for rid in (r1, r2):
        world.db.expire_all()
        request = world.db.query(OrderInquiryReserveRequest).filter_by(id=rid).one()
        assert request.parked_at is None, "every request in the email is stamped sent"


def test_ac_rf_40_parked_notices_one_oi_two_requests_one_email_all_stamped(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _oi(world, one, [_line("A"), _line("B")])
    _ask(client, world, inquiry, rows[:1], [_line("A")], park=False)
    _ask(client, world, inquiry, rows[1:], [_line("B")], park=False)
    _commit(world, inquiry, reserves=[_reserve(world, r, "50") for r in rows], park_notice=True)
    mails = _note_mails(world)
    assert len(mails) == 1, [m["subject"] for m in mails]
    assert len(_table(mails[0]["body_html"])["rows"]) == 2
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as cs:
        sent = _ok(cs.post(NOTE_SEND))
    world.db.commit()
    assert sent["emails_sent"] == 1 and len(_reserved_calls(calls)) == 1
    for row in rows:
        rr = _rr(world, row)
        assert rr.notified_qty == Decimal("50") and rr.notice_parked_at is None


def test_ac_rf_41_immediate_commit_two_requests_same_requester_one_email(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _oi(world, one, [_line("A"), _line("B")])
    _ask(client, world, inquiry, rows[:1], [_line("A")], park=False)
    _ask(client, world, inquiry, rows[1:], [_line("B")], park=False)
    calls.clear()
    _commit(world, inquiry, reserves=[_reserve(world, r, "50") for r in rows])
    reserved = _reserved_calls(calls)
    assert len(reserved) == 1, "one email for the one OI and one requester"
    table = _table(_render(world, reserved[0])["body_html"])
    assert [r[3] for r in table["rows"]] == [f"{MARKER}-A", f"{MARKER}-B"]


def test_ac_rf_42_immediate_commits_on_two_ois_are_two_emails(sn, monkeypatch):
    """Existing behaviour."""
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    for _ in range(2):
        inquiry, rows = _oi(world, one, [_line("A")])
        _ask(client, world, inquiry, rows, park=False)
    calls.clear()
    for inquiry in world.db.query(OrderInquiry).filter(OrderInquiry.raised_by == one).all():
        rows = world.db.query(OrderInquiryReserveRequestRow).join(
            OrderInquiryReserveRequest, OrderInquiryReserveRequest.id == OrderInquiryReserveRequestRow.request_id
        ).filter(OrderInquiryReserveRequest.order_inquiry_id == inquiry.id).all()
        with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as cs:
            response = cs.post(
                COMMIT_URL(inquiry.id),
                json={"reserves": [{"row_id": r.row_id, "warehouse_id": world.site.id, "qty_reserved": "50"} for r in rows]},
            )
        assert response.status_code == 200, response.text
        world.db.commit()
    assert len(_reserved_calls(calls)) == 2


def test_ac_rf_43_immediate_two_requesters_on_one_oi_are_two_emails(sn, monkeypatch):
    """Guard: the merge in AC-RF-41 must not cross requesters."""
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    inquiry, rows = _oi(world, one, [_line("A"), _line("B")])
    _ask(client, world, inquiry, rows[:1], [_line("A")], park=False)
    with _as(world.db, world.reserver, RESERVER_PERMISSIONS) as cs:
        response = cs.post(
            REQUEST_URL(inquiry.id),
            json={"rows": [{"row_id": rows[1].id, "qty_requested": "50", "warehouse_id": world.site.id}]},
        )
        assert response.status_code == 201, response.text
    world.db.commit()
    calls.clear()
    _commit(world, inquiry, reserves=[_reserve(world, r, "50") for r in rows])
    assert len(_reserved_calls(calls)) == 2


def test_ac_rf_44_immediate_request_sends_the_same_table_as_parked(sn, monkeypatch):
    client, world, calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    lines = [_line("A", qty="80", ask="30"), _line("B")]
    live, live_rows = _oi(world, one, lines, so_no="SO-RF-0044")
    _ask(client, world, live, live_rows, lines, park=False)
    rendered = _render(world, _requested_calls(calls)[0])
    live_table = _table(rendered["body_html"])
    assert live_table["headings"] == REQUEST_HEADINGS
    assert rendered["subject"].startswith("Reserve request: ") and ", raised by " in rendered["subject"]

    parked, _pr, _ = _parked(client, world, one, lines, so_no="SO-RF-0045")
    parked_table = _table(_req_mails(client)[0]["body_html"])
    swap = lambda rows, no: [[no if c == live.inquiry_no else c for c in r] for r in rows]  # noqa: E731
    strip = lambda rows: [r[1:2] + r[3:] for r in rows]  # noqa: E731  (OI NO and S/O NO differ by seed)
    assert strip(live_table["rows"]) == strip(parked_table["rows"])
    assert live_table["rows"][0][0] == live.inquiry_no and parked_table["rows"][0][0] == parked.inquiry_no


# --------------------------------------------------------------------------------- #
# G. Template migration                                                              #
# --------------------------------------------------------------------------------- #


def _tpl(db, code):
    return db.execute(
        sa.text("SELECT subject, layout_json, body_text FROM email_templates WHERE code = :c"), {"c": code}
    ).first()


def _columns(db):
    return db.execute(
        sa.text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() ORDER BY 1, 2"
        )
    ).all()


def test_ac_rf_50_seeded_templates_are_updated_in_place(sn):
    _client, world = sn
    mods = _chain_to_0001(world)
    assert NEW_REV in mods, f"migration {NEW_REV} does not exist yet"
    before = {c: _tpl(world.db, c) for c in (REQUEST_CODE, RESERVED_CODE)}
    old = mods["oisn_0001_staged_notify"]
    for code in before:
        assert before[code][0] == old._bulk_subject(code), "precondition: still oisn_0001's template"
    columns = _columns(world.db)
    _run(mods[NEW_REV], world.db)
    world.db.commit()
    for code in before:
        after = _tpl(world.db, code)
        assert after[0] != before[code][0], f"{code} subject"
        assert after[1] != before[code][1], f"{code} layout_json"
        assert after[2] != before[code][2], f"{code} body_text"
        assert after[1]["width"] == "wide"
        assert "OI NO" in after[2], "the plain text carries the new table"
    assert _columns(world.db) == columns, "no schema change"


def test_ac_rf_51_admin_edited_template_is_left_alone_and_batches_still_render(sn, monkeypatch):
    client, world = sn
    mods = _chain_to_0001(world)
    assert NEW_REV in mods, f"migration {NEW_REV} does not exist yet"
    world.db.execute(
        sa.text("UPDATE email_templates SET subject = :s WHERE code = :c"),
        {"s": "ADMIN {{ reserve.oi_count }}/{{ reserve.line_count }}/{{ reserve.more_count }}/{{ reserve.requests|length }}", "c": REQUEST_CODE},
    )
    world.db.execute(
        sa.text("UPDATE email_templates SET subject = :s WHERE code = :c"),
        {"s": "ADMINR {{ reserve.ordinal }}|{{ reserve.rows|length }}|{{ reserve.link }}", "c": RESERVED_CODE},
    )
    world.db.commit()
    edited = {c: _tpl(world.db, c) for c in (REQUEST_CODE, RESERVED_CODE)}
    _run(mods[NEW_REV], world.db)
    world.db.commit()
    assert {c: _tpl(world.db, c) for c in edited} == edited, "an admin-edited template is untouched"

    _register()
    _captured_dispatches(monkeypatch)
    one = _raiser(world, "CS One")
    for _ in range(3):
        _parked(client, world, one)
    mails = _req_mails(client)
    assert len(mails) == 1
    assert mails[0]["subject"] == "ADMIN 3/3/0/3", mails[0]["subject"]
    assert mails[0]["body_html"], "the batch renders without failing"

    _answered(client, world, one, [("50", "50", None)])
    mail = _note_mails(world)[0]
    ordinal, rows_len, link = mail["subject"].removeprefix("ADMINR ").split("|")
    assert (ordinal, rows_len) == ("1", "1"), mail["subject"]
    assert "/project-sales/order-inquiries" in link


def test_ac_rf_52_upgrade_is_idempotent_downgrade_restores_only_untouched_rows(sn):
    _client, world = sn
    mods = _chain_to_0001(world)
    assert NEW_REV in mods, f"migration {NEW_REV} does not exist yet"
    module = mods[NEW_REV]
    seeded = {c: _tpl(world.db, c) for c in (REQUEST_CODE, RESERVED_CODE)}
    _run(module, world.db)
    once = {c: _tpl(world.db, c) for c in seeded}
    _run(module, world.db)
    assert {c: _tpl(world.db, c) for c in seeded} == once, "second upgrade changes nothing"
    assert once != seeded

    world.db.execute(
        sa.text("UPDATE email_templates SET subject = 'ADMIN EDIT' WHERE code = :c"), {"c": REQUEST_CODE}
    )
    _run(module, world.db, "downgrade")
    assert _tpl(world.db, REQUEST_CODE)[0] == "ADMIN EDIT", "an edited row is left alone on downgrade"
    assert _tpl(world.db, RESERVED_CODE) == seeded[RESERVED_CODE], "an untouched row goes back to oisn_0001"


def test_ac_rf_53_revision_id_length_and_no_full_template_code_in_the_file():
    mods = _scripts()
    assert NEW_REV in mods, f"migration {NEW_REV} does not exist yet"
    module = mods[NEW_REV]
    assert module.revision == NEW_REV and len(module.revision) <= 32
    text = Path(module.__file__).read_text()
    assert REQUEST_CODE not in text and RESERVED_CODE not in text
    assert "order_inquiry_reserve_requested" + "_default" not in text


# --------------------------------------------------------------------------------- #
# H. Size and the export                                                             #
# --------------------------------------------------------------------------------- #


def test_ac_rf_60_105_line_reserved_email_stays_under_the_gmail_clip(sn, monkeypatch):
    client, world, _calls = _setup(sn, monkeypatch)
    one = _raiser(world, "CS One")
    for n in range(7):
        lines = [_line(chr(65 + i), qty="100", ask="50") for i in range(15)]
        inquiry, rows = _oi(world, one, lines, customer="CUSTOMER A WITH A LONGER NAME", project="PROJECT X TOWER")
        _ask(client, world, inquiry, rows, lines, park=False)
        reserves = [_reserve(world, r, "50") for r in rows]
        if n == 0:
            reserves[0] = {**_reserve(world, rows[0], "20"), "reason": "only 20 on hand"}
        _commit(world, inquiry, reserves=reserves, park_notice=True)
    mails = _note_mails(world)
    assert len(mails) == 1
    table = _table(mails[0]["body_html"])
    assert len(table["rows"]) == 105 and table["headings"][-1] == "REASON"
    assert len(mails[0]["body_html"].encode()) <= 102 * 1024, len(mails[0]["body_html"].encode())


def test_ac_rf_70_export_headings_unchanged():
    from app.services.order_inquiry_worklist_service import EXPORT_HEADINGS

    assert EXPORT_HEADINGS == (
        "SO DATE", "S/O NO", "ITEM CODE", "QTY", "REQUESTED RESERVE", "RESERVED", "TOTAL QTY",
        "DELIVERY DATE", "PROJECT/CUSTOMER", "SUPPLIER", "PO NO ", "LOCATION", "ACKNOWLEDGED",
        "TAKEN", "REMAINING", "SUGGESTED", "CHANGE QUANTITY", "CHANGE DATE", "REMARK",
    )
