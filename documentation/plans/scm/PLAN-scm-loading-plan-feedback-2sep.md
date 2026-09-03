# PLAN - Loading plan feedback batch, 2 Sep 2026

**Status:** APPROVED by the captain 2 Sep 2026 (Lavish markup round, "ok all good, can start"). Implementation on `feat/scm-loading-plan-feedback-2sep`. UAC: `scm-loading-plan-feedback-2sep-acceptance-criteria.md`.
Four rulings taken 2 Sep (section 2). Branch `feat/scm-loading-plan-feedback-2sep` off
`origin/main` (the primary checkout is 47 commits behind main; nothing here builds on it).

**Amends:** `PLAN-scm-fulfilment-feedback-p4.md` R3/R5 (row actions, gear, subtitle),
`PLAN-scm-loading-plan-demand-first.md` section 6b.1 (one table, no-demand rows),
`PLAN-scm-proforma-invoice.md` (stand-in invoice selection). Applies `DESIGN-LANGUAGE.md` D6,
D7, D15 to the loading plan, which never adopted them.

## 1. What was measured (2 Sep, prod DB read-only + origin/main source)

| Symptom the captain saw | Cause, with evidence |
| --- | --- |
| Delete and Cancel "not clickable" on the Sent plan | Delete disabled by design on `sent_at` (p4 R3: sent plans are cancelled, not deleted). Cancel enabled. Two grey ghost icons side by side read as one dead pair. `LoadingPlansGrid.tsx:257-306` on main. |
| Not under a "..." menu | `RowActionsMenu`, `DetailActions actions=`, `use<Entity>Actions` (D15) shipped in apple S3/S6 for 16 entities; `scm/loading-plan/` has no `actions.tsx`, the record gear is a raw `DropdownMenu`, Cancel is an immediate mutation behind `ConfirmActionDialog`. |
| Information overload on the record | One scroll: unmatched panel (58 rows), stat cards, the request grid, the sent card. No tabs. |
| Match = row vanishes, no undo | `onPick` writes the alias then invalidates; the refetch drops the row. `DELETE /supplier-code-aliases/{id}` exists and re-runs the ladder, but the UI offers it only on dismissed codes. |
| Where is the memory | `scm.supplier_product_code_alias`, key (company, supplier, upper(code)), target product OR set, `matched_by` in manual / separator / token_set / size_drop, dismissed = neither target. Rung 0 of `supplier_code_matcher.resolve` on every later upload for that supplier. Visible only on the plan's unmatched panel and the PI detail's match dialog. Product Suppliers tab, product set page, supplier page: nowhere. A manual match never writes `product_suppliers`, the very link that puts a product in the plan universe. |
| ROYAL MIRROR "No file" plan shows 79 unknown codes | The panel is supplier-wide (`unmatched_for_supplier`, no plan filter). Prod holds a 115-row stock list under ROYAL MIRROR uploaded 17 Aug, the same row count as JINBAICHUAN's list: wrong supplier picked in an earlier upload. The subtitle says "No file" while the plan silently runs on that stale snapshot. Captain's ruling on markup: plan data is per plan (section 3.6). |
| What populates the list | Universe = `product_suppliers` links ∪ statement on file (stock list, else ONE unconverted PI) ∪ set drivers (`container_request_service.build`, L1139-1372). Demand never adds a product, only ranks it. Need / On hand / SPO are company-wide per product. No-demand rows exist by the 20 Aug ruling "nothing the stock list holds may vanish in the merge". |
| Same file, different rows | The file is ONE sheet with FIVE stacked invoice blocks (header rows 8, 18, 29, 57, 70). Reader emits 5 PIs, suffix = block index. Supplier is always the dialog pick, never the letterhead (which says JINBAICHUAN). Confirmed three times under KAIPING, MPM, FLOSSY, so prod has 5 PIs under each. A plan then reads ONE PI: `ORDER BY invoice_date DESC, created_at DESC, id DESC LIMIT 1`, and all five tie on date and timestamp, so the UUID decides. MPM's plan drew block 4, FLOSSY's block 2. |
| Need 1,573 vs 3,991 for SRTWB243 | SO cut-off 31/10 excludes later-dated SO lines. Correct. |

Fix per symptom (captain asked for the mapping on the markup round):

| Symptom | Fix |
| --- | --- |
| Delete / Cancel not clickable | S1: both in a "..." menu; Delete refused on a sent plan but SAYS why (`disabledReason`); Cancel works as a 5s countdown. |
| Not under "..." | S1: `actions.tsx`, row menu = record gear, Send to supplier inside, toolbar pager · gear · Save · Back. |
| Information overload | S2 tabs; S5 folds no-demand rows. |
| Match vanishes | S3: row stays with Undo; Dismiss same. |
| Memory: where | S3 Remembered list; S4 "Their code" on the product's Suppliers tab + product-supplier link on a manual match. |
| ROYAL MIRROR stale snapshot | S6 plan-owned statement (No-file plan = no codes); S7 codes header names the plan's statement. |
| What populates the list | S6 universe (WHO is a candidate) = links ∪ plan's statement ∪ aliases (S4) ∪ drivers. Demand decides WHERE, not whether: Lines table = candidates with open demand, ranked; fold (S5) = candidates with no open demand. A product with demand but none of the four memberships is not asked of this supplier. S8 documents it. |
| Same file, different rows | S6 all blocks bound and summed; S7 verdict counts + letterhead warning; S8 format doc. |
| Need differs by cut-off | No fix; S8 documents the rule. |

## 2. Rulings (captain, 2 Sep)

| Question | Ruling |
| --- | --- |
| After picking a product on an unknown code | **Row stays in place, matched, with Undo.** No countdown. Moves to the remembered list on the next load. |
| Does a manual match reach master data | **Yes: link + show code.** Manual match upserts `product_suppliers` when missing; product's Suppliers tab shows "Their code" from the alias table. Sets: alias only. |
| Held-but-no-demand rows | **Collapsed group, one line** under the ranked rows. The 20 Aug invariant survives with one line of chrome. |
| A PI file with stacked blocks | **One plan, all blocks summed.** Plan binds to every invoice the upload created; Packed = sum; drill shows the split. |

**Markup round (captain, 2 Sep, on the Lavish page):**

| Markup | Consequence |
| --- | --- |
| "The data in the plan should be respective to the plan, not per supplier" | **A plan owns its statement.** The stock list rows and the invoices a plan's upload created are stamped with the plan id; the codes tab, the holdings and the subtitle read the plan's own rows, never the supplier's latest. A "No file" plan has no codes and no holdings. Supersedes p4 R2 / AC-A17 (older plan's figures moving on a newer upload) and section 4's "not built: per-plan snapshot". S6 widens to both document kinds. |
| "Put Send to supplier in the gear icon dropdown" | Send to supplier becomes a gear item (and a row menu item). Toolbar right cluster: pager, gear, Save (N), Back. |
| "I need this (the memory) to be in UI" | S3 Remembered list + S4 "Their code" on the product's Suppliers tab, as planned. |
| Stack slot | A third slot: FE :3130, BE :8130 (3120/8120 were already held by integration-1sep). |
| Formats doc | Repo doc AND Outline user guide. |
| Prod ROYAL MIRROR snapshot | Leave it. With per-plan statements it can no longer leak into a plan. |

Defaults kept: letterhead mismatch is a **warning**, not a refusal; tabs are Lines · Supplier
codes · Sent, Lines default (captain renamed Request to Lines on the markup round); Cancel joins the deferred engine (5s) so both row actions behave
alike.

## 3. Design

### 3.1 One action set (S1) - D15 applied

`app/(protected)/scm/loading-plan/actions.tsx` exports `useLoadingPlanActions(plan, { onDeleted,
onCancelled, surface })` returning `RecordActionSet`, shaped exactly like
`user-management/users/actions.tsx`. Items, in order: View uploaded list (only with an
attachment), Refresh matching, Refresh suggestion, Copy link (`confirmLabel: 'Copied'`),
Download XLSX, Download PDF, Send to supplier (opens `SendRequestDialog`; disabled with reason
on a cancelled plan), Change cut-off, Cancel plan, then destructive: Delete plan. The toolbar
right cluster becomes pager, gear, Save (N), Back to loading plans; the standalone Send button
leaves the toolbar (captain's markup).

- `LoadingPlansGrid.tsx` actions column becomes `<LoadingPlanRowActions plan={row.original} />`
  (`RowActionsMenu`, `surface: 'toast'`). The two icon buttons and the cancel
  `ConfirmActionDialog` go. `rowPending` stays.
- `LoadingPlanView.tsx` passes `actions={actions}` and `pendingAction={pending}` to
  `DetailActions` instead of the raw `gear`. Refresh-suggestion's "Drop your N typed
  quantities?" and the leave-without-saving prompt stay as dialogs owned by the view (data-loss
  questions, the D7 carve-out); the cancel `ConfirmActionDialog` goes.
- Cancel = `useDeferredAction({ actionKey: 'loading_plan.cancel', window reversible })`, so
  the row dims and the toast counts down like Delete. Backend: one `register(FormAction(
  key="loading_plan.cancel", entity_types=("loading_plan",), execute=_cancel_loading_plan,
  window=WINDOW_REVERSIBLE, permission="scm.reorder.run", label="Cancel loading plan"))` in
  `record_actions.py`, `execute` delegating to `loading_plan_service.cancel` (never inlined).
  Park-time refusals: 409 `plan_cancelled` for cancel on a cancelled plan, 409 `plan_sent` for
  delete on a sent plan (the existing DELETE guard, reused in `_delete_loading_plan`).
- **Primitive change (foundation in the right place):** `RecordAction` gains
  `disabledReason?: string`; `RecordActionItem` forwards it as `title` on the
  `DropdownMenuItem` and as `aria-description`. Every existing consumer is unchanged (optional
  field). Guardrail: a vitest on `recordActions.tsx` renders a disabled item and asserts the
  title. Loading plan uses it for "Sent plans are cancelled, not deleted" and "Already
  cancelled".

### 3.2 Tabs (S2)

`LoadingPlanView.tsx` wraps the body in `Tabs variant="line"` (`components/ui/tabs`, the
D9 default), value from `?tab=` via `useSearchParams` (`lines` default, `codes`, `sent`).
Toolbar (`PageHeader` + `DetailActions`) stays above the strip. Tab contents:

- **Lines**: `ContainerRequestStatCards` + the What-to-ask card, Table / Schedule toggle as
  is. The inline `noticesCard` leaves `ContainerRequestSection` (it renders on the Sent tab).
- **Supplier codes (N)**: the S3 panel. N = `unmatched.length`.
- **Sent (N)**: the existing "Requests sent to X" card, promoted from `noticesCard` into its
  own component (the unrendered `SupplierNoticePanel.tsx` is either reused or deleted; a
  duplicate must not survive). N = notices count. Empty state "Nothing sent yet" + Send button.

Counts come from queries the page already runs; no new endpoint.

### 3.3 Supplier codes tab (S3)

`UnmatchedSupplierCodesPanel.tsx` becomes `SupplierCodesTab.tsx` with two groups:

- **Needs a decision (N)**: today's columns. On pick: mutate, then keep the row in a local
  `decided` map `{ code -> { kind: 'matched', product | set } | { kind: 'dismissed' } }`. The
  row renders the decision (code + name, or "Dismissed") and an **Undo** link. Undo calls the
  existing `DELETE /supplier-code-aliases/{id}` (the create/dismiss response must return the
  alias id; it does today) and clears the map entry. The query is NOT invalidated on pick; it is
  invalidated on Undo and on unmount, so the decided rows only leave on the next load. Rows
  never reorder while the tab is open.
- **Remembered (M)**: `GET /supplier-code-aliases?supplier_id=` (extend the existing list
  endpoint to return every alias, not only dismissed; response per AC-C5). Columns: Code,
  Matched to (product/set code + name, or "Dismissed"), How (label map of `matched_by`), When,
  By. Forget = `useDeferredRowAction({ actionKey: 'supplier_code_alias.forget' })`, already
  registered.
- Header line names the statement in use (AC-G2), from `plan.document_label`.
- **Scope is the plan.** `GET /supplier-code-aliases/unmatched?plan_id=` replaces the
  `supplier_id` form: it reads `supplier_inventory` rows and `proforma_invoice_line` rows
  stamped with this plan (section 3.6). Refresh matching (`rematch`) takes `plan_id` too and
  rebinds only this plan's rows. The Remembered list stays per supplier (memory is the
  supplier's, not the plan's).

### 3.4 The match reaches master data (S4)

- `supplier_code_alias_service.create()` (manual path only, `product_id` set): after
  `_record`, `_ensure_product_supplier_link(db, supplier_id, product_id)`: no-op when a
  `(product_id, supplier_id)` row exists; otherwise `standard_lead_time_days` = mode of the
  supplier's existing links (ties: max), `is_primary_supplier=False`; with zero existing links
  no row is written (no honest lead time). `ProductSupplierService.create_product_supplier`
  is NOT called (it 409s on duplicates and demands a payload); the helper writes the ORM row
  directly through the company-scoped session. `delete()` never touches the link (AC-D4).
- `container_request_service._linked_products` gains a UNION with
  `SupplierProductCodeAlias` rows for the supplier where `product_id` is not null (and set ids
  into the driver leg where `product_set_id` is not null), dismissed rows excluded.
- `GET /procurement/product-suppliers/product/{id}`: each row gains `supplier_item_code`
  (LEFT JOIN alias on product + supplier, upper-cased code as stored). Declared on
  `ProductSupplierSourcingTerms` so every `ProductSupplierResponse` route carries it; pytest
  asserts it (response_model lesson). `ProductSuppliersTab.tsx` adds "Their code" to the `dl`.
  No column on `product_suppliers`: the alias table is the single writer.

### 3.5 Fold the no-demand rows (S5)

`ContainerRequestSection.tsx`: rows with `has_demand === false` are split out of the DataGrid
data and rendered under it in a `Collapsible` line "N products held with no open demand"
(chevron, `aria-expanded`), expanded body = a second `DataGrid` with the same column set and
the same `listingKey` (one preference store, one look). Edits on folded rows keep flowing into
`edits` state. Default collapsed, state in component memory. No shared component is built for
one consumer; the trigger is the second fold.

### 3.6 A plan owns its statement (S6)

The plan is created FIRST, then the file is applied against it, so every row the upload writes
carries the plan id. The supplier's "latest snapshot" stops being what a plan reads.

- Migration `454_plan_owned_statement`, head chained on `453_shared_brand_attach`:
  - `scm.proforma_invoice.loading_plan_id` UUID NULL, FK `scm.loading_plan.id` ON DELETE SET
    NULL, index.
  - `scm.supplier_inventory.loading_plan_id` UUID NULL, same FK, index. The unique index
    `(company, supplier_id, item_code)` becomes `(company, supplier_id,
    coalesce(loading_plan_id, nil-uuid), item_code)`, so a plan's rows and a standalone upload's
    rows coexist. Existing rows stay `NULL` (the legacy supplier-wide snapshot).
- `PlanContainerDialog` order: Confirm = `POST /loading-plans` (status planning, no rows) →
  apply with `loading_plan_id` → navigate. An apply failure deletes the just-created plan
  (same DELETE) and shows the verdict error; the user is never left with an empty plan.
- `supplier_inventory_service.apply(..., loading_plan_id)`: with a plan id it replaces ONLY
  that plan's rows (re-upload into the same plan is still a replace); without one it keeps
  today's supplier-wide replace for the standalone upload page. `proforma_invoice_service
  .apply(..., loading_plan_id)` stamps every created or revised invoice.
- `container_request_service.build(plan)`: holdings = the plan's own `supplier_inventory`
  rows when `document_kind == 'stock_list'`; the plan's own invoices (current revision, summed
  per product/set, `blocks: [{block_index, pi_number, qty}]` for the drill) when `'proforma'`;
  nothing when `'none'`. Universe for `'none'` = `product_suppliers` links ∪ aliases (3.4) ∪
  drivers. `_stock_list()` / `_standin_proforma()` (supplier-wide) remain ONLY for legacy plans
  with no stamped rows, and are marked for deletion once every open plan predating 454 is
  cancelled or sent.
- `holding_as_of` = the plan rows' `as_of` / max `invoice_date`; `holding_blocks` = invoice
  count. FE `HoldingCell` prints "PI dd/mm/yyyy · 5 blocks"; the drill dialog gets a Blocks
  table.
- `_document_label` is computed from the plan's own rows: "Stock list dd/mm/yyyy" (its rows'
  `as_of`), "Proforma invoice <pi_number>" for one bound invoice, "Proforma invoice <source_ref
  stem> · N blocks" for several, "No file" for `'none'`. Never re-looked-up from the supplier.
- Alias `_rebind` (on match / dismiss / forget) keeps updating every row for the supplier,
  plan-scoped rows included, so the memory applies across plans; the codes tab only SHOWS this
  plan's rows.
- Consequence recorded: p4 AC-A17 ("a newer stock list changes an older plan's figures")
  is retired; the new AC-F6 asserts the opposite.

### 3.7 Name the statement, catch the wrong supplier (S7)

- `document_label` for `'none'` stays "No file", and the plan reads no statement (3.6);
  `record_dict` exposes `statement_as_of` (the plan rows' date, null for none) for the codes
  tab header.
- Readers (`supplier_inventory` stock-list reader and `proforma_invoice_reader.read_workbook`)
  return `letterhead`: the first non-empty text cell above the first header row. Preview /
  validate add `supplier_check: { letterhead, chosen_supplier_name, other_supplier_name |
  null }` and a `supplier_mismatch` warning when another active supplier's `supplier_name`
  (NFKC, case-folded) is a substring of the letterhead and the chosen one is not. Master-data
  names only, exact substring, deterministic.
- Verdict card: "N invoice blocks · L lines · U codes unknown" for proforma (stock list: "L
  rows · U codes unknown"), warnings listed under it. Confirm stays enabled.

### 3.8 Formats written down (S8)

`documentation/reference/SCM-UPLOAD-FORMATS.md`: stock list and proforma invoice (packing list
pointer), from the reader source: file types, active sheet only, header-row rule (stock list:
first row resolving `item_code`; proforma: a row resolving `item_code` + `qty` + `unit_price`),
alias table per column (seeded by migrations 311 and 375, `import_field_alias`), stacked
blocks, labelled block fields, date formats, totals rows, skip rules and how they are reported,
matching ladder rungs, currency rule, "supplier comes from the dialog". Offered for Outline.

### 3.9 The row lightbox matches the SPO document detail's design (S9)

Captain's markup, 3 Sep: `scm/components/PlanRowDialog.tsx` and
`scm/reorder/components/PlanRowDialogs.tsx` line tabs (`TabsList variant="line"`) and
`DataGrid` tables, matching `SPODocumentDetail.tsx`; every tab that lists a quantity gets a
footer TOTAL row, the 12-month history tab included. See UAC section J (AC-J1-AC-J4) for the
full contract; `DESIGN-LANGUAGE.md`'s `Tabs` row is amended to make line tabs the default
everywhere, dialogs included.

### 3.10 Captain's live-testing feedback batch, 3 Sep (S10)

Three frontend fixes found while the captain worked the lane live, onto this same PR. UAC
section K (AC-K1-AC-K3).

- `components/common/SearchableSelect.tsx`: cmdk's per-`CommandItem` `value` was
  `opt.searchText ?? label + description` - the identity cmdk highlights and tracks by, not
  the string `shouldFilter={false}` filters on (that is manual, in `visibleOptions`). Two
  options sharing a label collided on that identity, so hovering one highlighted every
  option with the same label. Fixed to `opt.value` (the id), with `keywords={[opt.label,
  opt.description ?? '']}` carrying the searchable text cmdk's own contract expects there.
  Separately, the popover this component renders did not scroll on a real wheel gesture when
  opened from inside a `Dialog`: Radix Dialog's own scroll lock (`react-remove-scroll`,
  wrapping the Overlay with `shards: [contentRef]`) only exempts the Dialog's OWN content
  subtree, and a `Popover` portalled to `<body>` sits outside it, so every wheel event over it
  is swallowed regardless of the popover's own scroll capacity. `react-remove-scroll`'s lock
  stack is last-mounted-wins, and Radix `Popover`'s `modal` mode wraps its OWN content in its
  own `RemoveScroll` instance (`@radix-ui/react-popover`), so making the `Popover` `modal`
  makes IT the active lock while open, letting its own list scroll - the same mechanism
  `Select`/`DropdownMenu` already use. No dialog-side change.

## 4. What is reused, and what is deliberately not built

- Reused: `RowActionsMenu`, `DetailActions`, `recordActions`, `useDeferredAction`,
  `useDeferredRowAction`, `deferredToast`, the pending-action registry, `Tabs`, `Collapsible`,
  the alias endpoints, the drill dialog, the two-step upload hook.
- Not built: a copy table for the statement (the rows are stamped in place with the plan id,
  one column per table, not a second table); a supplier-catalogue master; fuzzy supplier
  detection; a shared fold component (one consumer); a new column on `product_suppliers`.

## 5. Slices

| Slice | Scope | Phase 1 (FE mock) | Phase 2 (BE, tests first) | Blocks |
| --- | --- | --- | --- | --- |
| S1 | Actions set, kebab, deferred cancel, `disabledReason` | actions.tsx, grid, view, primitive | `loading_plan.cancel` registration + 409s, pytest | - |
| S2 | Tabs | view, sent tab component | - | S3 |
| S3 | Supplier codes tab: stay + Undo, remembered list | panel rewrite against mocked list | alias list endpoint shape, pytest | S4 |
| S5 | Fold no-demand rows | section | - | - |
| S6 | A plan owns its statement (stock list + PI) | dialog order, holding cell, drill blocks, codes tab per plan | 454, apply with plan id, build reads plan rows, label, unmatched/rematch by plan, pytest on the fixture | S7 |
| S7 | Statement label, letterhead warning, verdict counts | verdict card | label rules, reader letterhead, pytest | - |
| S4 | Match reaches master data | Suppliers tab "Their code" | link upsert, universe union, response field, pytest | - |
| S8 | Formats doc | - | doc | - |
| S9 | Row lightbox matches SPO document detail (line tabs, `DataGrid`, footer totals) | `PlanRowDialog.tsx`, `PlanRowDialogs.tsx`, `DESIGN-LANGUAGE.md` | - | - |

Order of execution in ONE lane, one coder at a time: S1, S2, S3, S5, S6, S7, S4, S8, S9.
Review (`/code-review`, then `emil-design-eng` Before/After/Why on S1-S3, S5) after S5 and
again at the end. One PR, or two (UI batch S1/S2/S3/S5, data batch S6/S7/S4/S8) if the diff
passes 2,500 lines.

## 6. Test fixture

`sorento_crm_backend/tests/fixtures/scm/2026-7-31_SORENTO_preload_list.xlsx` = a copy of the
captain's file (five blocks, 30 lines, JINBAICHUAN letterhead). Golden numbers for AC-F4 and
AC-G4 are read from it, not typed.

## 7. Settled on the markup round

1. Stack slot: a third slot, FE :3120 / BE :8120, for this lane.
2. `SCM-UPLOAD-FORMATS.md` goes to the repo AND the Outline user guide (S8).
3. The prod ROYAL MIRROR snapshot stays; with plan-owned statements it cannot reach a plan.

Approved 2 Sep. One finding surfaced while briefing S7, for the captain: AC-G3's exact-substring
rule will NOT warn on the captain's own file, because the master name is "CHAOZHOU JINBAICHUAN
SANITARY WARE CO., LTD" and the letterhead reads "CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY
CO.,LTD". Options when it comes up: (a) keep exact substring and accept the miss, (b) also
accept a supplier `supplier_code` or a stored "letterhead alias" on the supplier record (one
column, deterministic), (c) token overlap of 3+ words (still deterministic, wider). Not built
until ruled.
