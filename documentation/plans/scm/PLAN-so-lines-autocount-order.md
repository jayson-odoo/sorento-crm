# PLAN: Sales order lines in AutoCount order, with a Source column and a Plan CTA

Status: built, in review (21 Sep 2026)
Domain: scm
UAC: `so-lines-autocount-order-acceptance-criteria.md`
Lane: `feat/so-lines-autocount-order` (one branch, one PR)

## 1. Journey

A planner opens a sales order in Sorento with AutoCount open beside it. Today the Lines tab
orders lines by open-first, then delivery date, then product code, so line 7 in AutoCount can
sit first in Sorento and the two screens cannot be read together. The ask (owner, 21 Sep):

1. Lines show AutoCount's line number in the leftmost column and sort by it, numerically
   (1, 2, ... 10, 11, 12), by default.
2. Lines carry a Source column: AutoCount, Order inquiry, Upload, Absorbed history, Manual.
3. The record header's primary CTA becomes **Plan** (the same board the list's "Plan
   selected" opens); **Edit** moves into the gear dropdown beside Delete.
4. Fulfilment planning (board line numbers, order inquiry sheet numbering) names a line by
   the same number AutoCount does.

## 2. Measured (prod copy `sorento_ai_automation_0918_1900`, 21 Sep)

| Fact | Value |
| --- | --- |
| `sales_order_lines` line-sequence column | none (`app/models/order.py:476-528`) |
| AutoCount `Seq` on the wire | sent as `line_number` on every SO line (FoundryX `presets.py` `PresetField("Seq", "line_number")`, on their `origin/main`), read into `values["line_number"]` at `document_ingest_service.py:1210`, then popped at :1314 (by-ref update), :1356 (create), :1453 (adopt claim) |
| Line `source_system` counts | `autocount` 611,532; `scm_so_history` 24,022; NULL 11,137 (10,960 under `scm_upload` headers, 177 under `autocount` headers); `scm_order_inquiry` 1,763 |
| Header `source_system` counts | `autocount` 150,286; `scm_upload` 1,630; `scm_so_history` 868 |
| Header source label for `autocount` | falls through to `"manual"` (`sales_order_service.py:72-80`), so 150,286 AutoCount orders print **Manual** on the list and detail, and the Manual filter selects them. Defect, fixed in the same seam. |
| Current SO line order | `_line_sort_key` `sales_order_service.py:134-147`: open first, required_date (nulls last), product code |
| Board line numbers | derived per order by (required_date, item_code, line id) `project_fulfilment_board_service.py:2109-2144`; mirror `line_no` wins when every contributing line is mirrored |
| Mirror numbering | `project_so_adoption_service.py:_mirror` sorts by the same rule; `mirror_missing_lines` appends (`_next_line_no`), never renumbers |
| Detail header actions | `DetailActionsMenu` with `useSalesOrderActions` (Delete only) + primary Edit (`SalesOrderDetail.tsx:1425-1445`) |
| List "Plan selected" | pushes `/project-sales/fulfilment-planning?orders=<so_numbers>`, gated `projects.projects.view`, max 50 |
| Alembic head on `origin/main` | re-parent with `./scripts/alembic-reparent.sh` at PR time |

## 3. Design (simplest thing that works)

### 3.1 One column: `sales_order_lines.line_no INTEGER NULL`

AutoCount's `Seq`, kept as it arrives. NULL means the line never came from AutoCount (order
inquiry, upload, history, manual) or arrived before this column existed. No index: ordering is
done in Python per order, never in SQL across orders. Purchase order lines get nothing:
no screen asked for their order (trigger: a PO screen asks).

Ingest (`document_ingest_service.py`): the three `values.pop("line_number")` sites become
`values["line_no"] = values.pop("line_number")` for the sales-order spec only; the PO spec
keeps popping. An absent `line_number` on a re-push leaves the stored value alone (the
`absent_vs_null` rule the V5 fields already follow at :1211-1224); an explicit `null` clears.
The D11 adoption tie-break keeps reading `line_number` before it is renamed.

### 3.2 Serve it and sort by it

`serialize()` adds two line fields, declared on the response schema (`scm_orders.py:120`):

- `line_no: Optional[int]`
- `source: str` - the line's own `source_system` through one label function; NULL is
  "manual" (R2), never inherited from the header: the line itself carries no provenance.

`_line_sort_key` becomes: `line_no` ascending (nulls last), then today's key for the
nulls. Open-first is dropped: AutoCount shows every line in `Seq` order whatever its status,
and the ask is "presented the same way". Numeric, never string, so 10 follows 9.

One label function for header and line, `_source_label`, gains `autocount -> "autocount"`
and `_SOURCE_SYSTEMS` gains `"autocount": ("autocount",)`, so the list filter can select
AutoCount orders and Manual stops claiming them. FE `SOURCE_LABELS` + `SOURCE_FILTER_OPTIONS`
gain `autocount: 'AutoCount'`.

### 3.3 Lines tab (FE, `SalesOrderDetail.tsx`)

- New first column **No.** (`line_no`, size 64, right-aligned, `-` when null, numeric sort
  via `sortingFn: 'basic'`). Default table order = server order (already the case).
- New column **Source** after Status (pill via `Badge`, the label map above).
- Both in the default visible set. Column-config: coder checks how a saved column order
  treats an unknown key; the new columns must appear for a user with a saved order, No.
  leftmost.
- Edit session: No. is read-only (a value, never an input); a session-local new line shows
  `-`.

### 3.4 Header actions (FE)

- Primary slot: **Plan**, `Link` to `/project-sales/fulfilment-planning?orders=<so_number>`,
  shown only with `projects.projects.view` (same gate as the list). Label "Plan", not "Plan
  selected": one order is on the page.
- Gear dropdown (`useSalesOrderActions`): **Edit** (`SquarePen`, `run: beginEdit`) above
  Delete. The hook takes an `onEdit` option so the list surface (which has no edit session)
  passes none and shows no Edit item.
- Edit session header (Save / Cancel) unchanged. The post-save "Plan" link with the batch
  stays.

### 3.5 Fulfilment planning names the same line (S3)

- `FulfilmentBoardService._line_numbers`: when every contributing line of an order carries
  `line_no` and they are distinct, those numbers win over the derived ones. Mirror numbers
  still win over both when every line is mirrored (they are the confirm endpoint's address).
- `ProjectSoAdoptionService._mirror`: sorts by `line_no` (nulls last) before today's key, so
  a fresh adoption numbers the mirror 1..n in AutoCount order.
- Existing mirrors keep their numbers: `line_no` is the address drafts and confirmations
  use (`project_so.py:1282-1292`), so renumbering would detach them. A later Re-sync that
  renumbers is a separate ask (trigger: owner says an already-adopted order must match).
- Board list view order (`fulfilmentBoard.ts:orderByProductRows`) stays product-first: that
  is the grid's axis, and the toggle depends on it. `line_no` remains its last tiebreak.
  Superseded for the LIST view by S4 below (owner ruling, 21 Sep) - `orderByProductRows`
  and this rule stay exactly as written for the GRID.
- S4 (owner, 21 Sep): the board list view sorts by sales order then AutoCount line number;
  the grid axis stays product-first, so the grid/list toggle is no longer position-aligned.

### 3.6 Backfill

Existing AutoCount lines have NULL until FoundryX re-pushes. `source_ref` (DtlKey) upserts
by ref, so a full re-push writes `line_no` onto the same rows with nothing else changing.
Owner asks the FoundryX peer for a re-push of all sales orders (their #68 "repush widening"
exists). Until then such lines sort by today's rule and print `-`.

## 4. Rejected

- **Derive the number locally** (position by created_at): wrong whenever a line was inserted
  mid-order in AutoCount; the whole ask is AutoCount's own number.
- **Backfill by a Sorento pull**: SO/PO stay on push (19 Sep ruling); a re-push is one
  request.
- **Renumber existing mirrors**: breaks draft/confirm addressing (3.5).
- **PO lines too**: no consumer.

## 5. Slices and tests

Phase 1 (FE against mocks): S2 columns + header, vitest fixtures carry `line_no` + `source`.
Phase 2 (tester red first, then one coder, kept alive):

- **S1 BE**: migration; ingest keeps `line_no` on create / by-ref update / adopt claim,
  absent leaves it, null clears, PO spec unchanged; `serialize` fields + order (1..12
  numeric, nulls after, fallback among nulls); response schema pins both fields; source
  labels incl. `autocount`; list filter `source=autocount` / `manual` split.
- **S2 FE**: No. leftmost + numeric sort; Source pill; column-config with a saved order;
  Plan primary with href + permission gate; Edit in gear; Delete still there; edit session
  header unchanged; list filter option.
- **S3 BE**: `_line_numbers` prefers `line_no`; mirror still wins; `_mirror` orders by
  `line_no`; `mirror_missing_lines` appends without renumbering.

Phase 3: reviewer + browser pass (SO detail via sidebar, 1280 + 375, an AutoCount order on
the lane DB with `line_no` set by SQL for the evidence run) once per lane. No guide step (owner, 21 Sep).

## 6. Rulings (owner, 21 Sep 2026, on the lavish page)

R1. Pure AutoCount order; open-first dropped.
R2. A line with NULL `source_system` shows **Manual** (not the header's source).
R3. Header CTA label "Plan".
R4. FoundryX full re-push for the backfill: owner asks the peer (outside this lane).
R5. S3 ships in this lane.
R6. Board list view: sales order then AutoCount No. (option 2 of 3; grid unchanged).
