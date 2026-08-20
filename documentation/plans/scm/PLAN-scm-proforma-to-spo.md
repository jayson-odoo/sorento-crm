# PLAN - a proforma invoice becomes an SPO: convert, match, net, hand to AutoCount

**Status:** Journey + three shaping decisions approved by the captain, 20 Aug 2026 (live
session, while testing the new proforma screen). AMENDED the same evening: the flow now
bends through the packing list (see the Amendment section - it supersedes parts of the
original decisions and journey below).

**First half BUILT, 20 Aug 2026 (same evening):** the PI -> DRAFT INBOUND SHIPMENT convert
from the Amendment's first decision. What shipped:

- `POST /api/v1/scm/proforma-invoices/convert-to-draft-shipment` (body
  `{proforma_invoice_ids: string[]}`, permission `scm.reorder.run` - the same one the
  packing-list apply path writes under, not the proforma-upload permission). One or more
  PIs, any suppliers, become ONE `inbound_shipments` row with `shipment_status = 'draft'`
  (a new value in that column's vocabulary - migration 405 extends the live check
  constraint; deliberately NOT declared on the SQLAlchemy model, so `blank_session()` tests
  that already drive the column through dead legacy values keep passing - see the comment
  at `InboundShipment.__table_args__`). Every shipment line carries its OWN `supplier_id`
  from the PI it came from - the multi-supplier-per-container rule, migration 374 -
  matching (product, supplier) PI lines across the selected invoices are merged onto one
  shipment line (quantity summed, cost quantity-weighted-averaged), never onto the header.
- Provenance: `scm.proforma_invoice_shipment_link` (one row per PI line touched by a
  convert - unique on `proforma_invoice_line_id`), pointing at the shipment line it became,
  or carrying `unmatched_reason` when the convert could not carry it across (no catalogue
  product match, or no positive quantity - `inbound_shipment_lines.product_id` is NOT
  NULL, so these are reported, never silently dropped). A partial match still creates the
  shipment; only a selection with NOTHING convertible is refused (422).
  `proforma_invoice_service.serialize()` reads this back as `converted_shipments` (header)
  and per-line `shipment_id`/`shipment_number`/`unmatched_reason`, so a PI shows where each
  line went from its own detail page.
  - the packing-list -> SPO trail (next slice) is a SEPARATE link, per the Amendment's
    "PI line -> shipment line (draft), and shipment line -> SPO line" composition - not
    built by this slice.
- Idempotency: a PI with ANY existing link row is refused with a 409 naming the invoice and
  the shipment it already went to, rather than silently doubling what counts as incoming.
  `bulk_delete` and the single `DELETE` both refuse (never cascade) a converted PI for the
  same reason, naming the shipment.
- Also folded into this pass (captain, same evening, same files): bulk delete on
  `/scm/proforma-invoices`, mirroring the PO book's bulk delete (commit d6f048f3d) -
  `POST /api/v1/scm/proforma-invoices/bulk-delete`, row-selection + one "Actions" dropdown
  shared with Convert, AlertDialog confirmation naming the count.
- FE: the "Convert to draft shipment" action lives on BOTH the proforma-invoices LIST
  (multi-select via the shared select column + Actions dropdown - the natural surface for
  picking more than one PI into one container) AND the single-PI detail page (same action,
  one-invoice selection). Both land on `/scm/incoming?shipment=<shipment_number>` on
  success (human-readable number in the URL, never the id) - `IncomingContainersView` reads
  the param once and pre-selects the matching row.
- NOT built (the next slice): the "Create SPO" action off the shipment, and reconciling a
  REAL packing-list upload onto this exact draft shipment row (today a later
  `/scm/packing-lists/apply` for the same container creates its own shipment unless it
  happens to share a shipment/container number - the draft's `shipment_number` is its own
  `SHIP-DRAFT-...` series precisely so it never COLLIDES with a real upload's derived
  number, but nothing yet makes the two MERGE). That merge is unstarted work for whoever
  picks up the SPO half.

Implementation session for the remainder (Create SPO) starts here.

**Serves:** the proforma UAC's own named "next task" (the PI-vs-PO verification screen this
plan absorbs) - `scm-proforma-invoice-acceptance-criteria.md`. Depends on the proforma FE
(`PLAN-scm-proforma-invoice-frontend.md`, shipped this batch).

## Decisions (captain, 20 Aug)

| Question | Decision |
| --- | --- |
| What does converting create? | **A CRM SPO record + an AutoCount handoff.** A real SPO row in the CRM's PO book, marked CRM-originated, plus an exportable worksheet the office keys into AutoCount. The next book import reconciles by number. AutoCount stays the system of record for ordering; the CRM SPO gives live visibility until the import catches up. |
| Grain? | **Line-level, pre-checked.** One screen per PI: every line pre-selected with a suggested qty; the buyer unticks or trims before converting. |
| POs and stock? | **Match PO + net stock.** A PI line matching an open PO line to the same supplier LINKS to it (already ordered - no new SPO line, shown as covered). The rest net against on hand + incoming SPO, the same arithmetic as the container request. Components visible, qty editable. |

## Amendment - the flow bends through the packing list (captain, 20 Aug evening)

Live-tested with the real documents
(`fulfilment_example_files/KAILU形式发票(Sorento)260717.xlsx` and `FSCU8103365.xlsx`), the
captain corrected the flow: **PI -> packing list -> SPO**. The SPO is built from the
PACKING LIST (what actually ships), not from the PI. Grounding from the files:

- A PI is ONE factory's invoice: model, qty, unit price, and sometimes our PO doc no
  (`202605-S0060`) on the line.
- A packing list is ONE CONTAINER consolidating SEVERAL factories' PIs (FSCU8103365 packs
  AFANNI + CAIZHOU + KAILU + IDC), with vessel dates, cartons, CBM, weights.

Two shaping decisions (captain, same session):

| Question | Decision |
| --- | --- |
| What does "convert PI to packing list" do? | **Draft shipment from PIs.** Pick one or more PIs -> the system creates a DRAFT inbound shipment (`/scm/incoming`) pre-filled with their lines. When the agent's real packing list arrives, it is uploaded onto the same shipment and replaces/reconciles the draft, showing PI-vs-packed differences. **BUILT** (20 Aug evening, this session) - see the Status line at the top for the endpoint, the `draft` status, the provenance table and where the FE action lives. The "uploaded onto the SAME shipment" half is NOT built: a real packing-list upload today creates its OWN shipment unless it happens to share a number with the draft (the draft's `SHIP-DRAFT-...` series exists precisely so it never collides) - merging the two is unstarted, flagged for whoever builds the SPO half. |
| When is the SPO created? | **Separate button after packing-list apply.** The shipment page gets a "Create SPO" action she presses when ready. Suggestion logic as originally planned (match open PO lines by product / stated po_ref / delivery date, net on hand + incoming SPO), but the BASE quantity is the PACKED qty, not the invoice qty. **NOT BUILT** - this is the remaining half of this plan. |

Consequences for the sections below:

- The original decision "converting creates a CRM SPO + AutoCount handoff" STANDS, but its
  source document is now the packing list; the journey's screen moves from the PI detail
  page to the inbound shipment page.
- The original "Out of scope: auto-creating inbound shipments" is REVERSED - creating the
  draft shipment from PIs is exactly the convert function.
- PI-line links now run PI line -> shipment line (draft) - BUILT, `scm.proforma_invoice_
  shipment_link` - and shipment line -> SPO line - NOT BUILT, next slice; the PI -> SPO
  trail is the composition of the two.

## Journey (original - screen placement superseded by the Amendment above)

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
