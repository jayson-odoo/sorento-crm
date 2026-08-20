# PLAN - a proforma invoice becomes an SPO: convert, match, net, hand to AutoCount

**Status:** Journey + three shaping decisions approved by the captain, 20 Aug 2026 (live
session, while testing the new proforma screen). NOT yet implemented - queued behind the
20 Aug demo-follow-ups batch. Implementation session starts here.

**Serves:** the proforma UAC's own named "next task" (the PI-vs-PO verification screen this
plan absorbs) - `scm-proforma-invoice-acceptance-criteria.md`. Depends on the proforma FE
(`PLAN-scm-proforma-invoice-frontend.md`, shipped this batch).

## Decisions (captain, 20 Aug)

| Question | Decision |
| --- | --- |
| What does converting create? | **A CRM SPO record + an AutoCount handoff.** A real SPO row in the CRM's PO book, marked CRM-originated, plus an exportable worksheet the office keys into AutoCount. The next book import reconciles by number. AutoCount stays the system of record for ordering; the CRM SPO gives live visibility until the import catches up. |
| Grain? | **Line-level, pre-checked.** One screen per PI: every line pre-selected with a suggested qty; the buyer unticks or trims before converting. |
| POs and stock? | **Match PO + net stock.** A PI line matching an open PO line to the same supplier LINKS to it (already ordered - no new SPO line, shown as covered). The rest net against on hand + incoming SPO, the same arithmetic as the container request. Components visible, qty editable. |

## Journey

Actor: Ms Tee, on a proforma detail page (`/scm/proforma-invoices/{id}`) - the supplier has
sent the PI for what they are packing.

1. She presses **Convert to SPO**. The screen shows the PI's lines, every one pre-checked,
   each with: the invoice qty, any **matching open PO line** to this supplier (by product,
   then by the PI line's `po_ref` when it names one - the stated ref outranks inference),
   on hand, incoming SPO, and the **suggested SPO qty** = invoice qty, minus what a matched
   PO already covers, minus stock/incoming surplus - floored at 0, editable.
2. Lines fully covered by a PO or by stock read as covered (kept visible, unchecked by
   default, one line each says why). Unmatched-product lines (no catalogue product) cannot
   convert and say so.
3. She confirms. The system creates ONE SPO in the CRM PO book (CRM-originated source
   marker, supplier, currency and prices from the PI lines, expected date from the PI or
   asked once), writes the PI-line -> SPO-line links, and hands her the **AutoCount
   worksheet** (exportable file listing exactly what to key).
4. What she holds: a live SPO the planning views count as incoming the moment it exists,
   the worksheet for AutoCount, and a PI whose lines each show where they went (SPO line,
   linked PO line, or covered/skipped). The next AutoCount book import reconciles the CRM
   SPO by number - a match flips it to book-confirmed; a mismatch surfaces on the existing
   diff surface, never silently.

Nothing is asked that can be derived: supplier, currency, prices, quantities and the PO
matches all come off the PI and the books. Her decisions: which lines, final quantities,
and the expected date when no source states one.

## Design notes for the implementing session (verify all against code)

- **SPO record:** a `purchase_orders` header + lines with a CRM-originated `source_system`
  marker (existing rows use `scm_po_history` / `scm_spo_history` - pick a new value, e.g.
  `crm_spo`, and check every consumer that filters by source before choosing). SPO number:
  generated in a clearly-CRM series so an AutoCount import can never collide with it.
- **Reconciliation:** decide match key with the diff/import owner (number vs supplier+date
  +lines). The outstanding-import diff surface already exists; extend, do not fork.
- **PI-line links:** a link column/table from `scm.proforma_invoice_line` to the created
  SPO line / matched PO line - the audit trail step 4 renders. Prefer a small link table
  over columns if a line can split across targets.
- **PO matching:** open PO lines to the same supplier, matched by product_id; a stated
  `po_ref` on the PI line pins the match. Show remaining (ordered - received) as the
  covered qty.
- **Netting:** reuse the container-request arithmetic (open need context differs: here the
  base is the INVOICE qty, not SO need). State the formula on screen.
- **Worksheet:** follow the consolidated-packing-list export pattern
  (`consolidated_packing_list.py` + its export route) for the AutoCount handoff file.
- **Permissions:** conversion is a write to the PO book - new slug or an existing
  procurement write slug; sweep like migration 375 did if new.
- **Out of scope:** auto-creating inbound shipments (the packing list channel owns
  arrival); price variance vs PO (the verification screen ambition stays absorbed but
  variance ALERTING can land later - show the two prices side by side, no gate).
