# Proforma invoice as a first-class document - acceptance criteria

Status: Implemented, 2026-08-17, on branch `fm/scm-proforma-first-class` (unmerged). Gaps G3b +
G3c of the SCM fulfilment gap report (firstmate home,
`data/scm-fulfilment-gap/report.md`). Plan: `PLAN-scm-proforma-invoice.md`.

Backend slice. There is no NEW screen in this slice: the deliverable is the document, its
reader, its upload channel and the price that is no longer thrown away. The one frontend change
is the currency field on the EXISTING packing-list upload (AC-P5.4), because that channel now
refuses a priced file whose currency nothing states and the operator needs somewhere to state
it. The verification screen (PI vs PO, variance, overcharge) is the next task and depends on
this one.

## Journey

**Actor:** Ms Tee (purchasing / fulfilment office). She arrives from the fulfilment screen
after the supplier has sent, on WhatsApp, the packing list and the proforma invoice for the
container that is being loaded.

1. She picks the supplier (the file never says who wrote it reliably - Kailu's letterhead
   is a Hong Kong management company, Jinbaichuan's is a title cell in Chinese) and drops
   the proforma workbook on the upload. The system already knows the supplier's price-list
   currency when the supplier has one, and reads the currency the document itself states
   (`RMB`, `单价(元)`), so she is asked for a currency only when neither source says.
2. The preview shows: how many invoices the file holds (five, on a Jinbaichuan pre-loading
   list; one, on a Kailu proforma), each with its number, date, container reference when
   stated, line count, total, currency and where the currency came from - and the item codes
   we do not hold, named. Test gives the standard `{valid, errors, warnings, summary}`.
3. She presses Apply. Each invoice lands with every line: the supplier's item code verbatim,
   description, quantity, UOM, unit price, amount, and the PO reference on the lines that
   carry one. Re-uploading the same file updates the same invoices in place.
4. What she holds at the end: proforma invoices readable by supplier, with priced lines, in a
   stated currency - the input the next task verifies against purchase orders. Nobody else is
   told anything in this slice.

Separately, when she uploads the same Jinbaichuan pre-loading list through the existing
packing-list channel (S9), the shipment lines now carry the unit price the reader parsed and
the currency it belongs to, instead of the price being parsed and dropped.

## AC-P1 A proforma invoice is a document with lines `[BE]`

**AC-P1.1** Given an applied proforma, a header exists carrying: supplier, PI document number,
invoice date, currency, and the container / bill-of-lading reference when the document states
one (nullable, never invented).

**AC-P1.2** Every line carries: item code (verbatim, the supplier's spelling, no normalisation
beyond trim), description, quantity, UOM (nullable), unit price, amount, and the stated PO
reference when the line carries one. The PO reference column exists and is null on the lines
that do not carry one; the Kailu proforma lands with 19 lines of which exactly 3 carry a PO
reference (`202605-S0060` x2, `202605-S0084`).

**AC-P1.3** A line's `product_id` is set only on an exact, case-insensitive, company-scoped
match of `products.product_code`. No fuzzy match, no alias table. Unmatched lines are still
persisted (with `product_id` null) and named in the preview / test summary.

**AC-P1.4** Two proforma invoices from one supplier with the same document number are the same
invoice: applying the same file twice yields the same header rows with their lines replaced,
not a second set (idempotent by identity `(company, supplier, pi_number)`).

## AC-P2 The reader reads both real shapes `[BE]` `[T]`

**AC-P2.1** The reader has its own alias document type `proforma_invoice` in
`import_field_alias`, seeded by migration and replayed by `scripts/bootstrap_env` (same
mechanism as 311/338/347/357/358). No second aliasing scheme.

**AC-P2.2** Multi-block PI-format pre-loading list (`2026-7-31 SORENTO 预装清单.xlsx` shape):
five blocks, each headed by a title cell containing `Proforma Invoice`, labelled cells
(`Customer Name 客户名：`, `提单号：` blank, `Date 日期：` + a date cell, `Container No 货柜号：`
blank, `封条号：` blank), the 19-column header (`产品型号` ... `RMB` `金额（rmb）` `商标` `备注`),
lines, a totals row (`总金额`). Reads as **5 documents, 30 lines**, every line with unit price
and amount, invoice date 2026-07-31 on each, currency CNY stated by the document, no PI
number in the file (a positional one is derived: see AC-P2.5), container and BL both null.

**AC-P2.3** Kailu single proforma (`KAILU形式发票(Sorento)260717.xlsx` shape): letterhead
rows, `PROFORMA INVOICE - 形式发票`, labelled `货单号：` `KL20260717`, `日期：` `17.07.2026`,
header `序号` `品名` `编号` `产品数量` `单价(元)` `总价（元）` `其他`, 19 lines, `合 计` totals row,
signature and bank-detail rows. Reads as **1 document, 19 lines**, `pi_number=KL20260717`,
`invoice_date=2026-07-17`, currency CNY stated by the document (`元`), `po_ref` on exactly the
3 lines that carry one, item code with an embedded newline (`SRTWT8258\n-GM`) preserved
verbatim after trim of outer whitespace only, totals / bank rows are not lines.

**AC-P2.4** A blank labelled value stays blank: `提单号：` followed by the label `Date 日期：`
does NOT read the next label as the bill of lading (the defect the gap report recorded in the
packing-list reader's `_labelled`). The fix lives in the shared helper, so the packing-list
channel is corrected by the same change and a regression test pins it there too.

**AC-P2.5** A block that states no document number gets a derived one, positional and stable
across re-upload: `PI-<file stem>-<block index>`; a document that states one keeps it
verbatim.

**AC-P2.6** A file with no recognisable header (item code + quantity + unit price on one row)
is refused with the missing columns named, never partially applied.

## AC-P3 Currency is never assumed `[BE]` `[T]`

**AC-P3.1** Currency resolves in this order, and the preview names which one won:
`upload form value` > `stated by the document` (unit-price / amount header carrying `RMB`,
`元`, `CNY`, `¥` -> CNY; `USD`, `US$` -> USD; `MYR`, `RM` -> MYR; or a labelled `Currency:` cell)
> `the supplier's price list, when every priced product_suppliers row for that supplier
agrees on one currency` > none.

**AC-P3.2** When priced lines exist and no currency resolves, Test returns an error naming the
gap ("state the currency this invoice is in") and Apply refuses with 422. A price is never
stored without its currency.

**AC-P3.3** No house default. A supplier whose price list is mixed-currency resolves to none,
not to the majority.

## AC-P4 The upload channel has the shape every other channel has `[BE]` `[T]`

**AC-P4.1** `POST /api/v1/scm/proforma-invoices/preview` (file + supplier_id [+ currency]) -
writes nothing, returns per-document summary. `POST /api/v1/scm/proforma-invoices/apply`
with `?validate_only=true` returns `{valid, errors, warnings, summary}`; without it writes and
returns per-document results with created / updated counts.

**AC-P4.2** `GET /api/v1/scm/proforma-invoices?supplier_id=` lists headers newest first;
`GET /api/v1/scm/proforma-invoices/{id}` returns the header with its lines. Deletion:
`DELETE /api/v1/scm/proforma-invoices/{id}` hard-deletes header + lines.

**AC-P4.3** Preview / apply / delete are gated on the new permission
`scm.proforma_invoice.upload` (registered in `permission_registry.py`); reads are gated on
`scm.dashboard.view`. The migration sweeps the new grant onto every role that currently holds
`scm.reorder.run`, excluding `integration_*` roles. A caller with no permission gets 403.

**AC-P4.4** No UUID reaches a human: list / detail responses carry supplier code + name and
product code where a product matched.

## AC-P5 The pre-loading list stops dropping its prices `[BE]` `[T]`

**AC-P5.1** `packing_list_service.apply` writes `unit_cost` and `currency` onto each
`inbound_shipment_lines` row from the reader's `unit_price` and the resolved currency
(same order as AC-P3.1: form value > document > supplier price list).

**AC-P5.2** A packing list with priced lines and no resolvable currency: Test errors, Apply
422s (AC-P3.2). A packing list with NO prices is unaffected: lines land with `unit_cost` null
and no currency demanded (the existing tests keep passing unchanged).

**AC-P5.3** A stated currency is never overwritten downstream: `_capture_incoming_cost`
already returns early when `line.currency` is set; a test pins that a stated CNY survives an
allocation against a PO line in MYR.

**AC-P5.4** `[FE]` The packing-list upload dialog carries an optional `Currency` field (a
three-letter code, upper-cased), sent with the read, the Test and the Apply, and left out
entirely when empty so a blank never overrides what the file states. Where the read resolved
one, the preview says which currency and where it came from; where the file is priced and
nothing resolved, it says so before Confirm is pressed.

## Known limits (accepted, not defects)

- **A derived document number is only as unique as the file name.** A block that states no PI
  number is named `PI-<file stem>-<block index>` (AC-P2.5), so two DIFFERENT files uploaded for
  the same supplier under the SAME filename - or filenames sharing their first 80 characters,
  since the stem is truncated to 80 so the block index always survives - derive the same
  numbers and the second one replaces the first in place. That is the price of idempotency without a generated id: the alternative
  makes a genuine re-upload create a second set. A supplier whose documents state their own
  number is unaffected. Where it bites, rename the file.

- **Two blocks in ONE file stating the same PI number replace each other.** `apply` resolves
  each block independently by `(company, supplier, pi_number)`, so the second block's lines
  overwrite the first block's and the stored `line_count` / `total_amount` describe the last
  block only. Unreachable in both known supplier shapes: Jinbaichuan's blocks state no number
  at all, so theirs are positional and therefore distinct, and Kailu's file is a single
  document. If a supplier ever stacks a repeated number, the honest outcomes are to merge the
  blocks or to refuse the file naming the duplicate, and that is the change to make then.

- **Editing a shipment through the ordinary Packing Lists form drops the captured price.**
  `procurement_service.update_shipment` replaces every line from the payload it is given, and
  the FE form's line schema carries only `product_id` and `quantity_shipped`, so saving an edit
  (a note, a date, anything) reinserts the lines with `unit_cost` and `currency` NULL. That
  supplier then reads as "never received" on the Order Decision sheet again, and the PI-vs-PO
  check loses its incoming side. The mechanism pre-dates this slice (SPO allocation already
  stamped cost and currency onto these lines); what changed is that the ingest now fills the
  column, so the wipe went from theoretical to the normal outcome of a routine edit. Accepted
  here rather than fixed, because the fix touches `update_shipment` and the packing-list form,
  a surface a concurrent worker owns: it is a named follow-up for the packing-list task, whose
  options are to preserve both fields from the replaced line matched on `product_id` when the
  payload states neither, or to carry them through the form's line schema. Tracked as **BL-023**
  in `documentation/backlogs/backlog.md`, which is where the follow-up is picked up from.

## Out of scope (owned elsewhere)

- PI-to-PO matching, variance, overcharge detection (next task).
- Multi-supplier container combining / additive uploads / `supplier_id` on shipment lines
  (live now in another worktree - rebase expected).
- Loading-plan demand ranking (live now).
- Any frontend screen. The upload channel is API-complete; the screen ships with the
  verification task that consumes it.
- Fuzzy item-code matching or a code-alias table.
