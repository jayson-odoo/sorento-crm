# PLAN - SCM M4: Cash Constraint + Co-Pilot Loop

**Slug:** `scm-m4-cash-copilot` · **Milestone:** M4 · **UAC:** `scm-m4-cash-copilot-acceptance-criteria.md`
**Umbrella:** `PLAN-scm-reorder-copilot.md` · **Depends:** M0/M1/M2/M3 · **Status:** Building slice-by-slice (A→D)
**Type:** BE (cash stage + decisions + feedback) + interactive results/PO/config UI

## Reality check (2026-07-16, post-M3+policy-config build - de-risks the plan)
- `reorder_recommendation` ALREADY carries the M4 columns (M3 pre-provisioned): `rank_score`,
  `rank`, `funding_status`, `cash_impact`, `unit_cost`, `urgency_score`, `priority_score`,
  `status` (proposed|accepted|adjusted|dismissed). No column migration for these.
- `scm.on_order_v` ALREADY excludes drafts: `WHERE po.status IN ('active','received','partial','closed')`
  (migration 274) - M4-D5's most-dangerous bug (draft counted as supply) is already prevented.
  Draft POs use a status OUTSIDE that set (`draft_recommendation`).
- `purchase_orders`/`purchase_order_lines` (public, mig 273) + `purchasing_budget` (M0 stub) exist.
- LLM infra reusable: `ai_prompt_registry` / `ai_prompt_service` / `ai_prompt_seed` / `ai_trace`
  (add key `scm_override_reason_classifier`, schema-forced). Policy-suggestion Apply reuses the
  just-built `policy_service` to mutate `reorder_policy` (human-applied + audited).
- NEW tables only: `cash_ranking_policy`, `override_reason`, `reason_action_map`,
  `recommendation_override`.

## Locked decisions (user grill 2026-07-16)
- **M4-D14 - Margin gap = GRACEFUL DEGRADE.** Real data has cost on ~91 SKUs and the seed must NEVER
  write `list_price`. `rank_score = Σ(wᵢ·fᵢ) / Σ(wᵢ present)` - the margin factor is DROPPED (not
  zeroed) for SKUs with no cost, so it never dilutes the score; urgency (low days-of-cover / below-ROP
  depth) dominates, ABC + SO-priority + committed fill in. No fabricated cost/price. Ranking stays
  meaningful and honest on real data. Show which factors were present per rec (explainability).
- **M4-D15 - Build slice-by-slice, three-phase loop + checkpoint each:** A cash-stage + interactive
  results → B decisions + PO draft/confirm + create-GR → C LLM feedback loop → D config CRUD.
- **M4-D16 - Uncosted buys = separate "Needs cost" bucket, NOT funded/deferred.** A buy with no
  supplier cost (`cash_impact` null) cannot be cash-ranked. It goes to a THIRD section ("Needs cost")
 - un-rankable, still showing urgency / days-of-cover / order qty, with an "add supplier cost to
  cash-rank this" CTA. Funded/Deferred (and Σ funded ≤ budget) are computed over COSTED buys only.
  Rationale: real data is ~13,280 uncosted vs ~91 costed; funding uncosted "for free" would make the
  cash constraint meaningless and hide the cost-data gap. This bucket surfaces the gap as actionable.
  (Supersedes the prototype's "fund uncosted for free" default.)

## Slice-B UX revision (user grill 2026-07-16, post-handoff - supersedes parts of §3/§5)
- **M4-D17 - Decisions are STAGED; the PO is created at Confirm decisions, not on each
  Accept/Adjust.** Accept/Adjust/Reject only set `rec.status` (+ append override for adjust/reject).
  A new **Confirm decisions** action (`POST /scm/reorder-runs/{id}/confirm-decisions`,
  `decision_service.confirm_decisions` - idempotent reconciler) consolidates accepted+adjusted recs
  into one draft PO per supplier. Gives the planner an editable overview before any PO exists. The
  draft→active confirm (PO list, renumber) is unchanged downstream. Bulk-accept `po_count` is now 0
  (staged).
- **M4-D18 - Adjusted qty reflects in the results grid** (struck original → override, cash impact
  recomputed pro-rata), not only in the PO.
- **M4-D19 - Rank column shows a clean 1..N section position** (`display_rank`, assigned in
  `computeFunding` after each section's final sort), not the raw global rank; the true score stays in
  the explainability popover.
- **M4-D20 - Budget is live-only: the "Apply budget" button is removed** (funding recomputes on every
  input/slider change; no persistence step). Funding_status persistence is dropped for now.
- **M4-D21 - Funded / Deferred / Needs cost are collapsible** (all start expanded) and column-aligned
  (Needs cost gets a leading spacer + dash rank).
- **M4-D22 - Past-run banner is a slim info line** (no prominent "Back to latest" button; inline text
  link + history-panel selection return to latest).
- **M4-D23 - Run-time budget cap DEFERRED** (the Run-planning "Budget" field stays disabled). View-time
  slider is the M4 budget mechanism; a run-time cap changes the deterministic engine → its own slice/M5.
- **Pending follow-ups:** supplier-choice detail popup (score breakdown + ranked alternatives - needs
  M2 scorecard components surfaced); confirm the buy/disposition toggle (stat tiles) meets the "see
  dispositions" ask or add an inline affordance.

## Goal
Close the co-pilot loop - cash-ranked recommendations, human Accept/Adjust/Reject, draft→confirm PO
flow, and reason-driven policy suggestions. The deal-closer.

## 1. Schema
- **`scm.cash_ranking_policy`**: weight_urgency, weight_margin, weight_abc, weight_priority, weight_committed, is_active, note.
- **`scm.purchasing_budget`** (M0 stub → full): period_start/end, budget_amount, currency, scope_type (global|supplier|category), scope_ref, set_by.
- **`scm.override_reason`** (vocab), **`scm.reason_action_map`** (reason_code, suggested_action, target_policy_field, adjustment, trigger_type immediate|pattern, threshold_n, window_days).
- **`scm.recommendation_override`** (append-only): recommendation_id, original_qty, override_qty, override_supplier_id, reason_text, reason_code, reason_confidence, suggested_action, action_applied, overridden_by, overridden_at.
- **`reorder_recommendation`** (from M3) + `rank_score`, `funding_status`, `rank`.
- **`purchase_order`** status supports `draft_recommendation` | `active`; `on_order` view filters status ≠ draft.

## 2. Cash stage (deterministic; extends the M3 run)
- After qty, compute `rank_score` per recommendation from `cash_ranking_policy` (normalize each factor 0 - 1). **Freeze rank_score on the recommendation.**
- **Funding at view-time:** `GET /scm/reorder-runs/{id}/recommendations?budget=X` → greedy by rank, skip-overflow-continue, return funded/deferred + days-to-stockout for deferred. Budget slider calls this; **Apply budget** persists funding_status + the chosen budget to the run. No engine re-run.

## 3. Decisions + PO flow
- `POST /scm/recommendations/{id}/accept` → upsert a **draft PO per supplier** (consolidate lines), rec→accepted. Bulk accept funded.
- `POST /scm/recommendations/{id}/adjust` → body {override_qty, override_supplier_id?, reason_text}; recompute lead/qty off chosen supplier; write `recommendation_override`; rec→adjusted; reflect in draft PO.
- `POST /scm/recommendations/{id}/reject` → {reason_text}; rec→dismissed; enqueue feedback.
- **PO list** (`purchase_order`): DataGrid + **bulk Confirm** (draft→active) via shared bulk-action component; single confirm too. `create-GR-from-PO` action on active PO (stamps qty_received; GR = `picking_headers` goods_received). Active PO → counts as `on_order` (view already filters).

## 4. Feedback pipeline (LLM classify → deterministic action)
- On adjust/reject, enqueue a classify task: LLM (`ai_prompt` key `scm_override_reason_classifier`, schema-forced `{reason_code, confidence}` over `override_reason`) → store on the override. Human-correct via UI.
- Resolve `reason_action_map[reason_code]`: `immediate` → create a pending suggestion now; `pattern` → increment a counter per (reason_code, scope); at `threshold_n` within `window_days` → create suggestion.
- **Policy suggestions panel:** list pending suggestions + evidence ("cut SKU X 3× - reason: too much → lower service_level 0.95→0.90?"). **Apply** → mutate the target `reorder_policy` field + write an **audit** entry. Engine never self-writes.
- Reuse AI infra: prompt registry, governance/trace, `feedback_no_overfit_llm_nlp` (semantic, not keyword).

## 5. FE (Phase 1 prototype → Phase 2 wire, test-first)
- **Recommendation results** (from M3, now interactive): budget slider (live fund/defer), funded vs deferred sections, per-row Accept/Adjust/Reject, bulk Accept funded, supplier + alternatives popover, confidence badge, days-to-stockout on deferred.
- **Adjust modal:** qty + supplier switch (`SearchableSelect` over alternatives) + reason textarea → shows classified code (editable) → suggested action.
- **Reject dialog:** reason (AlertDialog confirm) → classified code.
- **PO list:** DataGrid + bulk Confirm + create-GR action (confirm dialogs, count-bearing copy).
- **Config CRUD:** cash_ranking_policy, purchasing_budget, override_reason, reason_action_map (modals).
- **Policy suggestions panel** + override history (read-only).
- Reuse DataGrid/bulk-action/modal-CRUD/`ConfirmDeleteDialog`/SearchableSelect; mobile-scrollable modals.

## 6. Tests (test-first / TDD)
- **pytest:** ranking weights alter order (AC-M4.1); greedy skip-overflow (AC-M4.2); live re-fund (AC-M4.3); draft-PO consolidation (AC-M4.5); on_order excludes draft / includes active (AC-M4.6); adjust override append-only + supplier recompute (AC-M4.7); reject (AC-M4.8); reason-classify with **mocked LLM** + immediate/pattern trigger (AC-M4.10/4.11); apply-suggestion audited + no self-write (AC-M4.12); **LLM-boundary** no numeric write (AC-M4.13); auth.
- **vitest:** interactive results, budget slider, decision flows, PO bulk confirm, suggestions panel, config CRUD states.
- **playwright:** AC-M4.15 full loop.

## Slice B - Phase-3 review follow-ups (deferred hardening; reviewer verdict READY, no blockers)
Fixed at review time: confirm/create-GR now invalidate the on-order-bearing dashboard caches
(net-position/rollups/products/warehouses/suppliers), not just the PO list; accept-response doc
drift (`draft_po_id`) corrected. Deferred (low-exposure, out-of-scope-ish for Slice B):
1. **Draft consolidation concurrency** - `_draft_po_for_supplier` does SELECT-then-INSERT with no
   lock / partial-unique index on `(supplier_id) WHERE status='draft_recommendation'`. Two concurrent
   accepts for the same supplier (two tabs / rapid double-click) could create two drafts. `bulk_accept`
   is sequential so the main path is safe. Hardening: partial unique index + ON CONFLICT / advisory lock.
2. **Re-accept/adjust of a rec already in a CONFIRMED (active) PO** - `_remove_rec_line` filters
   `status='draft_recommendation'`, so a line already in an active PO isn't removed; a new draft line is
   created and the UI points at the new draft. Reachable because `bulk_confirm` leaves `rec.status='accepted'`.
   Hardening: guard accept/adjust when the rec's PO is already active.
3. Nits: GR PickingLine `quantity_picked` is `int(round())` vs the PO line's `Numeric(15,4)` (fractional-qty
   mismatch, harmless for whole-unit reorder qty); `AdjustRequest.override_supplier_id` carries a supplier
   CODE not a UUID (rename to `_code` to remove the foot-gun).

## 7. Risks
- **Draft-PO / on_order** - the single most dangerous bug (draft counted as supply → under-order). Explicit test both directions (AC-M4.6).
- **LLM classifier reliability** - low-confidence classification must be human-correctable + never block the decision; the reason_text is always stored raw.
- **Pattern counter** - scope + window must be well-defined so suggestions don't spam; threshold configurable; dedupe pending suggestions.
- **Budget slider persistence** - funding is view-time but Apply must persist deterministically so a shared run doesn't show divergent funded sets.
- **No-overfit** - classifier is generalized NLP over the vocab; test with paraphrases, not an allowlist.
