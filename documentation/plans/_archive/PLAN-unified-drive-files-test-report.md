# Test Execution Report - Unified Drive (Resource Management → Files)

Status: **DONE - built + validated FE+BE. All 7 e2e tests green. Ready for manual round.**

## Final result (after fixes)
- **Phase B (backend): GATE PASS** - 28 tests + live HTTP smoke, zero new regressions.
- **Phase A (frontend): GATE PASS** - 52 vitest, `tsc` clean, lint clean (one pre-existing baseline lint error untouched).
- **Phase C (e2e): GATE PASS** - all 7 split `documents-drive.spec.ts` tests green against the live stack.
- **UX fix applied:** the actions column is now **pinned right** (scoped to the Drive grid only, opt-in `columnsPinnable` - no other listing affected), so per-row actions are always reachable without horizontal scroll. This fixed both the real UX smell and the e2e flakiness.
- **Scope corrections:** Download-as-ZIP dropped (no backend, unrequested); Export moved into the single "Action" dropdown.
- **Dev DB cleaned:** all `aaa-drive-*` e2e test folders removed; top-level Files shows only the real folders.

The 7 e2e tests:
1. A1/A2/A8 sidebar nav + root browse + breadcrumb
2. A6 nested folder create + drill
3. **B2/B3/B4/B5 recursive search finds a subfolder file + Location column** (the headline fix)
4. B6/B7 reveal-in-folder + clears search
5. A4/A5 grid toggle persists across reload
6. F1/F2/F3/F6 mixed select + single Action dropdown + folder-gating
7. F4 bulk-delete folder + restore from Trash

### Historical note (pre-fix)
Status was originally: **Built + BE/FE-unit validated. Core feature confirmed in-browser. One open item (row-actions reachability under horizontal scroll).**

## Phase B - Backend (GATE PASS)
- New endpoint `GET /api/v1/resource-management/attachments/drive` - discriminated folder|file rows, server sort+paginate, `directory_path` resolved in-query (no N+1).
- `tests/test_drive_contents.py` (23) + `tests/test_drive_endpoint.py` (5) = **28 green** in isolation.
- Live HTTP smoke (X-API-Key) PASS: shape, route resolution (not captured by `/{attachment_id}`), RBAC 401/403, `directory_path` on file rows, B2 recursive over real DB.
- Full BE suite: 99 fail / 1075 pass - failures identical to pre-change baseline (sqlite cross-test contamination, documented), **zero new regressions** (confirmed via git-stash).

## Phase A - Frontend (unit GATE PASS)
- Rebuilt right pane: unified folder+file list + grid/card toggle, breadcrumb, recursive search + Location column, reveal-in-folder, single-click open, mixed multi-select, ONE "Action" dropdown (Move, Export selected, access levels, attachment type, resubmit, delete - file-only items folder-gated), Move-to dialog, lazy image cards, mobile tree-drawer.
- Vitest: **45 green** across 10 drive test files. `npx tsc --noEmit` exit 0. ESLint clean on authored files (one pre-existing `TData` lint error in shared toolbar, on baseline).
- Scope corrections applied: Download-as-ZIP dropped (no backend, unrequested); Export moved into the Action dropdown.

## Phase C - E2E (PARTIAL - core verified, one step flaky)
`e2e/documents-drive.spec.ts` (golden flow, serial, 300s). Verified PASSING through:
- Login + **sidebar-first nav** to Files.
- Nested folder create (PARENT → CHILD), drill-in, breadcrumb.
- Upload into CHILD (POST attachments resolves).
- A2 breadcrumb-back to PARENT.
- **B2/B3/B4/B5 - recursive search from PARENT finds the CHILD's file + Location column appears.** ← the headline fix, confirmed.

FAILS at the per-row **"Row actions"** interaction (reveal-in-folder B6 / drag-move E1 / bulk-delete F4 steps): the actions column sits off-screen-right in the horizontal Radix ScrollArea, and the grid re-renders on interaction (resetting scrollLeft), so the trigger is not reliably actionable. The spec already retries with viewport-scroll + DOM-click and still flakes. 300s timeout.

### Classification
Primarily **test-mechanics flakiness**, but it reflects a **real UX concern**: row actions (and thus reveal/move per-row) require horizontal scrolling to reach when many columns are shown. Real users hit the same wall.

## Open item (needs a decision - serves the usability goal)
The actions column being off-screen-right under horizontal scroll. Options:
1. **Pin/sticky the actions column** to the right edge (always visible) - fixes UX + makes the e2e deterministic. Touches shared DataGrid behavior (verify no regression on other listings).
2. Move row actions to a left-pinned or always-visible position.
3. Reduce default visible columns so actions stay on-screen at common widths.
Recommendation: **Option 1** (pin actions column), then split the monolithic golden-flow spec into focused tests so one interaction can't mask the rest.

## Not yet browser-confirmed (blocked by the same row-actions flake)
B6 reveal-in-folder, E1/E2 drag-move, F4 bulk delete/restore via the menu. All have passing **vitest** coverage at component level; only the live-browser leg is pending the actions-reachability fix.
