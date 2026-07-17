# SCM M4 Slice B — Test Report (decisions + PO draft/confirm/GR)

> **Revised 2026-07-16 (M4-D17..D23, slice-B UX grill).** Decisions are now STAGED — Accept/Adjust/
> Reject set status only; a new **Confirm decisions** step materialises the consolidated draft POs
> (`decision_service.confirm_decisions`, idempotent). Adjusted qty reflects in the grid; rank shows a
> clean 1..N; the "Apply budget" button is gone (live funding); sections are collapsible; the past-run
> banner is a slim text line. pytest reworked to the staged model — **16 pass**
> (`tests/scm/test_m4_decisions.py`, incl. `confirm_decisions` consolidation/idempotency/on-order +
> a confirm-decisions endpoint + auth). Full flow re-verified via Playwright-MCP on the BRW-IB run
> (81 buys): Adjust FT-B 768→100 (grid shows struck 768→100, cash RM168,192→RM21,900, badge Adjusted,
> NO PO) → Accept FT-03 → "2 decisions staged" bar → Confirm decisions → FT-B→PO-DRAFT-0006 /
> FT-03→PO-DRAFT-0007 (separate suppliers); re-select run → confirm bar cleared; console 0 errors.

Keyed to `scm-m4-cash-copilot-acceptance-criteria.md`. Suites: **pytest 13**
(`tests/scm/test_m4_decisions.py`), **vitest 71** (12 files under `app/(protected)/scm/**`;
full SCM vitest suite 213 green, no regressions), **playwright 1**
(`e2e/scm-m4-copilot.spec.ts` — written; authenticates + drives the flow on prod but times out
on the heavy 609-buy grid; the loop itself is Playwright-MCP-verified — see AC-M4.15).
Stack: FE :3000 (dev/HMR during build; prod for handoff), BE :8005, worker, live prod-copy DB.
Phase-3 reviewer verdict: **READY, no blockers**.

| AC | Verdict | Evidence |
|----|---------|----------|
| AC-M4.5 (draft-PO consolidation per supplier) | PASS | pytest: 2 recs same supplier → 1 draft, 2 lines; different suppliers → separate. Browser: accept 4 real recs → 3 consolidated drafts (one supplier got 2 recs). |
| AC-M4.6 (on_order excludes draft / includes active, both directions) | PASS | pytest: `draft_recommendation` absent from `on_order_v`; after bulk-confirm→active, present. Reviewer traced end-to-end clean (the #1 risk). |
| AC-M4.7 (adjust: recompute + append-only override, original unchanged) | PASS | pytest: qty override + supplier switch recompute off frozen inputs / product_suppliers (never client cost); every adjust adds a `recommendation_override` row; rec only touched at `.status`. |
| AC-M4.8 (reject → dismissed + reason) | PASS | pytest: rec→dismissed, reason_text stored (server-validated required). |
| AC-M4.9 (bulk accept funded / bulk confirm via shared bulk-action + count-confirm) | PASS | vitest + browser: unified `BulkActionsMenu` Actions dropdown, count-bearing confirm ("Accept N", "Confirm N drafts"); select-all-all-rows, action scoped to applicable subset, hidden when none apply. |
| AC-M4.14 (no-orphan: PO list/detail CRUD, DataGrid, no UUID, SearchableSelect, extractApiError, buildDataGridParams) | PASS | vitest: PO list (drafts+active, hyperlink, select-all, Create-GR per-row on active), PO detail (all sections + empty states); services use shared helpers; no UUID rendered. |
| AC-M4.15 (Playwright full loop, 375+1280, console clean) | PARTIAL (MCP-verified) | The full loop (accept → consolidated draft POs → confirm → renumber `PO-YYYY/MM-####` → create GR) is **verified end-to-end via Playwright-MCP on real data, console 0 errors**. The persisted spec `e2e/scm-m4-copilot.spec.ts` authenticates + drives the flow correctly but **times out (~4.2m > 240s budget) on the heavy real-data reorder grid (609-buy run)**. Follow-up: point the spec at a light run (e.g. a few-buy warehouse) or a seeded fixture so it completes in budget. Not a feature defect. |
| Numbering (M4-D6) | PASS | Confirm assigns via canonical `NumberingService` ("purchase_order") — `PO-YYYY/MM-####`, FOR UPDATE lock, no NaN/collision. Seed-counter offset = data artifact. |
| create-GR (M4-D6) | PASS | pytest + browser: creates `picking_headers` goods_received (`picking_status='posted'`, in the check-constraint set), stamps `qty_received`, rejects GR-from-draft, links via source_entity. |
| Auth (RBAC) | PASS | pytest: reads `scm.dashboard.view`, writes `scm.reorder.run`; denial covered. |

## Review fixes applied
- Confirm/create-GR now invalidate the on-order dashboard caches (net-position/rollups/products/
  warehouses/suppliers), not just the PO list — stale-on-order after confirm fixed.
- Accept-response contract doc corrected (`draft_po_id`).

## Deferred hardening (reviewer should-fix, low exposure — see PLAN "Slice B Phase-3 review follow-ups")
Draft-consolidation concurrency guard; re-accept-of-confirmed-PO line guard; fractional-qty GR
rounding; `override_supplier_id`→`_code` rename.
