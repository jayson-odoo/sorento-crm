'use client';

/**
 * The Products action set (D15): Delete.
 *
 * Edit is the record page's primary button and the list's row click opens the
 * record, so neither belongs in this menu (D15). The list's old Duplicate icon
 * is not here because it was never implemented - it logged to the console.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import type { ProductListItem } from './types/product.types';
import ProductDeleteDialog from './components/product-delete-dialog';

export interface UseProductActionsOptions {
  /** Where to go once the record is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useProductActions(
  product: ProductListItem | undefined | null,
  { onDeleted }: UseProductActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('master_data.products.delete');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const actions: RecordAction[] = [];
  if (!product) return { actions, dialogs: null };

  if (canDelete) {
    actions.push({
      key: 'product.delete',
      label: 'Delete product',
      icon: Trash2,
      kind: 'destructive',
      run: () => setDeleteOpen(true),
    });
  }

  const dialogs = (
    <ProductDeleteDialog
      open={deleteOpen}
      closeDialog={() => setDeleteOpen(false)}
      product={product}
      onSuccess={onDeleted}
    />
  );

  return { actions, dialogs };
}

/** The list row's "..." cell - the same items the record page's gear shows. */
export function ProductRowActions({ product }: { product: ProductListItem }) {
  const { actions, dialogs } = useProductActions(product);

  if (actions.length === 0) return null;

  return (
    <>
      <RowActionsMenu actions={actions} ariaLabel="product" />
      {dialogs}
    </>
  );
}
