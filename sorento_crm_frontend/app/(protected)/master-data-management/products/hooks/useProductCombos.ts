'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  addProductComboPart,
  copyProductCombo,
  createProductCombo,
  listProductCombos,
  listProductSoldWith,
  updateProductCombo,
  updateProductComboPart,
  type ComboCopySummary,
} from '../services/productComboService';
import type {
  ProductComboCreate,
  ProductComboPartCreate,
  ProductComboPartUpdate,
  ProductComboUpdate,
} from '../types/productCombo.types';

// Exported so `useProductComboImage` (a sibling hook, S5) invalidates the
// SAME query key a combo mutation here does - two different cache keys for
// one list would leave a combo's own image stale after an upload.
export const combosKey = (productId: string | undefined) => ['product-combos', productId];
const soldWithKey = (productId: string | undefined) => ['product-sold-with', productId];

/** The host's own combos, with their parts (AC-S1-1). */
export function useProductCombos(productId: string | undefined) {
  return useQuery({
    queryKey: combosKey(productId),
    queryFn: () => listProductCombos(productId as string),
    enabled: !!productId,
  });
}

/** The read-only mirror on a PART's own page (AC-S1-6). */
export function useProductSoldWith(productId: string | undefined) {
  return useQuery({
    queryKey: soldWithKey(productId),
    queryFn: () => listProductSoldWith(productId as string),
    enabled: !!productId,
  });
}

export function useCreateProductCombo(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (write: ProductComboCreate) => createProductCombo(productId, write),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: combosKey(productId) });
      toast.success('Combo added');
    },
    // No toast on error: a duplicate name is answered inline in the modal
    // (AC-S1-2), where the field that has to change is.
  });
}

export function useAddProductComboPart(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { comboId: string; write: ProductComboPartCreate }) =>
      addProductComboPart(input.comboId, input.write),
    onSuccess: (part) => {
      queryClient.invalidateQueries({ queryKey: combosKey(productId) });
      // The part now reads "Sold with" this host on its own page.
      queryClient.invalidateQueries({ queryKey: soldWithKey(part.product_id) });
    },
    // Host-as-part and duplicate-part are answered inline under the picker
    // (AC-S1-3), so no toast here either.
  });
}

export function useUpdateProductCombo(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { comboId: string; write: ProductComboUpdate }) =>
      updateProductCombo(input.comboId, input.write),
    onSuccess: () => {
      toast.success('Combo saved');
      return queryClient.invalidateQueries({ queryKey: combosKey(productId) });
    },
    onError: (error: Error, input) => {
      // A refused rename is answered under the name input (COMBO-RENAME), not in a toast too.
      if ('name' in input.write) return;
      toast.error(error.message || 'Failed to save the combo');
    },
  });
}

export function useUpdateProductComboPart(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { partId: string; write: ProductComboPartUpdate }) =>
      updateProductComboPart(input.partId, input.write),
    onSuccess: () => {
      toast.success('Part saved');
      return queryClient.invalidateQueries({ queryKey: combosKey(productId) });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save the part'),
  });
}

/**
 * Delete asks nothing (D7): the button parks the removal on the server for its
 * grace window and a toast carries the countdown, the same shape
 * `product_companion_rule.delete` uses on this page's Suppliers tab.
 *
 * `partProductIds` is every product currently on screen as a part, so a removal
 * also refetches that product's own "Sold with" mirror - it would otherwise keep
 * naming a combo it is no longer in until its page happened to be revisited.
 */
export function useProductComboDelete(
  productId: string,
  partProductIds: readonly string[] = [],
) {
  return useDeferredRowAction({
    actionKey: 'product_combo.delete',
    entityType: 'product_combo',
    verb: 'Deleting',
    successMessage: 'Combo deleted',
    invalidateKeys: [
      combosKey(productId),
      ...partProductIds.map((partId) => soldWithKey(partId)),
    ],
  });
}

export function useProductComboPartDelete(
  productId: string,
  partProductIds: readonly string[] = [],
) {
  return useDeferredRowAction({
    actionKey: 'product_combo_part.delete',
    entityType: 'product_combo_part',
    verb: 'Removing',
    successMessage: 'Part removed',
    invalidateKeys: [
      combosKey(productId),
      ...partProductIds.map((partId) => soldWithKey(partId)),
    ],
  });
}

/** The result toast of a combo copy: what was created, overwritten and skipped. */
export function comboCopyResultLine(summary: ComboCopySummary): string {
  const parts = [`${summary.created} created`];
  if (summary.overwritten) parts.push(`${summary.overwritten} overwritten`);
  if (summary.skipped.length) parts.push(`${summary.skipped.length} skipped`);
  const links = summary.template_links_copied
    ? ''
    : ' Price tag templates were not copied.';
  return `Combo copied: ${parts.join(', ')}.${links}`;
}

/**
 * COMBO-COPY-TO-PRODUCTS: `preview` is the dry run behind the confirm step, `copy` the write.
 * Every product's combos and "Sold with" mirrors are refetched after a copy, since any may change.
 */
export function useCopyProductCombo(comboId: string) {
  const queryClient = useQueryClient();
  const preview = useMutation({
    mutationFn: (targetIds: string[]) =>
      copyProductCombo(comboId, targetIds, [], true),
    onError: (error: Error) => toast.error(error.message),
  });
  const copy = useMutation({
    mutationFn: ({
      targetIds,
      overwriteIds,
    }: {
      targetIds: string[];
      overwriteIds: string[];
    }) => copyProductCombo(comboId, targetIds, overwriteIds),
    onSuccess: (summary) => {
      queryClient.invalidateQueries({ queryKey: ['product-combos'] });
      queryClient.invalidateQueries({ queryKey: ['product-sold-with'] });
      toast.success(comboCopyResultLine(summary));
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return { preview, copy };
}
