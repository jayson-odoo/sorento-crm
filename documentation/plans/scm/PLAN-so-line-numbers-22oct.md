# PLAN: Fulfilment planning names SO line numbers, not internal line numbers (SO-LINE-NUMBERS, 22 Oct 2026)

Status: built, PR #1831; review round 1 (NOT READY, 2 must-fix) fixed in round 2, re-review
pending; hand test filed (Track: small fix - no migration, no auth/RBAC change, no new ingest
surface; breadth past ~300 lines from ~40 one-expression seams plus tests).
Lane: SO-LINE-NUMBERS, branch `crew/so-line-numbers`, base origin/main 3c2199d48f.
UAC: `so-line-numbers-22oct-acceptance-criteria.md` (alongside).
Plan created: 2026-10-22T13:20:00Z

## Ruling

Owner OK, 22 Oct ~21:10 MYT. Every "line N" a user reads in fulfilment planning (dialog
titles, trail / order-back notes, decision reasons, exports) names the SO line number the
customer's sales order carries (the AutoCount line, `SalesOrderLine.line_no`), never the
planning order's own internal `ProjectSalesOrderLine.line_no`. One helper per side.

## Diagnosis (dev copy `sorento_cagent_stack`, read-only)

SO401624 on the dev copy: internal 11 = SO line 224 (SRTWB242), internal 9 = SO line 304
(SRTSA-SS). Query: `projects.sales_order_lines pl JOIN sales_order_lines cl ON
cl.id = pl.core_sales_order_line_id`.

The two owner reports:

1. Borrow dialog title `Borrow for line 11` - `BorrowAddDialog.tsx:183` prints its `lineNo`
   prop, which the caller fills with the internal number.
2. Order-back note `lent 1 to SO401624 line 9` - `project_supply_service.py:8179` (and its
   siblings `:7772`, `:8253`, `:8308`) format `line.line_no` of the project line.

Full inventory: see "Seams" (filled from the sweep).

## Architecture

- **Layer.** Display only. The number a user reads is computed where the text is built: BE for
  notes / reasons / errors, FE for dialog titles and toasts. No stored identifier changes.
- **Shared mechanism.** BE: `display_line_nos(db, mirror_ids)` (`project_line_split_service.py:1507`,
  batch, coalesce core over mirror) plus a pure `so_line_no(core_no, mirror_no)` beside it for
  sites that already hold the core row; `LineFacts.line_no` (`:272`) is the same rule. FE:
  `soLineNoText` / `soLineLabel` (`_shared/lib/fulfilmentBoard.ts:1875,1889`).
- **Fixed at the source, not per screen.** `donor_line_no` is display-only
  (`planning_change_service.py:2811`) and filled with the internal number at its three sources
  (`project_supply_service.py:4140,4297,4616`); filling it with the SO number fixes every
  downstream reader (notes `:7095,:8160`, board `project_fulfilment_board_service.py:3788`,
  ladder reason `scm/front_planning_engine.py:957`, FE donor text) in one place.
- **Payload rule.** An existing `line_no` field keeps its meaning (it is a match key in places,
  e.g. `FulfilmentBoardPanel.tsx:3258`); where the FE has only `line_no`, the BE adds
  `so_line_no` beside it and the FE renders through `soLineNoText`.
- **Special cases removed.** The wrong comment at `project_supply_service.py:7090` ("the core
  line carries no line number") goes.

## Seams

BE text built from the internal number:
- `project_supply_service.py:7772` Borrowed by ... line, `:8179` order-back to ... line, `:8253`
  group pile lines, `:8308` location order-back line, `:1368/:1374` cancel errors.
- donor sources `:4140`, `:4297` (`DemandLine.core_line_no`, `scm/supply_assignment.py:285`),
  `:4495/:4616` (query already joins the core line).
- `project_fulfilment_board_service.py:4482` `(line {taker.line_no})` (`taker.so_line_no` exists).
- `api/v1/projects/fulfilment_planning.py:1183` superseded reason; `:865` simulate errors payload.
- `planning_change_service.py:2297` row build, `:2459` refusal `so_line_no`, `:2482` `row_out`,
  `:3286`, `:3459`, `:3485`, `:4398` texts.
- `planning_history_service.py:171-175,254,264,344` and `project_order_inquiry_service.py:1300-1318`
  (fill `so_line_no` with the internal number today).
- `stock_transfer_service.py:508` (`so_line_no` filled with the internal number).
- echo payloads: `project_supply_service.py:1390` cancel, `:5523` duplicate refusal, `:7535`
  `lines_confirmed`, `:10275` `_pile_book`; `SupplyLine` schema (`schemas/project_supply.py:206`)
  gets `so_line_no`.

FE text built from the internal number (under `app/(protected)/project-sales/`):
- `BoardLineDecisionPanel.tsx:1334,1348` and `SupplyLineCard.tsx:436` dialog `lineNo`.
- `BorrowAddDialog.tsx:483`, `BoardCellBreakdownDialog.tsx:1654,1663`, `SupplyLineCard.tsx:586`
  donor text (fixed by the BE source; no FE change unless it formats).
- `BoardDecideControl.tsx:313`, `FulfilmentBoardPanel.tsx:1975` (+ `:3258` parse, which moves to
  an explicit `line_no` on the posted-line entry), `:3125`, `:3150`, `:3165`, `:3670`.
- `_shared/lib/unpostableNotices.ts:58`, `_shared/lib/supplyComposition.ts:326`,
  `SupplyCompositionSection.tsx:139`, `SupplyLineCard.tsx:126,470`, `PileQueueDialog.tsx:107`,
  `BoardChangeTable.tsx:110,364` via `boardChangeAnnotations.ts:409`.
- aria-labels `BoardVerdictActions.tsx:70`, `BoardCellBreakdownDialog.tsx:1020`,
  `SupplyLineCard.tsx:256,291,308,369`.

Already right (no change): handover email `project_order_inquiry_service.py:4502`, line-split
notes, `project_supply_service.py:3711`, `PlanningHistorySheet.tsx` (reads `so_line_no`; its BE
fill is the bug).

Left alone on purpose: the reconciliation sheet (`FulfilmentPlanningSheet.tsx:96,160`,
`project_supply_service.py:9155`) reconciles mirror lines to core lines and may run before a
core link exists; its numbering is the planning order's own (UNVERIFIED as a ruling; flagged in
the PR).

## Size

Breadth, not depth: ~40 one-expression seams across BE and FE. Expected diff may pass ~300
lines with tests; no migration, no auth, no new behaviour, so it stays the small fix track (the
brief sized it S) and the PR says so.

## Tests (red first)

- pytest: order-back notes and `Borrowed by` reason name SO numbers where core and mirror
  numbers differ; donor candidate `donor_line_no` is the SO number; planning history /
  change-row / transfers `so_line_no` is the SO number; fallback to mirror without a core.
- vitest: Borrow / Reserve dialog titles from `so_line_no`; Decide toast and posted-line label
  use the SO number while the held-back filter still matches on `line_no`; line blockers.

## Out of scope

Keys, html ids, sort orders and anything else a user never reads keep the internal number.
Notes already written to the DB are history and are not rewritten.

## Review round 1 (reviewer on 8f2a6746c5) and what round 2 did

- Must-fix: the board Decide/Amend seeders (`boardAmend.ts` `draftFromSources` / `frozenDraft`)
  and the FE-built held-back failing line (`FulfilmentBoardPanel.tsx`) carried no `so_line_no`.
  Both fixed.
- Should-fix: `row_out` ran one `display_line_nos` per row; `get_batch` now reads the batch's
  numbers once. A wire test reads `so_line_no` back through the batch endpoint, and every new
  field's schema declaration is pinned.
- Found in round 2: the withdrawn-line echo (`fulfilment_planning.py` `_withdrawn_entries`)
  sent no `so_line_no`; it now does, like `lines_confirmed`. Exact echo dicts in
  `test_so_cancel_line.py`, `test_confirm_echoes_lines_confirmed.py` and
  `test_confirm_all_preview.py` extended for the new field.
- Pile queue: a core line with no planning mirror keeps "Not planned"; a planned row shows and
  sorts by its SO number.
- Left as is (nits): the history and change lists keep their existing internal-number order;
  the inline `so_line_no ?? line_no` spots that predate this lane stay.

