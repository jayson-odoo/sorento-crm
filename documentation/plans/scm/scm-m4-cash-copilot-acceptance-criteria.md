# UAC - SCM M4: Cash Constraint + Co-Pilot Loop

> Given/When/Then contract for milestone M4. Parent umbrella: `scm-reorder-copilot-acceptance-criteria.md`.
> Depends on M0/M1/M2/M3. Governs: `PRINCIPLES.md`. **The deal-closer - the co-pilot loop.**

**Slug:** `scm-m4-cash-copilot` · **Domain:** scm · **Milestone:** M4 · **Status:** DRAFT (grilled, pre-code)

## Scope
Close the loop: rank recommendations under a cash budget, let the human Accept/Adjust/Reject, draft
POs from accepts, confirm POs into supply, and feed reject/adjust reasons back into policy suggestions.
LLM is used **only** to classify a free-text reason into a code (no number touched). Market advisory +
LLM explanation = M5.

## Locked decisions (from M4 grill)

| # | Decision |
|---|---|
| M4-D1 | **Cash ranking** = `Σ(weight·normalized_factor)` over urgency (low DoC / below-ROP depth; stockout=max), margin (`(list−cost)/list`), ABC, SO priority, committed-vs-forecast. Config in a separate **`scm.cash_ranking_policy`** (weights + default urgency+margin dominant); single active + per-run override. |
| M4-D2 | **rank_score frozen in the run; funded/deferred applied live at view-time** against a budget the user can slide - instant what-if, no re-run. Persisted back to the run. |
| M4-D3 | **Allocation** = greedy by rank, **skip an item that overflows remaining budget and continue** to the next that fits (MoQ is all-or-nothing). `funding_status = funded | deferred`. Deferred shown separately with **visible stockout risk (days-to-stockout)** - never dropped. |
| M4-D4 | **Accept → consolidated draft PO per supplier** (`purchase_order` status `draft_recommendation`, one PO/supplier, multiple lines). Rec status → `accepted`. Platform never transmits. |
| M4-D5 | **Draft POs are NOT `on_order`** - `on_order` counts open PO lines with status ≠ draft. Prevents the next run double-counting drafts as incoming supply. |
| M4-D6 | **PO list + bulk Confirm** (reuse shared DataGrid bulk-action component) flips `draft_recommendation → active`; only then does the PO count as `on_order`. `create-GR-from-PO` available from an active PO (stamps `qty_received`). |
| M4-D7 | **Adjust** = qty override + **supplier switch** (from M3 ranked alternatives → recomputes lead/qty), reason required. Writes `recommendation_override` (append-only, never mutates the recommendation), rec status → `adjusted`, flows into the draft PO with overridden values. |
| M4-D8 | **Reject** = rec status → `dismissed`, reason required → the feedback trigger. |
| M4-D9 | **Reason → LLM classify → suggested action.** Reason captured on **Adjust AND Reject**. LLM maps `reason_text → reason_code` (`override_reason` vocab) + confidence; **human can correct the code**. `reason_code → reason_action_map → suggested_action` (deterministic). |
| M4-D10 | **`trigger_type` per reason** = `immediate` (1 signal, e.g. "discontinued"→mark discontinued) or `pattern` (N same reason_code on same SKU/scope within window → e.g. "too much"→lower service_level). Threshold configurable. |
| M4-D11 | **Suggestions surface in a "Policy suggestions" panel** (+ inline nudge) with evidence; human clicks **Apply** → policy change applied by the human and **logged to audit**. **Engine never self-writes policy.** |
| M4-D12 | **No-orphan-tables (M4 share):** PO list (+confirm), `cash_ranking_policy`/`purchasing_budget`/`override_reason`/`reason_action_map` config CRUD, `recommendation_override` history - all on shared DataGrid/bulk-action/modal-CRUD components. |
| M4-D13 | **Bulk actions:** bulk Accept funded recs; bulk Confirm draft POs. Every destructive/detach action (reject, delete, unlink) = AlertDialog confirm first. |

## Acceptance criteria

### Cash ranking
- **AC-M4.1** GIVEN `Σ cash_impact > budget` WHEN ranked THEN the configurable weighted score orders recommendations; changing `cash_ranking_policy` weights re-orders with no code change (default urgency+margin).
- **AC-M4.2** GIVEN a budget WHEN allocated THEN greedy-by-rank funds whole items, **skips an overflowing item and continues** to the next that fits; funded/deferred set accordingly; Σ funded cash ≤ budget.
- **AC-M4.3** GIVEN the user slides the budget at view-time THEN funded/deferred recompute live from the frozen rank_score **without a new run**, and persist.
- **AC-M4.4** GIVEN deferred items WHEN shown THEN they appear separately with days-to-stockout risk; none are dropped.

### Decisions & PO
- **AC-M4.5** GIVEN Accept on recs for the same supplier WHEN applied THEN one consolidated draft PO (`draft_recommendation`) with multiple lines is created; rec → accepted.
- **AC-M4.6** GIVEN a draft PO WHEN the next `reorder_run` computes `on_order` THEN the draft is excluded; GIVEN the PO is confirmed (bulk or single) THEN status → active and it now counts as `on_order`.
- **AC-M4.7** GIVEN Adjust WHEN the user changes qty and/or switches supplier THEN qty/lead recompute off the chosen supplier, a `recommendation_override` row is written, the original recommendation is unchanged, and the draft PO reflects the override.
- **AC-M4.8** GIVEN Reject with a reason THEN rec → dismissed and the reason enters the feedback pipeline.
- **AC-M4.9** GIVEN bulk Accept funded / bulk Confirm draft POs THEN the shared bulk-action component performs them with a count-bearing confirm dialog.

### Feedback loop
- **AC-M4.10** GIVEN a free-text reason WHEN classified THEN the LLM returns a `reason_code` from the vocab + confidence; the user can override the code; a deterministic `suggested_action` is derived from `reason_action_map`.
- **AC-M4.11** GIVEN an `immediate`-type reason (1 signal) THEN a suggestion surfaces at once; GIVEN a `pattern`-type reason THEN it surfaces only after N same-code signals on the same SKU/scope within the window.
- **AC-M4.12** GIVEN a surfaced suggestion WHEN the user clicks Apply THEN the policy change is applied by the human and written to audit; **no engine self-write**; the recommendation/override rows are never mutated by the suggestion.
- **AC-M4.13** GIVEN the LLM classifier WHEN traced THEN it only reads/writes the reason_code - it touches **no quantity/ROP/SS/budget** field (LLM-boundary test).

### No-orphan-tables / conventions
- **AC-M4.14** GIVEN each M4 entity (PO, cash_ranking_policy, purchasing_budget, override_reason, reason_action_map, recommendation_override) THEN a frontend list/CRUD exists (DataGrid + modal + confirm-delete), no UUIDs shown, SearchableSelect, extractApiError, buildDataGridParams.
- **AC-M4.15 (verify)** Playwright: run → budget slider funds/defers → Accept (draft PO created) → PO list bulk Confirm (now on_order) → Adjust with supplier switch → Reject with reason → reason classified → Apply a policy suggestion (audited); 375px + 1280px, console clean.

## Tests (test-first - TDD)
- **pytest:** cash ranking (weights alter order), greedy skip-overflow allocation, live re-fund, draft-PO consolidation, on_order-excludes-draft / includes-active, override append-only, reason-classify (mock LLM) + immediate/pattern trigger, apply-suggestion audited, LLM-boundary (no numeric write), auth.
- **vitest:** results interactive states, budget slider, Accept/Adjust/Reject flows, PO list + bulk confirm, Policy-suggestions panel, config CRUD states.
- **playwright:** AC-M4.15.

## Deferred
LLM recommendation explanation prose + market advisory (M5); transfer netting + multi-echelon (later);
AutoCount PO transmission (never - hard rule).
