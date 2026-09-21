'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  addProductComboPart,
  createProductCombo,
  listProductCombos,
  listProductSoldWith,
  updateProductComboPart,
} from '../services/productComboService';
import type {
  ProductComboCreate,
  ProductComboPartCreate,
  ProductComboPartUpdate,
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

export function useUpdateProductComboPart(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { partId: string; write: ProductComboPartUpdate }) =>
      updateProductComboPart(input.partId, input.write),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: combosKey(productId) }),
    onError: (error: Error) => toast.error(error.message || 'Failed to save the choice group'),
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
