# PLAN - Customer PO edit view

**Status:** implemented 2026-08-18 (FE + BE + tests + evidence run). Not reviewed.
**Slug:** po-edit-view. **UAC:** `po-edit-view-acceptance-criteria.md`.
**Parent:** `PLAN-quotation-edit-view.md` - same complaint, same answer, other document.
**Classification:** CORE (part of the project-sales module already installed), `projects` schema,
no new table and no migration.

## Why

The client, on the quotation: *"every addition of line doesn't trigger a save, cause now i delete
each line, then you ask me to confirm, then when i add line, you also trigger save, very annoying,
we should have an edit view imo"*. The quotation document got that edit view (S10/S11). The
customer PO page still had the old behaviour, and the request is verbatim: *"we need edit function
in purchase order (just like our quotation, please use the same design methodology as our quotation
page), so it is not line by line edit and save, it is entering an edit page, make changes to header
and lines, then click save"*.

Two faults, plus one the ask exposes:

1. **Every line wrote on blur**, with a confirmation dialog per removal. Correct for a table that
   is the whole feature, wrong for one section of a record with a single Save.
2. **The header could not be read at all on the record.** PO number, date, source, issuer, bound
   version, amount and notes lived ONLY inside a modal, so reading the bound version meant opening
   the form that changes it.
3. **The header had two editing surfaces** waiting to disagree: the list's pencil and (once this
   lands) the page. One had to go.

## The quotation methodology, and what is mirrored

Read `QuotationDocumentClient` + `useQuotationEditSession` + `QuotationVersionEditor` for the
original. Mirrored exactly:

- **In-place edit MODE on the record's own page**, not a separate `/edit` route. The entry point is
  behind the gear (`Edit the PO`); once the session is open, Cancel and Save replace the primary CTA
  in the page header, where a control you are about to press can be seen.
- **A session hook holds everything and writes nothing** (`usePurchaseOrderEditSession`): staged
  lines, a header draft, `isDirty`, `linesChanged`, `removedCount`. Dirty is measured against what
  the server had when the session opened, so typing a value and typing it back leaves Save disabled.
- **The shown record is `{...server, ...headerDraft}`**, merged once at the top, because the title,
  the facts line and the header card all read it and must not disagree.
- **The line table is the shared `InlineLineTable` in `staging` mode**, `readOnly` outside a session.
  No per-row tick, no per-row delete dialog, removal struck through and restorable.
- **One confirmation, at Save, naming the count**, when the save deletes stored lines. Staging a
  removal destroys nothing, so it asks nothing (the reconciliation with
  `feedback_confirm_before_delete_or_unlink` is the parent plan's, unchanged).
- **`beforeunload` warns** while dirty; totals are recomputed from the live drafts with the repo's
  decimal-exact string helpers.

## Two deliberate deviations

1. **ONE request, not two.** The quotation Save writes a bulk-lines PUT per scope plus a document
   PATCH, because one quotation document spans several scopes and cannot be atomic anyway. A PO is
   one header and one line set, so `PUT /purchase-orders/{po_id}` takes both and applies them in one
   transaction. A header PUT followed by a lines PUT could half-land, leaving a renamed PO whose
   lines never moved.
2. **No context provider, and the session lives with the page.** The quotation's tabs are ROUTES, so
   its session must live in a shell and reach panels through context or a tab switch would throw the
   work away. The PO page is one page with no tabs; a flat session and a prop is the whole need.

Also: the list's Edit pencil now routes to `pos/{id}?edit=1` and `PurchaseOrderDialog` is
CREATE-only. Two editing surfaces for one header is exactly what the view-and-edit-are-the-same rule
exists to stop.

## Route contract

`PUT /api/v1/project-sales/purchase-orders/{po_id}` (permission `projects.projects.edit`)

```jsonc
{
  // Header: any subset. Unset keys are left alone.
  "po_number": "HQ/26/01/121",
  "po_date": "2026-01-16",
  "po_source": "contractor_direct",     // contractor_direct | trading_house
  "issuing_party_id": null,
  "quotation_version_id": null,
  "po_amount": "1805907.02",
  "notes": "BTB/WA",

  // OMIT to leave the lines untouched. [] clears them. Present = the FULL desired set, in order.
  "lines": [
    { "id": "<existing line id>", "product_id": null, "product_code": "SRTWC86",
      "description": "...", "unit_price": "392.85", "quantity": "927.00",
      "uom": "PCS", "notes": null },
    { "product_code": "THEIRS-7", "unit_price": "410.00", "quantity": "1" }
  ]
}
```

Answers the usual `ProjectPurchaseOrderResponse` (now carrying
`published_sales_order_count`). `sort_order` is array position and is ignored if sent. Refusals:
422 `po_line_identity_required` / `po_line_duplicate`, 404 `po_line_not_found`, 403 without the
permission - each rolls the whole save back.

## Invariants preserved

- **Extraction provenance is untouched.** This writes `projects.purchase_orders` and
  `projects.purchase_order_lines` only. `po_versions` / `po_lines` (the document as read, with its
  extracted JSON, arithmetic scores and annotations) are immutable once confirmed and are never
  touched here.
- **A PO whose sales orders are out stays editable, but the screen says so.** Corrections are the
  normal case, and refusing them would strand the user; silently allowing them would hide that the
  published orders do not follow. The list now reports `published_sales_order_count` and the edit
  session states it. A blocking guard was rejected: the amendment flow, not this screen, is where a
  published SO changes.
- Mismatches are flagged, never blocked (AC-F9). Erosion from v1 stays a number, not a flag.
- `updated_at` is stamped by the column's `onupdate`; the audit listeners on `purchase_orders`
  record who. No activity event: an ordinary field edit deliberately does not advance the
  meaningful-activity clock (`project_activity_service`).

## Evidence run (2026-08-18, agent-browser, FE :3050 + BE :8030, real prod-copy data)

Sidebar Project Sales -> Pipeline -> PRJ-000003 (PO Received) -> POs tab -> row pencil on
`HQ/26/01/121` (92 lines, RM 1,805,907.02).

1. `?edit=1` opened the session on arrival; header fields were inputs holding their values; Save
   disabled with "Nothing has changed yet".
2. Line 1 qty 927.00 -> 928: row total, table footer and the header's "Lines total" all moved to
   RM 1,806,299.87 with no request; Save enabled.
3. Save -> exactly ONE `PUT .../purchase-orders/0d436b19-...` 200 in 1.87s; page returned to the
   read view with the new total.
4. Reverted to 927.00 the same way (data left as found).
5. Notes edited then Cancel -> read view shows the stored `BTB/WA`, and no request was made.
6. 375px and 1280px: no clipping, `scrollWidth == clientWidth`, header actions wrap. Console clean.

**Known trap for the next run:** agent-browser's click on an off-screen element is a silent no-op.
Three Save clicks did nothing until `scrollintoview` was run first, which reads exactly like a
broken button.

## Definition of done

1. A 92-line PO is saved in ONE request, not 92. Done (measured above).
2. No dialog while staging; one at Save when lines leave; the PO's own delete dialog unchanged.
3. Cancel restores what was on screen before Edit. Done.
4. The header is readable on the record, in the same order it is edited in. Done.
5. pytest + vitest green; no new Playwright spec (standing order), evidence run recorded above.
