'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { confirmDecisions } from '../services/decisionService';
import { savePlanEdits, type PlanEditRow } from '../services/planEditsService';
import { planDecisionKind, type PlanDecision, type PlanDecisionMap } from '../lib/planDecisions';
import {
  confirmSummary,
  decisionForLine,
  editedProductCount,
  hasRowEdit,
  recIdsForLine,
  type ConfirmSummary,
  type PlanRowEdit,
  type PlanRowEditMap,
} from '../lib/planEdits';
import type { CoverProposal } from '../lib/coverPlan';
import type { PoReceipt } from '../lib/poCover';
import type { PlanLine } from '../lib/planLine';
import { planRowDecisionsKey } from './usePlanLines';

/**
 * Every unsaved edit on a plan, and the two buttons that end them.
 *
 * The draft map is the whole point of the revamp (plan 4.5): the panel's inputs write here,
 * the pill turns Unsaved, and NOTHING reaches the backend until Save runs. Before this, each
 * control wrote on its own - a pencil Record, a MOQ blur, a level Save, a health click - so
 * one row could be four requests and a half-finished thought was already persisted.
 *
 * The map is keyed by ROW id. A product-grain row is several recommendations underneath, and
 * the fan-out happens at save time (`recIdsForLine`), the same way `usePlanLines.decide` and
 * `.updateMoq` already fan their writes out.
 */
export function usePlanEdits(
  runId: string | null,
  /** The rows AS THE GRID RENDERS THEM - grouped when the run is product-grain, so the map's
   *  keys are the ids the grid's own cells write under. */
  lines: PlanLine[],
  decisions: PlanDecisionMap,
  coverFor?: (line: PlanLine) => CoverProposal,
  poFor?: (line: PlanLine) => PoReceipt[],
) {
  const qc = useQueryClient();
  const [edits, setEdits] = useState<PlanRowEditMap>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const setRowEdit = useCallback((line: PlanLine, patch: PlanRowEdit) => {
    setEdits((prev) => ({ ...prev, [line.id]: { ...prev[line.id], ...patch } }));
  }, []);

  /** Drop a row's draft entirely - "Use suggestion" is the absence of an edit, not a
   *  fourth kind of one. */
  const resetRow = useCallback((line: PlanLine) => {
    setEdits((prev) => {
      if (!prev[line.id]) return prev;
      const next = { ...prev };
      delete next[line.id];
      return next;
    });
  }, []);

  const clearAll = useCallback(() => setEdits({}), []);

  const saveCount = useMemo(() => editedProductCount(edits, lines), [edits, lines]);
  const confirmable = useMemo<ConfirmSummary>(
    () => confirmSummary(edits, decisions, lines, coverFor, poFor),
    [edits, decisions, lines, coverFor, poFor],
  );

  /**
   * Leaving with drafts prompts.
   *
   * `beforeunload` covers a refresh, a close and a jump out of the app - the three exits a
   * router guard cannot see. The one exit INSIDE the app (the plan header's "Plans" link)
   * asks its own question, because Next's app router gives no cancellable navigation event
   * to hang this on.
   */
  useEffect(() => {
    if (saveCount === 0) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Chrome ignores the string and shows its own wording; assigning it is still what
      // arms the prompt at all.
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [saveCount]);

  /** The draft map, flattened to one row per RECOMMENDATION - the wire shape. */
  const payloadRows = useCallback((): PlanEditRow[] => {
    const rows: PlanEditRow[] = [];
    for (const line of lines) {
      const edit = edits[line.id];
      if (!hasRowEdit(edit)) continue;
      const decision = editedDecisionFor(edit as PlanRowEdit, decisionForLine(line, decisions));
      for (const recId of recIdsForLine(line)) {
        rows.push({
          rec_id: recId,
          ...(decision ? { decision } : {}),
          ...(edit?.moq !== undefined ? { moq: edit.moq } : {}),
          ...(edit?.level !== undefined ? { level: edit.level } : {}),
          ...(edit?.reorderQty !== undefined ? { reorder_qty: edit.reorderQty } : {}),
          ...(edit?.lifecycle !== undefined ? { lifecycle: edit.lifecycle } : {}),
        });
      }
    }
    return rows;
  }, [edits, lines, decisions]);

  const save = useCallback(async () => {
    if (!runId) return null;
    const rows = payloadRows();
    if (!rows.length) return null;
    setIsSaving(true);
    try {
      const result = await savePlanEdits(runId, rows);
      clearAll();
      await qc.invalidateQueries({ queryKey: planRowDecisionsKey(runId) });
      await qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'level-suggestions'] });
      await qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'product-economics'] });
      await qc.invalidateQueries({ queryKey: ['plan-lines', runId, 'buy'] });
      return result;
    } finally {
      setIsSaving(false);
    }
  }, [runId, payloadRows, clearAll, qc]);

  /**
   * Confirm = save, then confirm. One button (plan 4.5): a buyer who edited three rows and
   * pressed Confirm meant those three edits to be in the purchase orders, and asking them to
   * press Save first is a trap with no upside.
   */
  const confirm = useCallback(async () => {
    if (!runId) return null;
    setIsConfirming(true);
    try {
      await save();
      const result = await confirmDecisions(runId, []);
      await qc.invalidateQueries({ queryKey: planRowDecisionsKey(runId) });
      await qc.invalidateQueries({ queryKey: ['scm', 'purchase-orders'] });
      return result;
    } finally {
      setIsConfirming(false);
    }
  }, [runId, save, qc]);

  return {
    edits,
    setRowEdit,
    resetRow,
    clearAll,
    saveCount,
    confirmable,
    save,
    confirm,
    isSaving,
    isConfirming,
  };
}

/**
 * The decision an edit implies, in the wire shape - or undefined when the edit touched no
 * part of the mixture (a MOQ change on its own is not a decision, and recording one would
 * make an untouched row start counting as decided).
 */
function editedDecisionFor(
  edit: PlanRowEdit,
  persisted: PlanDecision | undefined,
): PlanEditRow['decision'] {
  const touchedMix = edit.decision !== undefined;
  const touchedPrice = edit.priceMode !== undefined || edit.supplierCode !== undefined;
  if (!touchedMix && !touchedPrice) return undefined;
  // A price or supplier change on an already-decided row re-records that decision so the
  // draft PO carries the change; on an undecided row there is nothing to re-record yet.
  const base = edit.decision ?? persisted;
  if (!base) return undefined;
  const merged: PlanDecision = {
    ...base,
    ...(edit.priceMode !== undefined ? { priceMode: edit.priceMode } : {}),
    ...(edit.supplierCode !== undefined ? { supplierCode: edit.supplierCode } : {}),
  };
  return {
    kind: planDecisionKind(merged),
    buy_qty: merged.buy,
    stock_takes: (merged.stock?.sources ?? []).map((s) => ({
      location: s.warehouse_code,
      qty: s.qty,
    })),
    po_qty: merged.po,
    price_mode: merged.priceMode ?? 'use_last',
    ...(merged.supplierCode ? { supplier_code: merged.supplierCode } : {}),
  };
}
