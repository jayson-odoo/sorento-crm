'use client';

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  acceptRecommendation,
  adjustRecommendation,
  bulkAcceptFunded,
  bulkRejectRecommendations,
  confirmDecisions,
  getRecommendationDecisions,
  rejectRecommendation,
} from '../services/decisionService';
import type {
  AdjustPayload,
  RecDecision,
  RejectPayload,
} from '../types/decisions.types';
import type { ReorderRecommendation } from '../types/reorder.types';

/** Cache key for the decisions recorded against a run. */
export const decisionsKey = (runId: string | null) => ['scm', 'reorder', 'decisions', runId];
/** Prefix key for the Purchase Orders list - invalidated whenever a draft PO changes. */
const purchaseOrdersKey = ['scm', 'purchase-orders'];

/**
 * Decisions recorded so far for a run, indexed by recommendation id - drives the
 * per-row status badges (proposed / accepted / adjusted / dismissed) in the cash
 * results grids.
 */
export function useRecommendationDecisions(runId: string | null, enabled: boolean) {
  const query = useQuery({
    queryKey: decisionsKey(runId),
    queryFn: () => getRecommendationDecisions(runId as string),
    enabled: enabled && !!runId,
    staleTime: 5_000,
    retry: 1,
  });

  const byId = useMemo<Record<string, RecDecision>>(() => {
    const map: Record<string, RecDecision> = {};
    (query.data ?? []).forEach((d) => {
      map[d.recommendation_id] = d;
    });
    return map;
  }, [query.data]);

  return { ...query, byId };
}

/**
 * The Accept / Adjust / Reject / bulk-Accept mutations for one run. Each
 * invalidates BOTH the decisions cache (so the row badge updates) and the PO
 * list cache (so a freshly-drafted PO appears). The caller awaits `mutateAsync`
 * and owns the success toast (so it can offer a "View draft PO" hand-off).
 */
export function useDecisionMutations(runId: string | null) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: decisionsKey(runId) });
    void queryClient.invalidateQueries({ queryKey: purchaseOrdersKey });
  };

  const accept = useMutation({
    mutationFn: (rec: ReorderRecommendation) => acceptRecommendation(rec),
    onSuccess: invalidate,
  });

  const adjust = useMutation({
    mutationFn: ({ rec, payload }: { rec: ReorderRecommendation; payload: AdjustPayload }) =>
      adjustRecommendation(rec, payload),
    onSuccess: invalidate,
  });

  const reject = useMutation({
    mutationFn: ({ rec, payload }: { rec: ReorderRecommendation; payload: RejectPayload }) =>
      rejectRecommendation(rec, payload),
    onSuccess: invalidate,
  });

  const bulkAccept = useMutation({
    mutationFn: (recs: ReorderRecommendation[]) => bulkAcceptFunded(runId as string, recs),
    onSuccess: invalidate,
  });

  const bulkReject = useMutation({
    mutationFn: ({ recs, reason }: { recs: ReorderRecommendation[]; reason: string }) =>
      bulkRejectRecommendations(runId as string, recs, reason),
    onSuccess: invalidate,
  });

  // Confirm decisions materialises the staged accepts/adjusts into draft POs, so
  // it invalidates the decisions cache (rows now carry a → PO link) AND the PO list.
  const confirm = useMutation({
    mutationFn: (ids: string[] = []) => confirmDecisions(runId as string, ids),
    onSuccess: invalidate,
  });

  return { accept, adjust, reject, bulkAccept, bulkReject, confirm };
}
