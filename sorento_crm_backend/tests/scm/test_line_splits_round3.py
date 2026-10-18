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


# ---------------------------------------------------------------------------
# Review of 89aad589bf (reviewer NOT READY), round 3
# ---------------------------------------------------------------------------


def _owner_total(s):
    """Live OI qty over 480 / 608 / 752 (not cancelled, not a CANCEL BALANCE)."""
    return sum((q for no in OWNER_CASE for q, _when in _live(_worklist(s, s.line[no]))), Decimal(0))


def _reconfirm(s):
    """A plain re-Confirm of the same Buy, no batch (the reviewer's probe)."""
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[no].id, buy_qty=str(after[0]))
        for no, (_before, after) in OWNER_CASE.items()
    ])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()


def test_review_a_plain_re_confirm_after_the_batch_confirm_changes_nothing(api, emails):
    """BLOCKING: the batch Confirm applied the owner's plan (live OI 1295 = AutoCount). A second
    Confirm with no change must not act on the plan again: live OI stays 1295 (it read 1735,
    +440) and no handover email is queued for the plan."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    assert _owner_total(s) == _d("1295"), "premise: the batch Confirm applied the plan"
    start = len(emails)
    _reconfirm(s)
    assert _owner_total(s) == _d("1295"), (
        "a re-Confirm with no change asks for nothing more",
        {no: _worklist(s, s.line[no]) for no in OWNER_CASE})
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert resent == [], ("no handover for a plan the batch Confirm already told", resent)


def _applied_480(s, remark_14=""):
    """480's splits as the owner's Confirm applied them (14 own, 236 + 167 on 608)."""
    return {"line_id": _on(s, 480), "splits": [
        _sp(14, D_480_NEW, on=_on(s, 480), remark=remark_14),
        _sp(236, D_608, on=_on(s, 608)),
        _sp(167, D_167, on=_on(s, 608)),
    ]}


def test_review_after_the_confirm_the_applied_plan_re_saves_and_a_14_plan_is_accepted(api, emails):
    """After the Confirm that applied it, 480's plan is applied (the FE's after-Confirm shape
    reads split_state "applied"). Re-saving that APPLIED plan (its splits still add up to the
    stored split base 417) is accepted (lead-signed change: it was refused against 14), and a
    new plan made against the current base 14 is accepted too."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    assert _line(_get(s), s, 480)["split_state"] == "applied", _line(_get(s), s, 480)
    r = _put(s, [_applied_480(s)])
    assert r.status_code == 200, ("the applied plan re-saves", r.status_code, r.text)
    r = _put(s, [{"line_id": _on(s, 480), "splits": [
        _sp(10, D_480_NEW, on=_on(s, 480)), _sp(4, D_608, on=None)]}])
    assert r.status_code == 200, ("a 14 plan is accepted", r.text)


def test_review_a_remark_only_save_after_the_confirm_is_accepted_and_re_confirm_changes_nothing(
    api, emails
):
    """Re-check BLOCKING: after the owner's Confirm, staff only type a remark on 480 and Save.
    The FE sends every line (`lineSplitModel.ts` `toPayload`: split lines with their splits,
    608 with []), so the applied plans are re-saved as they stand: 200 (it was 422 "Line 480:
    the splits add up to 417, not 14"), the remark is stored, and a re-Confirm after that Save
    still leaves live OI at 1295 with no email."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    r = _put(s, [
        _applied_480(s, remark_14=TYPED),
        {"line_id": _on(s, 608), "splits": []},
        {"line_id": _on(s, 752), "splits": [
            _sp(37, D_608, on=_on(s, 608)), _sp(467, D_752_NEW, on=_on(s, 752))]},
    ])
    assert r.status_code == 200, ("a remark-only Save after Confirm is accepted", r.status_code, r.text)
    assert _line(_get(s), s, 480)["splits"][0]["remark"] == TYPED
    start = len(emails)
    _reconfirm(s)
    assert _owner_total(s) == _d("1295"), (
        "the re-saved applied plan does not act again",
        {no: _worklist(s, s.line[no]) for no in OWNER_CASE})
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert resent == [], ("no email after a remark-only Save and re-Confirm", resent)


def test_review_re_confirm_of_the_new_line_plan_changes_nothing(api, emails):
    """Guard (`standing_splits`): after the Confirm that applied the New-line plan (480: 14 /
    236 / 167 on 480), a re-Confirm leaves 480's rows as they are and sends no email."""
    s = _seed(api)
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    before = sorted(_worklist(s, s.line[480]), key=str)
    assert _live(before) == sorted(
        [(_d("14"), D_480_NEW), (_d("236"), D_608), (_d("167"), D_167)]), "premise"
    start = len(emails)
    _reconfirm(s)
    assert sorted(_worklist(s, s.line[480]), key=str) == before, _worklist(s, s.line[480])
    assert emails[start:] == [], [
        (ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]


def test_review_kept_split_rows_keep_their_links(api, emails):
    """BLOCKING link conservation: 480's row is placed, linked to a PO for its 417. The
    New-line plan 14 / 236 / 167 keeps every split on 480, so each kept row stays linked for its
    own qty (417 in all): nothing orphaned, nothing asked again (it read 14 / 0 / 0)."""
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryLink, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from tests.test_planning_change_apply_on_board import _link, _po_line, _supplier

    s = _seed(api)
    _po, po_line = _po_line(s.world, _supplier(s.world), qty=417, expected_date=date(2026, 10, 10))
    _link(s.world, _order_row(s.world, s.line[480]), po_line, qty=417, document="ZZT-S0480")
    s.db.commit()
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)

    svc = ProjectOrderInquiryService(s.db)
    got = {}
    for row in s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == s.line[480].id, OrderInquiryRow.state != INQUIRY_CANCELLED
    ):
        linked = sum(
            (Decimal(str(l.qty)) for l in svc._links_of(row.id) if l.po_line_id == po_line.id),
            Decimal(0),
        )
        got[(_d(str(Decimal(str(row.qty)).normalize())), row.delivery_date)] = linked
    assert got == {
        (_d("14"), D_480_NEW): _d("14"),
        (_d("236"), D_608): _d("236"),
        (_d("167"), D_167): _d("167"),
    }, ("each kept row is linked for its own qty", got)
    everywhere = sum(
        (Decimal(str(l.qty)) for l in s.db.query(OrderInquiryLink)
         .filter(OrderInquiryLink.po_line_id == po_line.id).all()),
        Decimal(0),
    )
    assert everywhere == _d("417"), ("the PO's 417 is still linked in full", everywhere)


def _sheet(s, columns=None):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    kwargs = {"columns": columns} if columns else {}
    _name, data = OrderInquiryWorklistService(s.db).export_xlsx(query=s.core_so.so_number, **kwargs)
    rows = list(openpyxl.load_workbook(io.BytesIO(data)).worksheets[0].iter_rows(values_only=True))
    heads = list(rows[1])
    return heads, [r for r in rows[2:] if any(v not in (None, "") for v in r)]


def test_review_excel_total_qty_is_the_live_qty(api, emails):
    """Excel TOTAL QTY (`_write_sheet`) adds up what the rows ask for now, not the base QTY
    cells: SO417636 after the owner's plan, 1295 = AutoCount 14 + 632 + 649 (it read 1113 =
    417 + 192 + 504)."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    heads, rows = _sheet(s)
    at = heads.index("TOTAL QTY")
    totals = [r[at] for r in rows if r[at] not in (None, "")]
    assert totals == [1295.0], ("one run, TOTAL QTY = the live qty", totals)


def test_review_the_ten_column_worksheet_prints_every_split_rows_qty(api, emails):
    """The reorder-run OI worksheet (`export_tasks.generate_oi_worksheet`, the first 10 columns,
    no CHANGE QUANTITY): every row prints its own qty in QTY (no blank QTY row), and its QTY
    cells add up to the worklist export's TOTAL QTY (1295 for the owner plan). A split whose
    qty already sits inside another line (236 / 167 from 480 and 37 from 752, inside 608's
    632) is not printed again in this slice (re-check: the QTY cells summed 1735)."""
    from app.services.order_inquiry_worklist_service import EXPORT_HEADINGS

    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    full_heads, full_rows = _sheet(s)
    at_total = full_heads.index("TOTAL QTY")
    totals = [r[at_total] for r in full_rows if r[at_total] not in (None, "")]
    assert totals == [1295.0], ("premise: the worklist export's TOTAL QTY", totals)
    heads, rows = _sheet(s, EXPORT_HEADINGS[:10])
    assert len(heads) == 10, heads
    at = heads.index("QTY")
    qtys = [r[at] for r in rows]
    assert None not in qtys and "" not in qtys, ("no blank QTY row", qtys)
    for want in (14, 632, 467, 182):
        assert float(want) in qtys, (f"the {want} row prints its qty", qtys)
    assert sum(qtys) == totals[0], ("QTY cells add up to TOTAL QTY: nothing printed twice", qtys)
    for moved in (236, 167, 37):
        assert float(moved) not in qtys, (f"{moved} sits inside 608's 632, not printed again", qtys)


def _mixed(api, emails, *, with_splits, placed):
    """Owner seed, 480 confirmed partly from stock (USE pool 4 + Buy 10 with an amend reason,
    the mixed line `_kept_split_needs` leaves to the netting); `with_splits` saves the New-line
    plan first. Returns (worklist rows by line, sent email lines, Excel rows)."""
    from app.models.project_so import INQUIRY_PLACED

    s = _seed(api)
    if placed:
        _order_row(s.world, s.line[480]).state = INQUIRY_PLACED  # placed with no link
    s.db.commit()
    if with_splits:
        _save(s, _new_line_plan())
    start = len(emails)
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[480].id, reserve=[{"warehouse_id": s.world.pool_wh.id, "qty": "4"}],
                      buy_qty="10", amend_reason="Part from the pool."),
        _line_payload(s.line[608].id, buy_qty="632"),
        _line_payload(s.line[752].id, buy_qty="649"),
    ], batch_id=str(s.batch.id))
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    rows = {no: sorted(_worklist(s, s.line[no]), key=str) for no in OWNER_CASE}
    pool = s.world.pool_wh.warehouse_code
    sent = [(ln["qty"], str(ln["remark"]).replace(pool, "POOL"))
            for h in emails[start:] for ln in h.get("lines") or []]
    return rows, sent, _excel_rows(s)


@pytest.mark.parametrize("placed", [False, True], ids=["raised", "placed_unlinked"])
def test_review_a_mixed_line_nets_as_before_and_prints_what_the_worklist_holds(api, emails, placed):
    """A line partly from stock is not a whole-Buy split line (`_kept_split_needs`): it nets as
    without splits, and the email / Excel print what the worklist then holds, never the plan
    (worklist, email and Excel agree). The same Confirm is run on a twin order with no splits."""
    from tests.test_so_supply_confirmation import _stock

    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)  # one pool stock row, both orders
    world.db.commit()
    plain_rows, plain_sent, plain_xl = _mixed(api, emails, with_splits=False, placed=placed)
    split_rows, split_sent, split_xl = _mixed(api, emails, with_splits=True, placed=placed)
    assert split_rows == plain_rows, ("the worklist nets as without splits", split_rows, plain_rows)
    assert split_sent == plain_sent, (
        "the email prints what the worklist holds, not the plan", split_sent, plain_sent)
    assert split_xl == plain_xl, ("the Excel prints what the worklist holds", split_xl, plain_xl)


def test_review_confirmed_at_is_the_malaysia_date_of_the_confirm(api, emails):
    """AC-G1 status line: a Confirm at 2026-10-18 23:30 UTC is 19/10/2026 in Malaysia."""
    from app.models.project_so import SOSupplyDecision

    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    s.db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == str(s.order.id)
    ).update({SOSupplyDecision.confirmed_at: datetime(2026, 10, 18, 23, 30)},
             synchronize_session=False)
    s.db.commit()
    assert _get(s)["confirmed_at"] == "2026-10-19", _get(s)["confirmed_at"]


def _closed_line_case(api):
    """Line 2 (its own item) confirmed Buy 10, then AutoCount closes it (`closed`, qty 0)."""
    from app.services.scm.outstanding_diff import CLOSED
    from tests.test_planning_changes import _product

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    item = _product(db)
    when = date(2026, 11, 9)
    core = _core_line(db, core_so, item, world.own_wh, qty_ordered="10", required_date=when)
    line = _project_line(db, order, line_no=2, product=item, core_line=core)
    db.commit()
    r = _confirm(client, order.id, [_line_payload(line.id, buy_qty="10")])
    assert r.status_code == 200, r.text
    row = _order_row(world, line)
    core.line_status = "closed"
    line.qty = Decimal("0")
    db.commit()
    batch = _build(world, [_change(CLOSED, core, so_number=core_so.so_number, old_date=when,
                                   new_date=None, old_qty="10", new_qty="0")],
                   core_so, [str(core.id)])
    assert batch is not None, "premise: the close is a pending change"
    return client, order, line, row


def test_review_unsplit_line_prefill_is_the_email_remark_cancel_all(api):
    """One function (AC-G5) for an UNSPLIT line AutoCount cancelled: the sheet's pre-fill is the
    email's REMARK for it, "CANCEL ALL" (`handover_remark`, kind cancelled), not "CANCEL 10"."""
    from app.services.project_order_inquiry_service import handover_remark

    client, order, line, row = _closed_line_case(api)
    out = client.get(_url(order.id)).json()
    mine = next(x for x in out["lines"] if x["line_id"] == str(line.id))
    email = handover_remark("cancelled", row, {"qty": row.qty})
    assert email == "CANCEL ALL", "premise: the email spells a cancelled line CANCEL ALL"
    assert mine["remark_generated"] == email, (mine["remark_generated"], email)


@pytest.mark.parametrize("case", ["qty_and_date", "new_item_code"])
def test_review_unsplit_line_prefill_is_the_email_remark(api, emails, case):
    """One function (AC-G5) for an UNSPLIT line: the sheet's pre-fill before the Confirm is the
    REMARK the Confirm's email prints for that line. qty_and_date (752, DELAY, ORDER 145) is the
    guard; new_item_code (AutoCount swapped the product) prints NEW ITEM CODE."""
    if case == "qty_and_date":
        s = _seed(api)
        before = _line(_get(s), s, 752)["remark_generated"]
        sent = _confirm_batch(s, emails)
        printed = [r[4] for r in _printed(sent) if r[0] == "504"]
    else:
        from tests.test_oi_product_follow_apply import _apply, _swap_fixture

        fx = _swap_fixture(api, acknowledged=True)
        out = fx["client"].get(_url(fx["order"].id)).json()
        before = next(x for x in out["lines"] if x["line_id"] == str(fx["line"].id))[
            "remark_generated"]
        start = len(emails)
        r = _apply(fx)
        assert r.status_code == 200, r.text
        fx["world"].db.commit()
        printed = [str(ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []
                   if ln.get("item_code") == fx["new"].product_code]
    assert len(printed) == 1, ("the Confirm prints one row for the line", printed)
    assert before == printed[0], ("sheet pre-fill == email REMARK", before, printed[0])


# ---------------------------------------------------------------------------
# Crew ruling (a) on a declined move onto a target that grew: the origin keeps its rows AND
# links; the target's need excludes the declined incoming qty, so nothing is bought twice,
# nothing is cancelled, and what purchasing is asked for equals AutoCount.
# ---------------------------------------------------------------------------


def _asked(s, line):
    """Live rows that still ask purchasing for goods: not cancelled, not a CANCEL BALANCE, and
    not a row whose every link is on a document received in full."""
    from app.models.procurement import PurchaseOrderLine
    from app.models.project_so import (
        INQUIRY_CANCELLED,
        IV_CANCEL_BALANCE,
        OrderInquiryRow,
    )
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    total = Decimal(0)
    for row in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id):
        if row.state == INQUIRY_CANCELLED or row.verb == IV_CANCEL_BALANCE:
            continue
        links = svc._links_of(row.id)
        received = bool(links) and all(
            (po := s.db.get(PurchaseOrderLine, link.po_line_id)) is not None
            and Decimal(str(po.qty_received or 0)) >= Decimal(str(po.qty_ordered or 0))
            for link in links
        )
        if not received:
            total += Decimal(str(row.qty))
    return total


@pytest.mark.parametrize("case", ["target_placed_no_link", "target_received_in_full"])
def test_g10_a_declined_move_onto_a_grown_target_buys_nothing_twice(api, emails, case):
    """Line 2 51 -> 2 keeps 2 own + 49 at 01/11/2026 (the move onto line 18, 82 -> 131, is
    declined). Purchasing is asked for AutoCount's 2 + 131 = 133 (it was 182): line 2 keeps 2 +
    49 with its PO link (51), line 18 raises no ORDER for the declined 49 (asked 131 - 49 = 82),
    and nothing is cancelled."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

    s, origin, _splits = _declined(api, emails, case)
    target = s.no[18][1]
    asked = {2: _asked(s, origin), 18: _asked(s, target)}
    assert asked[2] + asked[18] == _d("133"), ("asked == AutoCount 2 + 131", case, asked,
                                               _worklist(s, origin), _worklist(s, target))
    assert asked[18] == _d("82"), ("line 18 asks 131 less the declined 49", case,
                                   _worklist(s, target))
    svc = ProjectOrderInquiryService(s.db)
    kept_link = sum(
        (Decimal(str(l.qty))
         for row in s.db.query(OrderInquiryRow).filter(
             OrderInquiryRow.so_line_id == origin.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
         for l in svc._links_of(row.id) if l.po_line_id == s.po_line.id),
        Decimal(0),
    )
    assert kept_link == _d("51"), ("the origin keeps its rows AND links (2 + 49)", case, kept_link)
    for line in (origin, target):
        assert _cancel_balances(_worklist(s, line)) == [], (case, _worklist(s, line))


def _origin_link(s, origin):
    """What line 2's live rows hold of its own PO line (`s.po_line`, 51 at the start)."""
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    return sum(
        (Decimal(str(l.qty))
         for row in s.db.query(OrderInquiryRow).filter(
             OrderInquiryRow.so_line_id == origin.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
         for l in svc._links_of(row.id) if l.po_line_id == s.po_line.id),
        Decimal(0),
    )


@pytest.mark.parametrize("case", ["target_placed_no_link", "target_received_in_full"])
def test_g13_a_re_confirm_after_a_declined_move_plan_changes_nothing(api, emails, case):
    """AC-G12 + AC-G13: after the Confirm that applied the plan (asked 133 = AutoCount, line 2
    holding 51 of its link), a second Confirm with no change changes nothing: the same worklist
    rows, asked still 133, line 18 does not ask for the declined 49 again, line 2's link
    unchanged, no CANCEL, no plan email again."""
    s, origin, _splits = _declined(api, emails, case)
    target = s.no[18][1]
    assert _asked(s, origin) + _asked(s, target) == _d("133"), "premise: the plan applied"
    assert _origin_link(s, origin) == _d("51"), "premise: line 2 keeps its link"
    before = {no: sorted(_worklist(s, s.no[no][1]), key=str) for no in (2, 18)}
    start = len(emails)

    r = _confirm(s.client, s.order.id, [
        _line_payload(v[1].id, buy_qty=str(now))
        for v, (_no, _qty, _when, now) in zip(s.no.values(), s.specs)
    ])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()

    after = {no: sorted(_worklist(s, s.no[no][1]), key=str) for no in (2, 18)}
    assert after == before, ("a re-Confirm with no change changes no row", case, before, after)
    assert _asked(s, origin) + _asked(s, target) == _d("133"), (case, after)
    assert _asked(s, target) == _d("82"), ("line 18 does not ask for the declined 49 again",
                                           case, after[18])
    assert _origin_link(s, origin) == _d("51"), (case, "line 2's link is unchanged")
    for line in (origin, target):
        assert _cancel_balances(_worklist(s, line)) == [], (case, _worklist(s, line))
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert resent == [], ("no plan email again", case, resent)


def test_g13_a_re_confirm_after_a_declined_move_off_a_line_cut_to_zero_changes_nothing(api, emails):
    """Re-check: line 2 51 -> 0 (its document received in full) with its 51 split onto line 18
    (82 -> 133); the move is declined, so line 2 keeps a 51 row at 01/11/2026 and line 18 asks
    82 (AC-G12). A second Confirm with no change changes nothing: line 2 keeps its 51 row,
    line 18 stays at 82, no CANCEL and no "ORDER 51" email (it cancelled the 51, raised line 18
    to 133 and sent "133 ORDER 51")."""
    from tests.scm.test_line_splits_confirm import D_18

    s, origin, _splits = _declined(api, emails, "source_received_cut_to_zero")
    target = s.no[18][1]
    assert (_d("51"), D_18) in _live(_worklist(s, origin)), ("premise", _worklist(s, origin))
    assert _asked(s, target) == _d("82"), ("premise", _worklist(s, target))
    before = {no: sorted(_worklist(s, s.no[no][1]), key=str) for no in (2, 18)}
    start = len(emails)

    r = _confirm(s.client, s.order.id, [
        _line_payload(v[1].id, buy_qty=str(now))
        for v, (_no, _qty, _when, now) in zip(s.no.values(), s.specs)
    ])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()

    after = {no: sorted(_worklist(s, s.no[no][1]), key=str) for no in (2, 18)}
    assert after == before, ("a re-Confirm with no change changes no row", before, after)
    assert (_d("51"), D_18) in _live(after[2]), ("line 2 keeps its 51 row", after[2])
    assert _asked(s, target) == _d("82"), ("line 18 stays at 82", after[18])
    for line in (origin, target):
        assert _cancel_balances(_worklist(s, line)) == [], _worklist(s, line)
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert not [x for x in resent if "ORDER 51" in str(x[1])], resent
    assert resent == [], ("no email for a re-Confirm with no change", resent)


# ---------------------------------------------------------------------------
# Re-check on 4d59aee4a7 (BLOCKING double ask since 160f1fb4b3): a split left on New line (no
# sits-on line) is part of its own line's plan (AC-G2) and is NOT counted again as the line's
# AutoCount extra (AC-G3).
# ---------------------------------------------------------------------------


def _one_line(api, qty, when):
    """One published order with line 480 at `qty` @ `when`, confirmed as Buy, nothing pending."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=str(qty),
                      required_date=when)
    core.line_no = 480
    line = _project_line(db, order, line_no=480, product=world.product, core_line=core)
    line.stock_location = world.own_wh.warehouse_code
    db.commit()
    r = _confirm(client, order.id, [_line_payload(line.id, buy_qty=str(qty))])
    assert r.status_code == 200, r.text
    db.commit()
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.line, s.qty = {480: line}, qty
    return s


@pytest.mark.parametrize("qty,own,new", [(14, 10, 4), (100, 60, 40)], ids=["480_at_14", "100_no_cut"])
def test_g3_a_new_line_split_is_not_counted_again_as_autocount_extra(api, emails, qty, own, new):
    """(a) 480 at 14, nothing pending after a Confirm, plan 10 own + 4 on New line; (b) a line of
    100 with no AutoCount cut, plan 60 own + 40 on New line. AutoCount qty = own + New line,
    so there is no extra: the API's extra is null, nothing says "ORDER <new>", the Confirm
    asks for the line's qty (14 / 100, not 18 / 140), the email prints the two split rows only
    (REMAIN / DELAY) and the Excel the same two rows (it printed an extra "ORDER 4" / "ORDER 40"
    row and asked for it)."""
    d, d_new = D_480_NEW, D_608
    s = _one_line(api, qty, d)
    _save(s, {480: [(own, d, 480, ""), (new, d_new, "new", "")]})
    line = _line(_get(s), s, 480)
    assert line["extra_qty"] is None and line["extra_remark"] is None, (
        "AC-G3: a New-line split is not AutoCount extra", line["extra_qty"], line["extra_remark"])
    assert [x.get("remark_generated") for x in line["splits"]] == ["REMAIN", "DELAY"], line["splits"]
    rows = [(_d(str(qty)), d, _d(str(own)), d, "REMAIN"), (None, None, _d(str(new)), d_new, "DELAY")]
    assert _excel_rows(s) == rows, ("the Excel prints the two split rows only", _excel_rows(s))

    start = len(emails)
    r = _confirm(s.client, s.order.id, [_line_payload(s.line[480].id, buy_qty=str(qty))])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    live = _live(_worklist(s, s.line[480]))
    assert live == sorted([(_d(str(own)), d), (_d(str(new)), d_new)]), (
        f"the Confirm asks for {qty}, not {qty + new}", _worklist(s, s.line[480]))
    sent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert sent == [(str(own), "REMAIN"), (str(new), "DELAY")], ("email: the two split rows only", sent)
    assert not [r for r in _excel_rows(s) if str(r[4]).startswith("ORDER")], _excel_rows(s)


def test_g3_the_owner_case_numbers_stand(api, emails):
    """Guard: the owner case keeps its numbers (752's real AutoCount extra 182, 608 REMAIN,
    live OI 1295 after the Confirm)."""
    s = _seed(api)
    _save(s, _owner_plan())
    out = _get(s)
    assert _q(_line(out, s, 752)["extra_qty"]) == _d("182"), _line(out, s, 752)["extra_qty"]
    assert _line(out, s, 480)["extra_qty"] is None
    assert _line(out, s, 608)["extra_qty"] is None
    _confirm_batch(s, emails)
    assert _line(_get(s), s, 608)["remark_generated"] == "REMAIN"
    assert _owner_total(s) == _d("1295"), {no: _worklist(s, s.line[no]) for no in OWNER_CASE}


# ---------------------------------------------------------------------------
# Crew rulings P1 / P2 (18 Oct): an applied New-line plan that staff EDIT acts again on the
# next Confirm; the next AutoCount change on a line with kept New-line rows leaves those rows
# standing. 480's row is linked to a PO for its 417, so "links kept" is checked row by row.
# ---------------------------------------------------------------------------

D_167_EDIT = date(2029, 12, 20)
D_36 = date(2030, 1, 20)


def _rows_with_links(s, po_line):
    """480's live rows as (qty, date) -> qty linked on `po_line`."""
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    out = {}
    for row in s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == s.line[480].id, OrderInquiryRow.state != INQUIRY_CANCELLED
    ):
        key = (_d(str(Decimal(str(row.qty)).normalize())), row.delivery_date)
        out[key] = out.get(key, Decimal(0)) + sum(
            (Decimal(str(l.qty)) for l in svc._links_of(row.id) if l.po_line_id == po_line.id),
            Decimal(0),
        )
    return out


def _new_line_plan_applied(api, emails):
    """Owner seed, 480 linked to a PO for its 417, the New-line plan confirmed (480: 14 own,
    236 and 167 on New line), each kept row linked for its own qty."""
    from tests.test_planning_change_apply_on_board import _link, _po_line, _supplier

    s = _seed(api)
    _po, po_line = _po_line(s.world, _supplier(s.world), qty=417, expected_date=date(2026, 10, 10))
    _link(s.world, _order_row(s.world, s.line[480]), po_line, qty=417, document="ZZT-S0480")
    s.db.commit()
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    assert _rows_with_links(s, po_line) == {
        (_d("14"), D_480_NEW): _d("14"), (_d("236"), D_608): _d("236"),
        (_d("167"), D_167): _d("167"),
    }, ("premise: the New-line plan applied with its links", _rows_with_links(s, po_line))
    return s, po_line


def _edit_480(s, parts):
    """PUT 480's plan, parts [(qty, date, 'own' | 'new', remark)]: the Save must be accepted."""
    body = [_sp(q, w, on=_on(s, 480) if on == "own" else None, remark=remark)
            for q, w, on, remark in parts]
    r = _put(s, [{"line_id": _on(s, 480), "splits": body}])
    assert r.status_code == 200, ("the edit of the applied plan saves", r.status_code, r.text)


def _sent_since(emails, start):
    return [ln for h in emails[start:] for ln in h.get("lines") or []]


def test_p1_editing_a_split_date_of_an_applied_plan_acts_on_the_next_confirm(api, emails):
    """P1 (a): the 167's date is edited to 20/12/2029 (same total) and saved. The line is no
    longer a standing plan for Confirm: the next Confirm moves purchasing's 167 row to
    20/12/2029 with its link, emails that change (DELAY, NEW DATE 20/12/2029), and the worklist,
    email and Excel all read 20/12/2029."""
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    start = len(emails)
    _reconfirm(s)

    got = _rows_with_links(s, po_line)
    assert got == {
        (_d("14"), D_480_NEW): _d("14"), (_d("236"), D_608): _d("236"),
        (_d("167"), D_167_EDIT): _d("167"),
    }, ("the 167 row moves to 20/12/2029 with its link", got)
    sent = _sent_since(emails, start)
    moved = [ln for ln in sent if ln["qty"] == "167"]
    assert len(moved) == 1 and moved[0]["delivery_date"] == "20/12/2029", (
        "the Confirm emails the 167's new date", [(l["qty"], l["delivery_date"], l["remark"]) for l in sent])
    assert str(moved[0]["remark"]).startswith("DELAY"), moved[0]["remark"]
    xl = _excel_rows(s)
    assert [r for r in xl if r[2] == _d("167") and r[3] == D_167_EDIT], ("Excel 167 @ 20/12/2029", xl)
    assert not [r for r in xl if r[3] == D_167], ("nothing reads 20/11/2029 any more", xl)


def test_p1_editing_a_split_qty_of_an_applied_plan_acts_on_the_next_confirm(api, emails):
    """P1 (a): 236 -> 200 with the 36 to a new split on 20/01/2030 (total unchanged). The next
    Confirm writes 200 and 36 at their dates, each linked for its own qty (417 in all), and
    the worklist, email and Excel all carry the new rows."""
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (200, D_608, "new", ""), (36, D_36, "new", ""),
                  (167, D_167, "new", "")])
    start = len(emails)
    _reconfirm(s)

    got = _rows_with_links(s, po_line)
    assert got == {
        (_d("14"), D_480_NEW): _d("14"), (_d("200"), D_608): _d("200"),
        (_d("36"), D_36): _d("36"), (_d("167"), D_167): _d("167"),
    }, ("200 and 36 replace the 236, each with its own link", got)
    sent = [(ln["qty"], ln["delivery_date"]) for ln in _sent_since(emails, start)]
    assert ("200", "20/11/2026") in sent and ("36", "20/01/2030") in sent, (
        "the Confirm emails the edited rows", sent)
    xl = _excel_rows(s)
    for qty, when in ((_d("200"), D_608), (_d("36"), D_36)):
        assert [r for r in xl if r[2] == qty and r[3] == when], (qty, when, xl)
    assert not [r for r in xl if r[2] == _d("236")], ("the 236 is gone", xl)


def test_p1_a_remark_only_edit_of_an_applied_plan_changes_nothing_on_confirm(api, emails):
    """P1 guard: only a remark typed on the 236 and saved; the next Confirm changes no row and
    sends no email."""
    s, po_line = _new_line_plan_applied(api, emails)
    before = sorted(_worklist(s, s.line[480]), key=str)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", "SITE HOLD"),
                  (167, D_167, "new", "")])
    start = len(emails)
    _reconfirm(s)
    assert sorted(_worklist(s, s.line[480]), key=str) == before, _worklist(s, s.line[480])
    assert _rows_with_links(s, po_line)[(_d("236"), D_608)] == _d("236")
    assert _sent_since(emails, start) == [], [
        (l["qty"], l["remark"]) for l in _sent_since(emails, start)]


def test_p2_the_next_autocount_change_keeps_the_new_line_rows_standing(api, emails):
    """P2 (a): after the New-line plan applied, AutoCount moves 480 from 14 to 20 (same date).
    After that Confirm 480's own row is 20, the 236 and 167 rows stand as they were (qty, date,
    link), nothing says CANCEL (worklist, email, Excel), and the email tells only 480's 14 ->
    20."""
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    s, po_line = _new_line_plan_applied(api, emails)
    svc = ProjectOrderInquiryService(s.db)

    def kept():
        out = []
        for row in s.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.so_line_id == s.line[480].id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.delivery_date.in_([D_608, D_167]),
        ):
            links = sorted((str(l.document), str(Decimal(str(l.qty)).normalize()))
                           for l in svc._links_of(row.id))
            out.append((str(row.id), row.verb, Decimal(str(row.qty)).normalize(),
                        row.delivery_date, links))
        return sorted(out)

    standing = kept()
    assert len(standing) == 2, ("premise: the 236 and 167 rows", standing)

    core = s.core[480]
    core.qty_ordered, s.line[480].qty = Decimal("20"), Decimal("20")
    s.db.commit()
    batch = _build(s.world, [_change(QTY_CHANGED, core, so_number=s.core_so.so_number,
                                     old_date=D_480_NEW, new_date=D_480_NEW, old_qty="14",
                                     new_qty="20")], s.core_so, [str(core.id)])
    assert batch is not None, "premise: the AutoCount change is pending"
    start = len(emails)
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[480].id, buy_qty="20"),
        _line_payload(s.line[608].id, buy_qty="632"),
        _line_payload(s.line[752].id, buy_qty="649"),
    ], batch_id=str(batch.id))
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()

    assert _live(_worklist(s, s.line[480])) == sorted(
        [(_d("20"), D_480_NEW), (_d("236"), D_608), (_d("167"), D_167)]), (
        "480's own row follows AutoCount, the New-line rows stand", _worklist(s, s.line[480]))
    assert kept() == standing, ("the 236 and 167 rows are untouched", standing, kept())
    for no in OWNER_CASE:
        assert _cancel_balances(_worklist(s, s.line[no])) == [], (no, _worklist(s, s.line[no]))
    sent = _sent_since(emails, start)
    assert not [l for l in sent if "CANCEL" in str(l.get("remark"))], sent
    assert not [r for r in _excel_rows(s) if "CANCEL" in str(r[4])], _excel_rows(s)
    told = [(l["qty"], (l.get("was") or {}).get("qty")) for l in sent]
    assert told == [("20", "14")], ("the email tells only 480's 14 -> 20", told,
                                   [l["remark"] for l in sent])


# ---------------------------------------------------------------------------
# Re-check on b3705f3fb3 (crew: CANCEL only where the user explicitly reduces qty; a re-plan
# that drops kept rows IS that). After the New-line plan applied (480: 14 / 236 / 167), 480 is
# re-planned as 10 own + 4 on New line (against the current 14): the 403 it drops is a CANCEL
# BALANCE purchasing's worklist holds and the email prints, never a silent cancel.
# ---------------------------------------------------------------------------


def _replan_480(s, emails):
    """Re-plan 480 as 10 own @ 20/09/2026 + 4 on New line @ 20/11/2026 and re-Confirm; returns
    the email lines that Confirm sent."""
    _edit_480(s, [(10, D_480_NEW, "own", ""), (4, D_608, "new", "")])
    start = len(emails)
    _reconfirm(s)
    return _sent_since(emails, start)


def _cancelled_403_in(sent):
    return [
        (ln["qty"], ln["remark"]) for ln in sent
        if "CANCEL" in str(ln.get("remark")) and (ln.get("qty") == "403" or "403" in str(ln.get("remark")))
    ]


def _assert_dropped_403_is_told(s, sent):
    from app.models.project_so import INQUIRY_CANCELLED

    rows = _worklist(s, s.line[480])
    assert _live(rows) == sorted([(_d("10"), D_480_NEW), (_d("4"), D_608)]), (
        "480 asks for the new plan, 10 + 4", rows)
    held = sum((q for state, q in _cancel_balances(rows) if state != INQUIRY_CANCELLED), Decimal(0))
    assert held == _d("403"), ("the dropped 403 is a CANCEL BALANCE on the worklist", rows)
    assert _cancelled_403_in(sent), ("the email prints the CANCEL 403", [
        (ln["qty"], ln["remark"]) for ln in sent])


def test_review_a_linked_re_plan_that_drops_kept_rows_cancels_them_and_gives_the_links_back(api, emails):
    """Linked: each kept row was linked for its own qty (417 on one PO). After the re-plan the
    10 and 4 rows are linked for their own qty only, the 403 of links is given back (it sat on
    the 10 row: 413), and worklist / email / Excel agree on the CANCEL 403."""
    from app.models.project_so import OrderInquiryLink

    s, po_line = _new_line_plan_applied(api, emails)
    sent = _replan_480(s, emails)
    _assert_dropped_403_is_told(s, sent)
    got = _rows_with_links(s, po_line)
    assert got.get((_d("10"), D_480_NEW)) == _d("10") and got.get((_d("4"), D_608)) == _d("4"), (
        "each plan row is linked for its own qty only", got)
    still = sum((Decimal(str(l.qty)) for l in s.db.query(OrderInquiryLink)
                 .filter(OrderInquiryLink.po_line_id == po_line.id).all()), Decimal(0))
    assert still == _d("14"), ("the dropped 403 of links is released", still)
    xl = _excel_rows(s)
    assert [r for r in xl if "CANCEL" in str(r[4])
            and (_d("403") in (r[0], r[2]) or "403" in str(r[4]))], ("the Excel prints the CANCEL 403", xl)


def test_review_an_unlinked_re_plan_that_drops_kept_rows_cancels_them_out_loud(api, emails):
    """Unlinked: the 236 and 167 rows are not cancelled silently; a CANCEL BALANCE for 403 is
    written and emailed."""
    s = _seed(api)
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    sent = _replan_480(s, emails)
    _assert_dropped_403_is_told(s, sent)


@pytest.mark.parametrize("received", [417, 100], ids=["received_in_full", "partly_received_guard"])
def test_review_kept_rows_on_a_received_document_stand_through_re_confirms(api, emails, received):
    """480's PO (417, linked across 14 / 236 / 167 by the applied New-line plan) is received in
    full: two more Confirms with no change leave the rows as they are and send no email either
    time (they re-emailed 14 / 236 / 167 each time). Partly received (100 of 417) is the guard:
    it already stands."""
    s, po_line = _new_line_plan_applied(api, emails)
    po_line.qty_received = Decimal(received)
    s.db.commit()
    before = sorted(_worklist(s, s.line[480]), key=str)
    for attempt in (1, 2):
        start = len(emails)
        _reconfirm(s)
        assert sorted(_worklist(s, s.line[480]), key=str) == before, (attempt, _worklist(s, s.line[480]))
        sent = [(ln["qty"], ln["remark"]) for ln in _sent_since(emails, start)]
        assert sent == [], (f"re-Confirm {attempt} sends no email", sent)
