'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { computeFundingM8, defaultBudgetFor, type M8FundingResult } from '../lib/reorderCashAllocation';
import { applyBudget } from '../services/reorderRunService';
import { m8CashImpact, recToPlanRow, type M8PlanRow, type M8ProposalLine } from '../lib/planRow';
import { useBuyRecommendationsForCash } from './useReorderRun';
import { useCashBudget } from './useCashBudget';
import { useDecisionMutations, useRecommendationDecisions } from './useDecisions';
import type { M8RowDecision } from '../components/CashResultsGrid';
import type { ReorderRecommendation } from '../types/reorder.types';
import type { ActionProposalLine } from '../types/explainer.types';

/** A pending inline edit (qty + supplier swap) applied on top of the frozen rec. */
interface LocalEdit {
  order_qty: number;
  supplier_code: string;
}

/** Shared empty set - passed as the greedy's `rejects` so section membership never
 *  depends on decisions (rejects only affect `committed`, computed in the hook). */
const EMPTY_SET: ReadonlySet<string> = new Set<string>();

/**
 * SCM M8 plan state - REAL backend (Phase 2). Loads the run's buy recommendations
 * + recorded decisions, adapts them onto the M8 plan grid rows, and owns the same
 * interactive model the prototype had (budget what-if, pins, drag-to-defer, inline
 * edits) - but every decision now hits the server:
 *
 *   • Accept / Fund  → POST /recommendations/{id}/accept   (pins the row)
 *   • Reject         → POST /recommendations/{id}/reject
 *   • Inline edit    → POST /recommendations/{id}/adjust    (supplier CODE)
 *   • Market bump    → POST /recommendations/{id}/adjust    (new qty)
 *   • Confirm        → PUT  /reorder-runs/{id}/budget  then  /confirm-decisions
 *
 * The budget split recomputes LIVE client-side via `computeFundingM8` (mirrors the
 * server allocator); the chosen budget is persisted on Confirm. Pins/rejects are
 * SEEDED from the decision overlay when a run loads, then driven by user actions.
 */
export function useReorderPlan(runId: string | null, enabled: boolean) {
  const recsQuery = useBuyRecommendationsForCash(runId, enabled);
  const decisions = useRecommendationDecisions(runId, enabled);
  const mutations = useDecisionMutations(runId);

  const recs = useMemo<ReorderRecommendation[]>(() => recsQuery.data ?? [], [recsQuery.data]);
  // Standing figure, not a property of this run: the same limit constrains every plan.
  const cashBudget = useCashBudget(enabled);

  const [budget, setBudget] = useState(0);
  const [pins, setPins] = useState<Set<string>>(() => new Set());
  const [rejects, setRejects] = useState<Set<string>>(() => new Set());
  const [forcedOver, setForcedOver] = useState<Set<string>>(() => new Set());
  const [editedIds, setEditedIds] = useState<Set<string>>(() => new Set());
  const [localEdits, setLocalEdits] = useState<Record<string, LocalEdit>>({});
  // Sticky Within-budget membership (M8-F). Section = STATE, not a live derivation, so
  // a DRAG moves exactly one row (no other row reshuffles). The greedy re-splits ONLY
  // when the budget value changes (respecting pins/drags); a drag or a decision never
  // re-runs it. Seeded from the initial greedy once the run loads.
  //
  // `null` means NOT SHAPED YET - no seed has landed and the user has dragged nothing - and
  // is deliberately distinct from an empty set, which means "the greedy funded nothing at
  // this budget". Conflating the two is how the screen came to read `Within budget 0` and
  // `RM 5,923,000 free` at the same time: every input needed to fund 230 lines was on
  // screen, membership state was empty for an unrelated reason, and the table blamed the
  // budget. While it is null the view DERIVES the split, so that state cannot be reached.
  const [withinIds, setWithinIds] = useState<Set<string> | null>(null);

  // Adapt recs → grid rows, applying any pending inline edit (qty + supplier swap).
  const rows = useMemo<M8PlanRow[]>(() => {
    return recs.map((rec) => {
      const base = recToPlanRow(rec);
      const edit = localEdits[rec.id];
      if (!edit) return base;
      const opt = base.alternatives.find((o) => o.value === edit.supplier_code);
      return {
        ...base,
        order_qty: edit.order_qty,
        unit_cost: opt ? opt.unit_cost : base.unit_cost,
        supplier: opt
          ? { code: opt.value, name: opt.label, unit_cost: opt.unit_cost, lead_time_days: opt.lead_time_days }
          : base.supplier,
      };
    });
  }, [recs, localEdits]);

  // Seed ONCE per run: budget (≈60% of costed total so the funded boundary lands
  // mid-list), pins/rejects/edits from the recorded decision overlay. Section
  // membership is DERIVED live (below) from budget + pins + drag - it is not stored,
  // so a budget change always re-splits and a decision never re-sections.
  const seededFor = useRef<string | null>(null);
  const lastGreedyBudget = useRef<number | null>(null);
  useEffect(() => {
    // Only seed once the decisions query has actually resolved for this run - a
    // disabled query (non-buy view) reports isFetched=false, so we don't seed empty.
    // Wait for the budget answer too, or the plan seeds itself against a guess and then
    // jumps when the real figure lands.
    if (!runId || recs.length === 0 || !decisions.isFetched || !cashBudget.isFetched) return;
    if (seededFor.current === runId) return;
    seededFor.current = runId;
    const nextPins = new Set<string>();
    const nextRejects = new Set<string>();
    const nextEdited = new Set<string>();
    const nextEdits: Record<string, LocalEdit> = {};
    for (const d of Object.values(decisions.byId)) {
      if (d.status === 'accepted' || d.status === 'adjusted') nextPins.add(d.recommendation_id);
      if (d.status === 'dismissed') nextRejects.add(d.recommendation_id);
      if (d.status === 'adjusted' && d.override_qty != null) {
        nextEdited.add(d.recommendation_id);
        nextEdits[d.recommendation_id] = {
          order_qty: d.override_qty,
          supplier_code: d.override_supplier_code ?? '',
        };
      }
    }
    // The COMPANY's budget when one is set; otherwise the plan whole. Never a guess.
    const seededBudget = defaultBudgetFor(recs, cashBudget.data?.budget_amount ?? null);
    setPins(nextPins);
    setRejects(nextRejects);
    setEditedIds(nextEdited);
    setLocalEdits(nextEdits);
    setForcedOver(new Set());
    setBudget(seededBudget);
    // Seed the sticky split from the initial greedy at the seeded budget, honouring the
    // seeded pins (adjusted/accepted lines force-in). Rejects are NOT passed - a reject
    // never changes a row's section.
    const seedRows = recs.map((rec) => {
      const base = recToPlanRow(rec);
      const edit = nextEdits[rec.id];
      if (!edit) return base;
      const opt = base.alternatives.find((o) => o.value === edit.supplier_code);
      return { ...base, order_qty: edit.order_qty, unit_cost: opt ? opt.unit_cost : base.unit_cost };
    });
    const split = computeFundingM8(seedRows, seededBudget, {
      pins: nextPins,
      rejects: EMPTY_SET,
      forcedOver: EMPTY_SET,
    });
    setWithinIds(new Set(split.within.map((r) => r.id)));
    lastGreedyBudget.current = seededBudget;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, recs, decisions.isFetched, cashBudget.data?.budget_amount]);

  // Re-run the greedy split ONLY when the budget value actually changes (M8-F): a drag
  // or a decision leaves `lastGreedyBudget` equal to `budget`, so this no-ops and the
  // sticky membership is preserved. A real budget change re-splits honouring current
  // pins (force-in) and forcedOver (force-out) so manual drags survive the re-split.
  useEffect(() => {
    if (seededFor.current !== runId || rows.length === 0) return;
    if (lastGreedyBudget.current === budget && withinIds !== null) return;
    lastGreedyBudget.current = budget;
    const split = computeFundingM8(rows, budget, { pins, rejects: EMPTY_SET, forcedOver });
    setWithinIds(new Set(split.within.map((r) => r.id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [budget, rows, runId, withinIds]);

  // Reset the seed guards when the run changes so a run switch re-seeds cleanly.
  useEffect(() => {
    seededFor.current = null;
    lastGreedyBudget.current = null;
    // Back to unshaped, NOT to an empty section: the next render derives the split rather
    // than claiming nothing is affordable.
    setWithinIds(null);
  }, [runId]);

  // Funding VIEW derived from the STICKY membership (not a fresh greedy) so drags don't
  // reshuffle other rows. Within/over read straight off `withinIds`; committed excludes
  // any rejected line's cash (it stays in its section but is not bought); free can go
  // negative when a drag-up overspends. Uncosted rows are always the needs-cost banner.
  const funding = useMemo<M8FundingResult<M8PlanRow>>(() => {
    const needsCost = rows.filter((r) => r.unit_cost === null);
    const costed = rows.filter((r) => r.unit_cost !== null);
    // Unshaped membership derives from the budget instead of reading as "nothing funded".
    const membership =
      withinIds ??
      new Set(
        computeFundingM8(rows, budget, { pins, rejects: EMPTY_SET, forcedOver }).within.map(
          (r) => r.id,
        ),
      );
    const within = costed.filter((r) => membership.has(r.id)).sort((a, b) => a.rank - b.rank);
    const over = costed.filter((r) => !membership.has(r.id)).sort((a, b) => a.rank - b.rank);
    let committed = 0;
    for (const r of within) {
      if (!rejects.has(r.id)) committed += m8CashImpact(r) ?? 0;
    }
    return { within, over, needsCost, committed, free: budget - committed };
  }, [rows, withinIds, rejects, budget, pins, forcedOver]);

  // Sequential 1..N priority label over the COSTED plan (both sections) by rank, so the
  // Rank column reads 1-5 for a 5-buy plan instead of the global engine rank (185, 194);
  // the 425 skipped needs-cost SKUs are ignored entirely (M8-F).
  const displayRank = useMemo<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    rows
      .filter((r) => r.unit_cost !== null)
      .slice()
      .sort((a, b) => a.rank - b.rank)
      .forEach((r, i) => {
        map[r.id] = i + 1;
      });
    return map;
  }, [rows]);

  const decisionMap = useMemo<Record<string, M8RowDecision>>(() => {
    const map: Record<string, M8RowDecision> = {};
    for (const r of rows) {
      if (rejects.has(r.id)) map[r.id] = 'rejected';
      else if (pins.has(r.id)) map[r.id] = 'accepted';
      else map[r.id] = null;
    }
    return map;
  }, [rows, pins, rejects]);

  // Which rows have already been materialised into a draft PO (M8-F8/M8-F9). Keyed
  // by recommendation id off the server decision overlay - populated only AFTER
  // Confirm decisions (accept/adjust stage, they don't create a PO). A row with a PO
  // is "confirmed": it drops out of the confirm-bar count and shows a "PO created"
  // link instead of Accept/Reject.
  const poByRow = useMemo<Record<string, { po_number: string; po_id: string | null }>>(() => {
    const map: Record<string, { po_number: string; po_id: string | null }> = {};
    for (const d of Object.values(decisions.byId)) {
      if (d.draft_po_number) {
        map[d.recommendation_id] = { po_number: d.draft_po_number, po_id: d.draft_po_id };
      }
    }
    return map;
  }, [decisions.byId]);

  const recById = useCallback(
    (id: string) => recs.find((r) => r.id === id) ?? null,
    [recs],
  );

  /** Accept a within-budget row, OR fund an over-budget row by dragging it up
   *  (M8-F13: drag is the only way to fund an over row). Both pin the row and move
   *  it into the Within section (M8-C3). For an already-within Accept the section
   *  add is a no-op; for a drag-up it promotes exactly that one row (M8-F12 (b)). */
  const fund = useCallback(
    (row: M8PlanRow) => {
      setPins((p) => new Set(p).add(row.id));
      setWithinIds((w) => new Set(w).add(row.id)); // move THIS row in, nothing else
      setForcedOver((f) => {
        const next = new Set(f);
        next.delete(row.id);
        return next;
      });
      setRejects((r) => {
        const next = new Set(r);
        next.delete(row.id);
        return next;
      });
      mutations.accept.mutateAsync(row.rec).catch((e) => {
        toast.error(e instanceof Error ? e.message : 'Failed to accept recommendation');
      });
    },
    [mutations.accept],
  );

  /** Defer a row (drag down) - client-only budget staging, no server decision.
   *  KNOWN LIMITATION: `forcedOver` is live-view-only; `confirm()` derives the persisted
   *  funded/deferred split from the decision overlay (pins/rejects) alone, so a row that
   *  was only dragged-to-defer (not rejected) reverts to funded on reload. */
  const defer = useCallback((row: M8PlanRow) => {
    setPins((p) => {
      const next = new Set(p);
      next.delete(row.id);
      return next;
    });
    setForcedOver((f) => new Set(f).add(row.id));
    setWithinIds((w) => {
      const next = new Set(w);
      next.delete(row.id); // move THIS row out, nothing else
      return next;
    });
  }, []);

  /** Reject a row with a reason → POST reject. Reject marks the DECISION only
   *  (M8-F1): it must NOT move the row between budget sections, so we leave `pins`
   *  and `forcedOver` untouched - a pinned/within row stays within (greyed), an
   *  over-budget row stays over. The allocator excludes a rejected row's cash from
   *  `committed`. Undo is via Accept (`fund`), which clears the reject. */
  const reject = useCallback(
    (row: M8PlanRow, reason: string) => {
      setRejects((r) => new Set(r).add(row.id));
      mutations.reject
        .mutateAsync({ rec: row.rec, payload: { reason_text: reason } })
        .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to reject recommendation'));
    },
    [mutations.reject],
  );

  /** Inline qty/supplier edit → POST adjust (supplier CODE in override_supplier_id). */
  const editRow = useCallback(
    (row: M8PlanRow, patch: { order_qty: number; supplier_code: string }, reason: string) => {
      setLocalEdits((e) => ({ ...e, [row.id]: patch }));
      setEditedIds((e) => new Set(e).add(row.id));
      setPins((p) => new Set(p).add(row.id));
      setWithinIds((w) => new Set(w).add(row.id));
      mutations.adjust
        .mutateAsync({
          rec: row.rec,
          payload: {
            override_qty: patch.order_qty,
            override_supplier_code: patch.supplier_code || null,
            reason_text: reason,
          },
        })
        .then((res) => toast.success(`Adjusted ${row.sku} - draft PO with ${res.supplier_name} staged`))
        .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to adjust recommendation'));
    },
    [mutations.adjust],
  );

  /** Apply one confirmed market-bump line → POST adjust with the new qty. */
  const applyProposalLine = useCallback(
    (line: M8ProposalLine) => {
      const rec = recById(line.row_id);
      if (!rec) {
        toast.error('That line is no longer in this plan.');
        return;
      }
      const base = recToPlanRow(rec);
      setLocalEdits((e) => ({
        ...e,
        [line.row_id]: { order_qty: line.new_qty, supplier_code: base.supplier.code },
      }));
      setEditedIds((e) => new Set(e).add(line.row_id));
      setPins((p) => new Set(p).add(line.row_id));
      setWithinIds((w) => new Set(w).add(line.row_id));
      mutations.adjust
        .mutateAsync({
          rec,
          payload: {
            override_qty: line.new_qty,
            override_supplier_code: null,
            reason_text: line.reason,
          },
        })
        .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to apply market bump'));
    },
    [mutations.adjust, recById],
  );

  /** Apply an assistant action proposal (M8-F16) - route each proposed line through the
   *  SAME confirm-gated decision handlers a manual click uses: accept → `fund`, reject →
   *  `reject` (carries the assistant's reason), adjust → `editRow` (new qty + reason,
   *  supplier unchanged). The Apply click IS the confirmation; the LLM never wrote a
   *  numeric field. A row that's no longer in the plan is skipped and counted as failed.
   *  Fires one summary toast; per-line server failures still surface via each handler. */
  const applyActions = useCallback(
    (lines: ActionProposalLine[]) => {
      let applied = 0;
      let failed = 0;
      for (const line of lines) {
        const rec = recById(line.rec_id);
        if (!rec) {
          failed += 1;
          continue;
        }
        const row = rows.find((r) => r.id === line.rec_id) ?? recToPlanRow(rec);
        if (line.action === 'accept') {
          fund(row);
          applied += 1;
        } else if (line.action === 'reject') {
          reject(row, line.reason);
          applied += 1;
        } else if (line.action === 'adjust' && line.new_qty != null) {
          editRow(row, { order_qty: line.new_qty, supplier_code: row.supplier.code }, line.reason);
          applied += 1;
        } else {
          failed += 1;
        }
      }
      if (applied) toast.success(`Applied ${applied} plan action${applied === 1 ? '' : 's'}`);
      if (failed) toast.error(`${failed} action${failed === 1 ? '' : 's'} could not be applied`);
      return { applied, failed };
    },
    [rows, recById, fund, reject, editRow],
  );

  /** Clear ALL local decision state (pins / rejects / drag / inline edits) back to the
   *  as-generated plan. Used by the demo Reset: the server decisions + draft POs are
   *  wiped server-side, so the FE overlay must drop to empty too (the per-run seed guard
   *  otherwise keeps the stale pins/rejects on screen). Budget is a view pref, left as-is. */
  const resetLocal = useCallback(() => {
    setPins(new Set());
    setRejects(new Set());
    setForcedOver(new Set());
    setEditedIds(new Set());
    setLocalEdits({});
    // Re-seed the sticky split from a clean greedy at the current budget (no pins/drags).
    const split = computeFundingM8(rows, budget, {
      pins: EMPTY_SET,
      rejects: EMPTY_SET,
      forcedOver: EMPTY_SET,
    });
    setWithinIds(new Set(split.within.map((r) => r.id)));
  }, [rows, budget]);

  /** Persist the chosen budget then materialise staged decisions into draft POs.
   *  NOTE: the persisted split is derived server-side from the decision overlay
   *  (pins/rejects) + budget only - `forcedOver` (manual drag-to-defer) is NOT sent, so a
   *  dragged-to-defer row that was never rejected reverts to funded on reload. */
  const confirm = useCallback(async () => {
    if (!runId) return;
    await applyBudget(runId, budget).catch(() => {
      /* budget persist is best-effort; the confirm is the material action */
    });
    return mutations.confirm.mutateAsync([]);
  }, [runId, budget, mutations.confirm]);

  return {
    runId,
    rows,
    budget,
    setBudget,
    pins,
    rejects,
    editedIds,
    funding,
    displayRank,
    decisions: decisionMap,
    decisionsById: decisions.byId,
    poByRow,
    fund,
    defer,
    reject,
    editRow,
    applyProposalLine,
    applyActions,
    resetLocal,
    confirm,
    isLoading: recsQuery.isLoading,
    isError: recsQuery.isError,
    error: recsQuery.error,
    refetch: recsQuery.refetch,
    isConfirming: mutations.confirm.isPending,
  };
}

export type M8PlanState = ReturnType<typeof useReorderPlan>;
