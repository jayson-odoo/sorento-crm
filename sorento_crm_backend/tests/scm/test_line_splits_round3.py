"""OI-LINE-SPLIT build round 3 (UAC section G, AC-G1 to AC-G7): refer back after Confirm, the
AutoCount extra row, no CANCEL from splits, one email / Excel row per split, one remark function.

Contract: `documentation/plans/scm/oi-line-split-16oct-acceptance-criteria.md` section G, the card
`CARD-oi-line-split-refer-back-18oct.md` (owner answers) and mock v5 sections 2, 5, 6, 7.

The owner's case (SO417636 CSK14B BRW-BB, masked), one item at one location:
- AutoCount: 480 417 @ 20/10/2026 -> 14 @ 20/09/2026; 608 192 -> 632 (20/11/2026 kept);
  752 504 @ 20/12/2026 -> 649 @ 02/01/2027.
- Splits: 480 = 14 @ 20/09/2026 own + 236 @ 20/11/2026 on 608 + 167 @ 20/11/2029 on 608;
  752 = 37 @ 20/11/2026 on 608 + 467 @ 02/01/2027 own. 608 is not split
  (192 + 236 + 167 + 37 = 632), 752 has an AutoCount extra of 649 - 467 = 182.
Crew ruling (18 Oct): 608's generated REMARK (its increase is all splits dropped on it, date
unchanged) is "REMAIN".

The email rows are read off the email actually SENT for the batch Confirm (`emails`), rendered
through the handover template as the `oihr_*` migrations leave it (every `oihr_*` from 0006 up,
chained in number order, the path a real database takes), so "QTY / DELIVERY on a line's first
row only" is asserted on the printed table, not on a data shape. Every row is seeded here.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from app.models.project_so import ACK_ACKNOWLEDGED
from app.services.scm.outstanding_diff import DATE_AND_QTY_CHANGED, QTY_CHANGED
from tests.scm.test_line_splits_api import _put, _sp, _url
from tests.scm.test_line_splits_outputs import emails  # noqa: F401 - the SENT handover
from tests.test_oi_handover_excel import stored  # noqa: F401 - autouse storage stub
from tests.test_planning_change_apply_on_board import (  # noqa: F401 - fixtures reused
    _build,
    _change,
    _confirm,
    _order_row,
    api,
    world,
)
from tests.test_planning_changes import (
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
)

D_480, D_480_NEW = date(2026, 10, 20), date(2026, 9, 20)
D_608 = date(2026, 11, 20)
D_752, D_752_NEW = date(2026, 12, 20), date(2027, 1, 2)
D_167 = date(2029, 11, 20)

#: line no -> (qty, date) before the AutoCount change, (qty, date) after it.
OWNER_CASE = {
    480: ((417, D_480), (14, D_480_NEW)),
    608: ((192, D_608), (632, D_608)),
    752: ((504, D_752), (649, D_752_NEW)),
}
TYPED = "UNDER PRE-ORDER, SO-XXXX03 ALREADY EMAILED"


class _S:
    pass


def _q(value):
    return None if value is None else Decimal(str(value))


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def _seed(api):
    """Lines 480 / 608 / 752 confirmed as Buy at their old figures (rows acknowledged), then the
    AutoCount change above as one pending batch. Mirror and core line numbers are both the
    AutoCount numbers, so every output names 480 / 608 / 752."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.core, s.line = {}, {}
    for no, ((qty, when), _after) in OWNER_CASE.items():
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=str(qty),
                          required_date=when)
        core.line_no = no
        line = _project_line(db, order, line_no=no, product=world.product, core_line=core)
        line.stock_location = world.own_wh.warehouse_code
        s.core[no], s.line[no] = core, line
    db.commit()
    r = _confirm(client, order.id, [
        _line_payload(s.line[no].id, buy_qty=str(before[0]))
        for no, (before, _after) in OWNER_CASE.items()
    ])
    assert r.status_code == 200, f"premise: the first Confirm (Buy) saves: {r.text}"
    for no in OWNER_CASE:
        row = _order_row(world, s.line[no])
        row.ack_state = ACK_ACKNOWLEDGED
        row.acknowledged_by = world.actor
        row.acknowledged_at = datetime.utcnow()
    db.commit()

    changes, ids = [], []
    for no, ((qty, when), (new_qty, new_when)) in OWNER_CASE.items():
        core, line = s.core[no], s.line[no]
        core.qty_ordered, line.qty = Decimal(str(new_qty)), Decimal(str(new_qty))
        core.required_date, line.delivery_date = new_when, new_when
        kind = DATE_AND_QTY_CHANGED if new_when != when else QTY_CHANGED
        changes.append(_change(kind, core, so_number=core_so.so_number, old_date=when,
                               new_date=new_when, old_qty=str(qty), new_qty=str(new_qty)))
        ids.append(str(core.id))
    db.commit()
    s.batch = _build(world, changes, core_so, ids)
    assert s.batch is not None, "premise: the pending change batch exists"
    return s


def _on(s, no):
    return str(s.line[no].id)


def _save(s, plan):
    """plan: {line no: [(qty, date, 480 | 608 | 752 | 'new' | 'cancel', remark)]}"""
    body = []
    for no, parts in plan.items():
        splits = []
        for qty, when, on, remark in parts:
            if on == "cancel":
                splits.append(_sp(qty, None, on=_on(s, no), cancel=True, remark=remark))
            else:
                splits.append(_sp(qty, when, on=None if on == "new" else _on(s, on), remark=remark))
        body.append({"line_id": _on(s, no), "splits": splits})
    r = _put(s, body)
    assert r.status_code == 200, f"premise: the splits save ({r.status_code}) {r.text}"


def _owner_plan(remark_14=""):
    """The owner's plan (case 1)."""
    return {
        480: [(14, D_480_NEW, 480, remark_14), (236, D_608, 608, ""), (167, D_167, 608, "")],
        752: [(37, D_608, 608, ""), (467, D_752_NEW, 752, "")],
    }


def _new_line_plan():
    """Mock section 7: 480's 236 and 167 left on New line (not dropped on any line)."""
    return {480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, D_167, "new", "")]}


def _confirm_batch(s, emails):
    """The board's one Confirm carrying the batch (it applies it). Returns the handovers the
    Confirm sent (never the first Confirm's)."""
    start = len(emails)
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[no].id, buy_qty=str(after[0]))
        for no, (_before, after) in OWNER_CASE.items()
    ], batch_id=str(s.batch.id))
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    return list(emails[start:])


def _get(s):
    r = s.client.get(_url(s.order.id))
    assert r.status_code == 200, r.text
    return r.json()


def _line(out, s, no):
    return next(x for x in out["lines"] if x["line_id"] == _on(s, no))


# ---------------------------------------------------------------------------
# the email as printed
# ---------------------------------------------------------------------------


def _template_migrations():
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    found = []
    for path in versions.glob("oihr_*.py"):
        m = re.match(r"oihr_(\d{4})_", path.name)
        if m and int(m.group(1)) >= 6:
            found.append((int(m.group(1)), path))
    assert found, "no oihr_* handover template migrations found"
    return [path for _n, path in sorted(found)]


def _load(path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"zzt_r3_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(handover):
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService
    from tests._pg_fixture import blank_session
    from tests.test_order_inquiry_handover_automation import _run_upgrade

    with blank_session() as db:
        for path in _template_migrations():
            _run_upgrade(_load(path), db)
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_handover" + "_default")
            .one()
        )
        ctx = {"handover": handover, "actor": {"name": "CS", "email": "cs@example.com"},
               "today": "18/10/2026"}
        return EmailTemplateService(db).render(template, ctx)


def _table_rows(html):
    from tests._email_body import authored_html

    if "<!--block:custom_text-->" in html:
        html = authored_html(html)
    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.S)
        if cells:
            rows.append([re.sub(r"<[^>]+>", "", c).strip() for c in cells])
    return rows


COLS = ("QTY", "NEW QTY", "DELIVERY", "NEW DATE", "REMARK")


def _printed(sent, cols=COLS):
    """Every item row of the sent handover email(s) as (QTY, NEW QTY, DELIVERY, NEW DATE,
    REMARK) (or `cols`), blank cells as "". The S/O header table and S/O group rows are
    skipped."""
    assert sent, "the batch Confirm sent no handover email"
    out = []
    for handover in sent:
        rows = _table_rows(_render(handover)["body_html"])
        head_at = next(i for i, row in enumerate(rows) if row and row[0] == "LOCATION")
        head = rows[head_at]
        for row in rows[head_at + 1:]:
            if len(row) != len(head):
                continue  # an S/O NO group row
            cell = dict(zip(head, row))
            out.append(tuple(cell.get(col, "") for col in cols))
    return out


def _has_block(rows, block):
    n = len(block)
    return any(rows[i:i + n] == block for i in range(len(rows) - n + 1))


def _sent_remarks(sent):
    return [str(ln.get("remark") or "") for h in sent for ln in h.get("lines") or []]


BLOCK_480 = [
    ("417", "14", "20/10/2026", "20/09/2026", "ADVANCE"),
    ("", "236", "", "20/11/2026", "DELAY"),
    ("", "167", "", "20/11/2029", "DELAY"),
]
ROW_608 = ("192", "632", "20/11/2026", "", "REMAIN")
BLOCK_752 = [
    ("504", "37", "20/12/2026", "20/11/2026", "ADVANCE"),
    ("", "467", "", "02/01/2027", "DELAY"),
    ("", "182", "", "02/01/2027", "ORDER 182"),
]


# ---------------------------------------------------------------------------
# AC-G1 refer back
# ---------------------------------------------------------------------------


def _figures(line):
    return (
        _q(line["base_qty"]), line["base_date"],
        _q(line.get("new_qty")), line.get("new_date"),
    )


EXPECTED_FIGURES = {
    480: (Decimal("417"), "2026-10-20", Decimal("14"), "2026-09-20"),
    608: (Decimal("192"), "2026-11-20", Decimal("632"), None),
    752: (Decimal("504"), "2026-12-20", Decimal("649"), "2027-01-02"),
}


def _today_candidates():
    from zoneinfo import ZoneInfo

    now = datetime.now(timezone.utc)
    return {
        date.today().isoformat(),
        now.date().isoformat(),
        now.astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat(),
    }


def test_g1_the_sheet_reads_the_same_change_before_and_after_the_confirm_that_applied_it(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    before = _get(s)
    assert "confirmed_at" in before, "AC-G1: the payload carries confirmed_at"
    assert before["confirmed_at"] is None, "a change is pending: no Confirmed date"
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(before, s, no)) == expected, (no, "before Confirm")

    _confirm_batch(s, emails)
    after = _get(s)
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(after, s, no)) == expected, (
            no, "AC-G1: after the Confirm that applied it, the change still reads base -> new",
            _figures(_line(after, s, no)))
    assert after.get("confirmed_at") in _today_candidates(), (
        "AC-G1: nothing pending and a Confirm on record: confirmed_at is the Confirm's date",
        after.get("confirmed_at"))


# ---------------------------------------------------------------------------
# AC-G3 the AutoCount extra
# ---------------------------------------------------------------------------


def test_g3_extra_is_autocount_qty_less_the_splits_sitting_on_the_line(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    for phase in ("before Confirm", "after Confirm"):
        if phase == "after Confirm":
            _confirm_batch(s, emails)
        out = _get(s)
        l480, l608, l752 = (_line(out, s, no) for no in (480, 608, 752))
        for no, line in ((480, l480), (608, l608), (752, l752)):
            assert "extra_qty" in line and "extra_remark" in line, (
                f"AC-G3: line {no} carries extra_qty / extra_remark ({phase})")
        assert _q(l752["extra_qty"]) == Decimal("182"), (phase, "649 - 467 own", l752["extra_qty"])
        assert l752["extra_remark"] == "ORDER 182", (phase, l752["extra_remark"])
        assert l608["extra_qty"] is None, (phase, "192 + 236 + 167 + 37 = 632", l608["extra_qty"])
        assert l608["extra_remark"] is None, (phase, l608["extra_remark"])
        assert l480["extra_qty"] is None, (phase, "14 own = 14", l480["extra_qty"])
        assert l480["extra_remark"] is None, (phase, l480["extra_remark"])


# ---------------------------------------------------------------------------
# AC-G4 no CANCEL from splits
# ---------------------------------------------------------------------------


def test_g4_the_owners_plan_tells_no_cancel_anywhere(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    sent = _confirm_batch(s, emails)
    rows = _printed(sent)
    assert not [r for r in rows if any("CANCEL" in c for c in r)], rows
    assert not [x for x in _sent_remarks(sent) if "CANCEL" in x], _sent_remarks(sent)
    assert _has_block(rows, BLOCK_480), ("480 prints 14 / 236 / 167", rows)


def test_g4_splits_left_on_new_line_are_deliveries_never_a_cancel(api, emails):
    """Mock section 7: 480 with 236 and 167 on New line printed "ADVANCE, CANCEL 403"; now each
    split is its own row (14 ADVANCE / 236 DELAY / 167 DELAY) and nothing says CANCEL."""
    s = _seed(api)
    _save(s, _new_line_plan())
    sent = _confirm_batch(s, emails)
    rows = _printed(sent)
    assert not [r for r in rows if any("CANCEL" in c for c in r)], rows
    assert not [x for x in _sent_remarks(sent) if "CANCEL" in x], _sent_remarks(sent)
    assert _has_block(rows, BLOCK_480), ("480 prints 14 / 236 / 167", rows)


def test_g4_an_explicit_cancel_split_still_prints_cancel_balance_and_nothing_else_cancels(api, emails):
    """Guard: CANCEL appears only for an `is_cancel` split. 480 = 14 own + 236 on New line +
    167 "Cancel this qty": the 236 is a DELAY row, the 167 is CANCEL BALANCE, no netted CANCEL."""
    s = _seed(api)
    _save(s, {480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, None, "cancel", "")]})
    sent = _confirm_batch(s, emails)
    rows = _printed(sent)
    assert ("417", "14", "20/10/2026", "20/09/2026", "ADVANCE") in rows, rows
    assert ("", "236", "", "20/11/2026", "DELAY") in rows, ("the New-line 236 is a delivery", rows)
    cancels = [r for r in rows if any("CANCEL" in c for c in r)]
    assert len(cancels) == 1, ("only the explicit cancel split says CANCEL", rows)
    assert cancels[0][1] == "167" and cancels[0][4].startswith("CANCEL BALANCE"), cancels


# ---------------------------------------------------------------------------
# AC-G6 the email: one row per split, the extra row, QTY / DELIVERY on the first row only
# ---------------------------------------------------------------------------


def test_g6_the_email_prints_one_row_per_split_under_its_line_and_the_extra_row(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    rows = _printed(_confirm_batch(s, emails))
    assert _has_block(rows, BLOCK_480), ("480: 14 / 236 / 167 under one line", rows)
    assert _has_block(rows, BLOCK_752), ("752: 37 / 467 / extra 182 under one line", rows)
    rows_608 = [r for r in rows if r[0] == "192"]
    assert len(rows_608) == 1, ("608 prints one row 192 -> 632", rows)
    assert rows_608[0][4] != "ORDER 440", ("the 440 moved, it is not bought", rows_608)
    assert rows_608[0] == ROW_608, ("crew ruling: 608 reads REMAIN", rows_608)
    assert len(rows) == 7, ("nothing else is told for these three lines", rows)


def test_g6_continuation_rows_blank_location_and_item_code_too(api, emails):
    """Mock section 5 (AC-G11): on a line's 2nd+ row LOCATION and ITEM CODE print blank, like
    QTY and DELIVERY; the line's first row carries them. 608 (one row) carries them too."""
    s = _seed(api)
    _save(s, _owner_plan())
    sent = _confirm_batch(s, emails)
    rows = _printed(sent, ("LOCATION", "ITEM CODE") + COLS)
    where = (s.world.own_wh.warehouse_code, s.world.product.product_code)
    blank = ("", "")
    block_480 = [where + BLOCK_480[0]] + [blank + r for r in BLOCK_480[1:]]
    block_752 = [where + BLOCK_752[0]] + [blank + r for r in BLOCK_752[1:]]
    assert _has_block(rows, block_480), ("480: 236 / 167 print no LOCATION / ITEM CODE", rows)
    assert _has_block(rows, block_752), ("752: 467 / 182 print no LOCATION / ITEM CODE", rows)
    assert where + ROW_608 in rows, ("608's one row carries LOCATION / ITEM CODE", rows)


def test_g6_a_typed_split_remark_replaces_the_generated_one(api, emails):
    s = _seed(api)
    _save(s, _owner_plan(remark_14=TYPED))
    rows = _printed(_confirm_batch(s, emails))
    first = ("417", "14", "20/10/2026", "20/09/2026", TYPED)
    assert _has_block(rows, [first] + BLOCK_480[1:]), (
        "the sheet's REMARK prints as it is, without the change word", rows)


# ---------------------------------------------------------------------------
# AC-G5 one generated remark, sent to the sheet
# ---------------------------------------------------------------------------


def test_g5_one_remark_function_serves_the_sheet_the_email_and_the_excel():
    from app.services import (
        order_inquiry_worklist_service,
        project_line_split_service,
        project_order_inquiry_service,
    )

    fn = getattr(project_line_split_service, "remark_for_row", None)
    assert callable(fn), "AC-G5: project_line_split_service.remark_for_row"
    assert getattr(project_order_inquiry_service, "remark_for_row", None) is fn, (
        "the email writer uses the same function object")
    assert getattr(order_inquiry_worklist_service, "remark_for_row", None) is fn, (
        "the worklist Excel uses the same function object")


def test_g5_remark_generated_per_split_is_what_the_email_prints_for_that_row(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    out = _get(s)
    l480, l752 = _line(out, s, 480), _line(out, s, 752)
    for no, line in ((480, l480), (752, l752)):
        for split in line["splits"]:
            assert "remark_generated" in split, f"AC-G5: line {no}'s splits carry remark_generated"
    got_480 = [x["remark_generated"] for x in l480["splits"]]
    got_752 = [x["remark_generated"] for x in l752["splits"]]
    assert got_480 == ["ADVANCE", "DELAY", "DELAY"], got_480
    assert got_752 == ["ADVANCE", "DELAY"], got_752

    rows = _printed(_confirm_batch(s, emails))
    printed_480 = next((rows[i:i + 3] for i in range(len(rows)) if rows[i][0] == "417"), [])
    printed_752 = next((rows[i:i + 3] for i in range(len(rows)) if rows[i][0] == "504"), [])
    assert [r[4] for r in printed_480] == got_480, (printed_480, got_480)
    assert [r[4] for r in printed_752] == got_752 + [l752.get("extra_remark")], (printed_752, got_752)


def test_g5_a_line_carries_the_generated_remark_of_its_own_row_608_remain(api, emails):
    """Each LINE carries `remark_generated` (its own unsplit / remaining row, `remark_for_row`).
    608 after the owner's Confirm: 192 -> 632, all of it moved in, date kept: "REMAIN" (crew
    ruling: moved qty never reads ORDER), the same text the email prints on 608's row."""
    s = _seed(api)
    _save(s, _owner_plan())
    sent = _confirm_batch(s, emails)
    l608 = _line(_get(s), s, 608)
    assert "remark_generated" in l608, "AC-G5: each line carries remark_generated"
    assert l608["remark_generated"] == "REMAIN", l608["remark_generated"]
    rows_608 = [r for r in _printed(sent) if r[0] == "192" and r[1] == "632"]
    assert len(rows_608) == 1, ("608 prints one row 192 -> 632", _printed(sent))
    assert rows_608[0][4] == l608["remark_generated"], (rows_608, l608["remark_generated"])


def test_g5_a_typed_remark_is_stored_and_the_generated_text_still_travels(api):
    s = _seed(api)
    _save(s, _owner_plan(remark_14=TYPED))
    first = _line(_get(s), s, 480)["splits"][0]
    assert first["remark"] == TYPED
    assert first.get("remark_generated") == "ADVANCE", first


# ---------------------------------------------------------------------------
# AC-G7 the worklist Excel
# ---------------------------------------------------------------------------


def _day(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return text


def _num(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).normalize()
    except Exception:  # noqa: BLE001 - a non-number prints as itself in the failure
        return value


def _excel_rows(s):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    _name, data = OrderInquiryWorklistService(s.db).export_xlsx(query=s.core_so.so_number)
    book = openpyxl.load_workbook(io.BytesIO(data))
    rows = list(book.worksheets[0].iter_rows(values_only=True))
    heads = list(rows[1])
    for need in ("QTY", "DELIVERY DATE", "CHANGE QUANTITY", "CHANGE DATE", "REMARK"):
        assert need in heads, (f"AC-G7: the OI Excel has a {need} column", heads)
    at = {h: heads.index(h) for h in ("QTY", "DELIVERY DATE", "CHANGE QUANTITY", "CHANGE DATE", "REMARK")}
    out = []
    for row in rows[2:]:
        if not any(v not in (None, "") for v in row):
            continue
        out.append((
            _num(row[at["QTY"]]), _day(row[at["DELIVERY DATE"]]),
            _num(row[at["CHANGE QUANTITY"]]), _day(row[at["CHANGE DATE"]]),
            (row[at["REMARK"]] or ""),
        ))
    return out


def _d(n):
    return Decimal(n)


EXCEL_480 = [
    (_d("417"), D_480, _d("14"), D_480_NEW, TYPED),
    (None, None, _d("236"), D_608, "DELAY"),
    (None, None, _d("167"), D_167, "DELAY"),
]
EXCEL_608 = (_d("192"), D_608, _d("632"), None, "REMAIN")
EXCEL_752 = [
    (_d("504"), D_752, _d("37"), D_608, "ADVANCE"),
    (None, None, _d("467"), D_752_NEW, "DELAY"),
    (None, None, _d("182"), D_752_NEW, "ORDER 182"),
]


def test_g7_the_excel_prints_the_same_rows_as_the_email(api, emails):
    """Mock section 6: QTY / DELIVERY DATE merged down a line's rows (blank under the first),
    CHANGE QUANTITY / CHANGE DATE the split's, REMARK the sheet's value else the generated one."""
    s = _seed(api)
    _save(s, _owner_plan(remark_14=TYPED))
    _confirm_batch(s, emails)
    rows = _excel_rows(s)
    assert not [r for r in rows if "CANCEL" in str(r[4])], rows
    assert _has_block(rows, EXCEL_480), ("480: 14 / 236 / 167", rows)
    assert _has_block(rows, EXCEL_752), ("752: 37 / 467 / extra 182", rows)
    assert EXCEL_608 in rows, ("608: 192 -> 632 REMAIN", rows)
    assert len(rows) == 7, rows


def test_g7_new_line_splits_are_excel_rows_never_a_cancel(api, emails):
    s = _seed(api)
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    rows = _excel_rows(s)
    assert not [r for r in rows if "CANCEL" in str(r[4])], rows
    block = [(_d("417"), D_480, _d("14"), D_480_NEW, "ADVANCE")] + EXCEL_480[1:]
    assert _has_block(rows, block), ("480's New-line splits print as their own rows", rows)


# ---------------------------------------------------------------------------
# AC-G10 the Confirm engine follows the plan (crew ruling (a), 18 Oct): split qty that is not
# moved onto another line stays purchasing's own OI worklist rows at the split dates, never a
# CANCEL BALANCE. Worklist, email and Excel then agree.
# ---------------------------------------------------------------------------


def _worklist(s, line):
    """Every OI worklist row of a mirror line, as (verb, state, qty, date)."""
    from app.models.project_so import OrderInquiryRow

    def qty(value):
        q = Decimal(str(value))
        return q.quantize(Decimal(1)) if q == q.to_integral_value() else q.normalize()

    return [
        (r.verb, r.state, qty(r.qty), r.delivery_date)
        for r in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).all()
    ]


def _live(rows):
    """The live (not cancelled) rows that ask purchasing for goods: (qty, date), sorted."""
    from app.models.project_so import INQUIRY_CANCELLED, IV_CANCEL_BALANCE

    return sorted(
        (qty, when) for verb, state, qty, when in rows
        if state != INQUIRY_CANCELLED and verb != IV_CANCEL_BALANCE
    )


def _cancel_balances(rows):
    from app.models.project_so import IV_CANCEL_BALANCE

    return [(state, qty) for verb, state, qty, _when in rows if verb == IV_CANCEL_BALANCE]


def test_g10_new_line_splits_stay_purchasings_own_worklist_rows(api, emails):
    """SO417636 480 (417 @ 20/10/2026 -> 14 @ 20/09/2026) with 236 @ 20/11/2026 and 167 @
    20/11/2029 left on New line: after Confirm 480's live OI rows are exactly 14 @ 20/09/2026,
    236 @ 20/11/2026 and 167 @ 20/11/2029, nothing is cancelled for that qty, and the email
    rows of 480 (ADVANCE / DELAY / DELAY) are the same three."""
    from app.models.project_so import INQUIRY_CANCELLED

    s = _seed(api)
    _save(s, _new_line_plan())
    sent = _confirm_batch(s, emails)
    rows = _worklist(s, s.line[480])
    expected = sorted([(_d("14"), D_480_NEW), (_d("236"), D_608), (_d("167"), D_167)])
    assert _live(rows) == expected, ("AC-G10: 480's worklist rows follow the plan", rows)
    assert _cancel_balances(rows) == [], ("AC-G10: no CANCEL BALANCE from a split", rows)
    assert not [
        r for r in rows if r[1] == INQUIRY_CANCELLED and r[2] in (_d("236"), _d("167"), _d("403"))
    ], ("nothing cancelled for the New-line qty", rows)

    printed = _printed(sent)
    assert _has_block(printed, BLOCK_480), ("480 prints 14 ADVANCE / 236 DELAY / 167 DELAY", printed)
    at = printed.index(BLOCK_480[0])
    emailed = sorted(
        (_d(r[1]), datetime.strptime(r[3], "%d/%m/%Y").date())
        for r in printed[at:at + len(BLOCK_480)]
    )
    assert emailed == _live(rows), ("the email rows are the worklist rows", emailed, rows)


def test_g10_an_explicit_cancel_split_still_makes_a_cancel_balance(api, emails):
    """Guard: 480 = 14 own + 236 on New line + 167 "Cancel this qty". The 167 still reaches
    purchasing as a CANCEL BALANCE, and it is the only one on the line."""
    s = _seed(api)
    _save(s, {480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, None, "cancel", "")]})
    _confirm_batch(s, emails)
    from app.models.project_so import INQUIRY_CANCELLED

    cancels = [
        (state, qty) for state, qty in _cancel_balances(_worklist(s, s.line[480]))
        if state != INQUIRY_CANCELLED
    ]
    assert cancels and all(qty == _d("167") for _state, qty in cancels), (
        "AC-G10 guard: the explicit cancel split is a CANCEL BALANCE of 167",
        _worklist(s, s.line[480]))
    assert len(cancels) == 1, ("one CANCEL BALANCE, nothing netted beside it", cancels)


#: The confirm tests' declined link moves (`test_line_splits_confirm.py`): the engine moves no
#: link, so line 2's splits stay its own worklist rows.
DECLINED = (
    "source_received_in_full",
    "source_received_cut_to_zero",
    "source_placed_no_link",
    "target_received_in_full",
    "target_placed_no_link",
    "target_did_not_grow_82",
    "target_did_not_grow_60",
)


def _declined(api, emails, case):
    """Seeds and confirms one declined move; returns (s, line 2, line 2's non-cancel splits as
    (qty, date))."""
    from app.models.project_so import INQUIRY_PLACED
    from tests.scm import test_line_splits_confirm as c

    d_2, d_18 = c.D_2, c.D_18
    if case.startswith("target_did_not_grow"):
        now = case.rsplit("_", 1)[1]
        s = c._so402757(api, with_splits=True, line18_now=now, batch_18=(now != "82"))
        c._confirm_both(s, buy_18=now)
        return s, s.line_2, [(2, d_2), (49, d_18)]
    if case == "source_received_cut_to_zero":
        s = c._lines(api, [(2, 51, d_2, 0), (18, 82, d_18, 133)])
        s.po_line.qty_received = Decimal("51")
        plan = [(51, d_18, 18)]
    elif case == "source_placed_no_link":
        s = c._lines(api, [(2, 100, d_2, 40), (18, 82, d_18, 132)], link_first=False)
        s.no[2][2].state = INQUIRY_PLACED
        plan = [(50, d_2, "own"), (50, d_18, 18)]
    else:
        s = c._lines(api, [(2, 51, d_2, 2), (18, 82, d_18, 131)])
        if case == "source_received_in_full":
            s.po_line.qty_received = Decimal("51")
        elif case == "target_received_in_full":
            _po, po_b = c._po_line(s.world, c._supplier(s.world), qty=82,
                                   expected_date=date(2026, 8, 25))
            c._link(s.world, s.no[18][2], po_b, qty=82, document="DOC-B")
            po_b.qty_received = Decimal("82")
        elif case == "target_placed_no_link":
            s.no[18][2].state = INQUIRY_PLACED
        plan = [(2, d_2, "own"), (49, d_18, 18)]
    s.db.commit()
    c._split(s, 2, plan)
    c._confirm_sent(s, emails)
    return s, s.no[2][1], [(qty, when) for qty, when, _on in plan]


def _missing(live, wanted):
    """The (qty, date) of `wanted` that no live row of `live` stands for (a multiset)."""
    left = list(live)
    out = []
    for qty, when in wanted:
        key = (_d(str(qty)), when)
        if key in left:
            left.remove(key)
        else:
            out.append(key)
    return out


@pytest.mark.parametrize("case", DECLINED)
def test_g10_a_declined_link_move_keeps_the_split_qty_as_its_own_worklist_rows(api, emails, case):
    """AC-G10: the engine declines the move (a received or placed row, a target that did not
    grow): each of line 2's splits stays line 2's own live OI row at the split's qty and date,
    and no CANCEL BALANCE is written for it."""
    s, origin, splits = _declined(api, emails, case)
    rows = _worklist(s, origin)
    assert _missing(_live(rows), splits) == [], (
        "AC-G10: every split of line 2 is a live worklist row at its date", case, rows)
    assert _cancel_balances(rows) == [], ("AC-G10: no CANCEL BALANCE from a split", case, rows)


# ---------------------------------------------------------------------------
# AC-G10 / AC-E1 (owner, 18 Oct: "the 632 comes from part of 417, part of 504"): a split dropped
# on a line of the Confirm whose AutoCount qty went up is MOVED there (with its links, AC-E1)
# whatever the origin line's net change. The owner's 752 went UP (504 -> 649 = 467 own + 182
# extra) yet its 37 sits on 608 (192 -> 632 = 192 + 236 + 167 + 37): purchasing must not be
# asked for the 37 on 752 as well as inside 608's 632.
# ---------------------------------------------------------------------------


def _live_by_line(s):
    return {no: _live(_worklist(s, s.line[no])) for no in OWNER_CASE}


def test_g10_a_split_dropped_on_a_line_that_went_up_moves_even_when_its_origin_went_up(api, emails):
    s = _seed(api)
    _save(s, _owner_plan())
    sent = _confirm_batch(s, emails)
    live = _live_by_line(s)
    rows = {no: _worklist(s, s.line[no]) for no in OWNER_CASE}

    assert not [q for q, _when in live[752] if q == _d("37")], (
        "the 37 moved to 608: no 37 row left on 752", rows[752])
    assert sum((q for q, _when in live[608]), Decimal(0)) == _d("632"), rows[608]
    assert sum((q for q, _when in live[752]), Decimal(0)) == _d("649"), (
        "752 keeps 467 own + 182 extra", rows[752])
    total = sum((q for no in live for q, _when in live[no]), Decimal(0))
    assert total == _d("1295"), (
        "no double ask: live OI qty = AutoCount 14 + 632 + 649", live)
    for no in OWNER_CASE:
        assert _cancel_balances(rows[no]) == [], (no, rows[no])

    # the email and the Excel still read as AC-G6 / AC-G7
    printed = _printed(sent)
    assert _has_block(printed, BLOCK_480), printed
    assert _has_block(printed, BLOCK_752), printed
    assert ROW_608 in printed, printed
    excel = _excel_rows(s)
    assert _has_block(excel, [(_d("417"), D_480, _d("14"), D_480_NEW, "ADVANCE")] + EXCEL_480[1:]), excel
    assert _has_block(excel, EXCEL_752), excel
    assert EXCEL_608 in excel, excel


def test_g10_the_moved_37_takes_its_po_link_from_752_to_608(api, emails):
    """AC-E1 for an origin that went up: 752's row is linked to a PO for its 504. The 37 moves
    to 608 with 37 of that link; 752 keeps 467 of it (504 in all, nothing dropped)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from tests.test_planning_change_apply_on_board import _link, _po_line, _supplier

    s = _seed(api)
    _po, po_line = _po_line(s.world, _supplier(s.world), qty=504, expected_date=date(2026, 12, 10))
    _link(s.world, _order_row(s.world, s.line[752]), po_line, qty=504, document="ZZT-S0752")
    s.db.commit()
    _save(s, _owner_plan())
    _confirm_batch(s, emails)

    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

    svc = ProjectOrderInquiryService(s.db)

    def linked(no):
        total = Decimal(0)
        for row in s.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.so_line_id == s.line[no].id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        ):
            total += sum(
                (Decimal(str(l.qty)) for l in svc._links_of(row.id) if l.po_line_id == po_line.id),
                Decimal(0),
            )
        return total

    got = {no: linked(no) for no in (608, 752)}
    assert got == {608: Decimal("37"), 752: Decimal("467")}, (
        "AC-E1: the 37 moves with its link, 752 keeps the rest", got)
