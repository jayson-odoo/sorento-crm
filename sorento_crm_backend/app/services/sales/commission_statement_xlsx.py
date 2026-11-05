"""The commission statement workbook (lane TARGET-COMMISSION-VIEW, owner Q1 4 Nov: xlsx).

Writes what `target_service.commission_statements` computed, nothing more: a Summary sheet
with one row per target, then one sheet per target (named by its number) with the header, the
period summary, and per period the tier table used and the documents behind "Achieved".
Dates are real dates shown dd/mm/yyyy, money is shown with 2 decimals (owner's 4 Nov rule),
so a stakeholder can sort and sum the cells.
"""
from __future__ import annotations

from app.utils.date_format import fmt_date_range, fmt_datetime
import io
from datetime import date, datetime
from typing import Iterable, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

DATE_FMT = "dd/mm/yyyy"
MONEY_FMT = "#,##0.00"
PCT_FMT = '0.0"%"'
BOLD = Font(bold=True)

METHODS = {
    "retroactive": "Highest tier pays on the whole amount",
    "marginal": "Each tier pays on its own slice",
    "none": "No commission",
}
NOT_TRACKED = "Payment is not tracked in the CRM."
#: A string starting with one of these is a formula to Excel: a target name typed by staff or a
#: customer name synced from AutoCount must stay text in a file sent to stakeholders.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")



def _account(account: Optional[dict]) -> str:
    if not account:
        return ""
    return f"{account['code']} - {account['name']} ({account['label']})"


def _rates(entries: Iterable[dict], metric: str) -> str:
    unit = "%" if metric == "amount" else " RM/unit"
    parts = []
    for entry in entries:
        if entry.get("rate") is None:
            continue
        text = f"{entry['rate']:.2f}{unit}"
        parts.append(f"{entry['label']} {text}" if entry.get("label") else text)
    return ", ".join(parts)


def _period_label(p: dict) -> str:
    return fmt_date_range(p["period_start"], p["period_end"])


def _paid(p: dict) -> Optional[float]:
    if p["commission_earned"] is None:
        return None
    return round((p["commission_earned"] or 0) + (p["bonus_earned"] or 0), 2)


class _Sheet:
    """Row-at-a-time writer that formats each cell by what it holds."""

    def __init__(self, ws):
        self.ws = ws
        self.row = 1

    def write(self, values: List, *, bold: bool = False, money: Iterable[int] = (), pct: Iterable[int] = ()):
        money, pct = set(money), set(pct)
        for col, value in enumerate(values, start=1):
            if value is None or value == "":
                continue
            cell = self.ws.cell(row=self.row, column=col, value=value)
            if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
                # Kept as text, as project_quotation_excel_service does: the name reads as typed.
                cell.data_type = "s"
                cell.quotePrefix = True
            if isinstance(value, (date, datetime)):
                cell.number_format = DATE_FMT
            elif col in money:
                cell.number_format = MONEY_FMT
            elif col in pct:
                cell.number_format = PCT_FMT
            if bold:
                cell.font = BOLD
        self.row += 1

    def gap(self):
        self.row += 1


def _target_sheet(ws, t: dict, generated: datetime, on: date) -> None:
    metric = t["metric"]
    unit = "RM" if metric == "amount" else "units"
    sheet = _Sheet(ws)
    sheet.write([f"Commission statement: {t['target_no']} {t['name']}"], bold=True)
    sheet.write(["For", t["subject_label"]])
    sheet.write(["Counts", t["counts_label"]])
    sheet.write(["Method", METHODS.get(t["commission_method"], t["commission_method"])])
    sheet.write(["Pays to", _account(t.get("payout_account")) or "-"])
    sheet.write(["Payment", NOT_TRACKED])
    sheet.write(["Earned to date (RM)", t.get("commission_to_date")], money=[2])
    sheet.write(["Current period so far (RM), not final", t.get("commission_current")], money=[2])
    sheet.write(["Generated", fmt_datetime(generated, naive_is_utc=False)])
    sheet.gap()

    sheet.write(["Summary"], bold=True)
    sheet.write(
        ["Period", f"Target ({unit})", f"Achieved ({unit})", "%", "Tier reached", "Rate",
         "Commission (RM)", "Bonus (RM)", "Pays to", "Status"],
        bold=True,
    )
    pays_to = (t.get("payout_account") or {}).get("code", "")
    for p in t["periods"]:
        status = "Current, not final" if p["is_current"] else ("Not started" if p["period_start"] > on else "Ended")
        if p.get("replaced"):
            status = "Replaced by another target"
        paid = _paid(p)
        sheet.write(
            [
                _period_label(p), p["target_value"], p["achieved_value"], p["achieved_pct"],
                f"Tier {p['tier_reached']}" if p["tier_reached"] else "None",
                _rates(p["tier_rates"], metric), p["commission_earned"], p["bonus_earned"],
                pays_to if paid else "", status,
            ],
            money=[2, 3, 7, 8], pct=[4],
        )
    sheet.write(
        ["Total", None, None, None, None, None,
         round(sum(p["commission_earned"] or 0 for p in t["periods"]), 2),
         round(sum(p["bonus_earned"] or 0 for p in t["periods"]), 2)],
        bold=True, money=[7, 8],
    )

    for p in t["periods"]:
        sheet.gap()
        sheet.write([f"Period {_period_label(p)}"], bold=True)
        if p["tier_table"]:
            sheet.write(["Tier table used"], bold=True)
            sheet.write(["Tier", "From (% of target)", f"Threshold ({unit})", "Rate", "Additional", "Reached"], bold=True)
            for rung in p["tier_table"]:
                sheet.write(
                    [f"Tier {rung['tier']}", rung["from_pct"], rung["threshold_rm"],
                     _rates(rung["rates"], metric), _rates(rung["additional_rates"], metric),
                     "Yes" if rung["reached"] else "No"],
                    money=[3], pct=[2],
                )
        sheet.write([f"Documents counted in Achieved ({t['counts_label']})"], bold=True)
        sheet.write(["Document no.", "Date", "Account", f"Amount counted ({unit})"], bold=True)
        for d in p["documents"]:
            sheet.write([d["doc_no"], d["doc_date"], d["account_code"], d["amount"]], money=[4])
        if not p["documents"]:
            sheet.write(["No documents in this period"])
        sheet.write(["Total (= Achieved)", None, None, p["achieved_value"]], bold=True, money=[4])

    for col, width in enumerate((34, 16, 18, 14, 16, 18, 16, 12, 14, 26), start=1):
        ws.column_dimensions[get_column_letter(col)].width = width


def build(statements: List[dict], *, on: date, generated: Optional[datetime] = None) -> bytes:
    """`on`: the date the figures were computed for (what "current" means)."""
    generated = generated or datetime.now()
    used: set = set()
    wb = Workbook()
    summary = _Sheet(wb.active)
    wb.active.title = "Summary"
    summary.write(["Commission statement", f"Generated {fmt_datetime(generated, naive_is_utc=False)}"], bold=True)
    summary.write(["Earned to date counts periods that have ended; the current period can still change. " + NOT_TRACKED])
    summary.gap()
    summary.write(
        ["Target no.", "Name", "For", "Counts", "Pays to", "Earned to date (RM)", "Current period so far (RM)"],
        bold=True,
    )
    for t in statements:
        summary.write(
            [t["target_no"], t["name"], t["subject_label"], t["counts_label"],
             _account(t.get("payout_account")), t.get("commission_to_date"), t.get("commission_current")],
            money=[6, 7],
        )
        # Target numbers are unique per company, so a statement over two companies can repeat one.
        title, n = t["target_no"][:31], 1
        while title in used:
            n += 1
            title = f"{t['target_no'][:27]} ({n})"
        used.add(title)
        _target_sheet(wb.create_sheet(title), t, generated, on)
    for col, width in enumerate((14, 40, 34, 22, 44, 20, 24), start=1):
        wb["Summary"].column_dimensions[get_column_letter(col)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
