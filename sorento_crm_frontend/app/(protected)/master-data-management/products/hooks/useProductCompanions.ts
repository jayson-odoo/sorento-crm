'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  createProductCompanionRule,
  listCompanionRulesForCompanion,
  listCompanionRulesForHost,
} from '../services/productCompanionService';
import type { ProductCompanionRuleWrite } from '../types/productCompanion.types';

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
    mutationFn: (write: ProductCompanionRuleWrite) => createProductCompanionRule(write),
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

/**
 * Delete asks nothing (D7): the row's Delete parks the removal on the server for its
 * grace window and a toast carries the countdown, exactly as `product_supplier.unlink`
 * does on the same page's Suppliers section - the way back is Cancel, not a dialog.
 *
 * `hostProductIds` (review round 1 item 14): every host across the rules CURRENTLY on
 * screen, so a deleted rule's hosts also refetch their own "Ships with" mirror - it
 * would otherwise keep naming a rule that no longer exists until the host's own page
 * happened to be revisited.
 */
export function useCompanionRuleDelete(
  companionProductId: string,
  hostProductIds: readonly string[] = [],
) {
  return useDeferredRowAction({
    actionKey: 'product_companion_rule.delete',
    entityType: 'product_companion_rule',
    verb: 'Deleting',
    successMessage: 'Rule deleted',
    invalidateKeys: [
      companionKey(companionProductId),
      ...hostProductIds.map((hostId) => hostKey(hostId)),
    ],
  });
}
