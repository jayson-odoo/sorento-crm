'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { deferredToast, dismissDeferredToast } from '@/components/common/deferredToast';
import {
  createProductCompanionRule,
  deleteProductCompanionRule,
  listCompanionRulesForCompanion,
  listCompanionRulesForHost,
  type CreateCompanionRuleInput,
} from '../services/productCompanionService';
import type { ProductCompanionRuleRow } from '../types/productCompanion.types';

const companionKey = (companionProductId: string | undefined) => [
  'product-companion-rules',
  'companion',
  companionProductId,
];
const hostKey = (hostProductId: string | undefined) => [
  'product-companion-rules',
  'host',
  hostProductId,
];

/** The companion's own "Supplied with" list (UAC A1). */
export function useCompanionRulesForCompanion(companionProductId: string | undefined) {
  return useQuery({
    queryKey: companionKey(companionProductId),
    queryFn: () => listCompanionRulesForCompanion(companionProductId as string),
    enabled: !!companionProductId,
  });
}

/** A host's read-only "Ships with" list (UAC A5). */
export function useCompanionRulesForHost(hostProductId: string | undefined) {
  return useQuery({
    queryKey: hostKey(hostProductId),
    queryFn: () => listCompanionRulesForHost(hostProductId as string),
    enabled: !!hostProductId,
  });
}

export function useCreateCompanionRule(companionProductId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateCompanionRuleInput) => createProductCompanionRule(input),
    onSuccess: (row) => {
      queryClient.invalidateQueries({ queryKey: companionKey(companionProductId) });
      // Every host this rule names now "ships with" it too.
      for (const host of row.hosts) {
        queryClient.invalidateQueries({ queryKey: hostKey(host.product_id) });
      }
      toast.success('Rule saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add the rule'),
  });
}

/** D7's window for a hard delete (System Settings > General, once that setting exists). */
const HARD_DELETE_WINDOW_SECONDS = 10;

/**
 * PHASE-1 ONLY. Simulates the server-parked grace window locally, reusing the shared
 * `DeferredCountdown`/`deferredToast` presentational pieces so the UX is byte-identical
 * to the real thing - there is just no `/api/v1/pending-actions` round trip backing it,
 * because that route 400s on an action_key nothing has registered yet
 * (`app/services/record_actions.py` has no `product_companion_rule.delete` entry until
 * Phase 2 S4). Phase 2 deletes this hook entirely and points the row at
 * `useDeferredRowAction({ actionKey: 'product_companion_rule.delete', ... })` instead -
 * the real thing, once the backend can dispatch it.
 */
export function useLocalDeferredRuleDelete(companionProductId: string) {
  const queryClient = useQueryClient();
  const [targetId, setTargetId] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastIdRef = useRef<string | number | null>(null);

  const settle = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
    if (toastIdRef.current !== null) dismissDeferredToast(toastIdRef.current);
    toastIdRef.current = null;
    setTargetId(null);
  }, []);

  const cancel = useCallback(() => {
    settle();
    toast.success('Cancelled. Nothing was applied.');
  }, [settle]);

  const run = useCallback(
    (rule: ProductCompanionRuleRow) => {
      if (targetId) return; // one countdown at a time, same as the real hook
      const commitAt = new Date(Date.now() + HARD_DELETE_WINDOW_SECONDS * 1000).toISOString();
      const hostProductIds = rule.hosts.map((h) => h.product_id);
      const subject = `${rule.companion_item_code} with ${rule.hosts
        .map((h) => h.item_code)
        .join(' + ')}`;
      setTargetId(rule.id);
      toastIdRef.current = deferredToast({
        pending: {
          id: `local-${rule.id}`,
          action_key: 'product_companion_rule.delete',
          entity_type: 'product_companion_rule',
          entity_id: rule.id,
          commit_at: commitAt,
          window_seconds: HARD_DELETE_WINDOW_SECONDS,
        },
        verb: 'Deleting',
        subject,
        onCancel: cancel,
      });
      timeoutRef.current = setTimeout(async () => {
        try {
          await deleteProductCompanionRule(rule.id);
          queryClient.invalidateQueries({ queryKey: companionKey(companionProductId) });
          for (const hostId of hostProductIds) {
            queryClient.invalidateQueries({ queryKey: hostKey(hostId) });
          }
          toast.success('Rule deleted');
        } catch (error) {
          toast.error(error instanceof Error ? error.message : 'Failed to delete the rule');
        } finally {
          settle();
        }
      }, HARD_DELETE_WINDOW_SECONDS * 1000);
    },
    [targetId, cancel, companionProductId, queryClient, settle],
  );

  useEffect(() => () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  return { run, targetId, isPending: targetId !== null };
}
