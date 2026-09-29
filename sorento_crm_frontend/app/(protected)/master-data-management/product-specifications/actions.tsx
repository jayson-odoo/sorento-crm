'use client';

/**
 * The Product Specifications record action set (D15): Delete.
 *
 * The gear (and the registry grid's row "..." menu, `SpecKeyRowActions`) is
 * ALWAYS present. Delete itself is left OUT of the array entirely on a built-in
 * specification (it ships with the product and would simply reappear on the next
 * deploy, so the backend refuses it too) and without `master_data.spec_registry.delete`
 * (AC-S3.8) - a disabled row with no reason attached reads as broken, and there is no
 * explanation to attach per the no-explanation rule. One hook, two surfaces: the
 * record page's gear renders it inline, next to Save/Cancel; the row menu renders the
 * same array, with the countdown in a toast instead - a row has nowhere to put one.
 */

import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { SPEC_REGISTRY_QUERY_KEY } from './hooks/useSpecRegistryQuery';
import type { SpecRegistryKey } from './types/productSpec.types';

export interface UseSpecKeyActionsOptions {
  onDeleted?: () => void;
  /**
   * Where the countdown goes: `inline` hands it back as `pending` for the record
   * card's primary area; `toast` (the list row) puts it over the grid instead.
   */
  surface?: 'inline' | 'toast';
}

export function useSpecKeyActions(
  specKey: SpecRegistryKey | undefined | null,
  { onDeleted, surface = 'inline' }: UseSpecKeyActionsOptions = {},
): RecordActionSet {
  const canDelete = useHasPermission('master_data.spec_registry.delete');

  // Delete asks nothing (D7): the countdown takes the primary button's place on the
  // record card, and Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'spec_key.delete',
    entityType: 'spec_key',
    entityId: specKey?.spec_key,
    verb: 'Deleting',
    subject: specKey?.label ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Specification deleted',
    invalidateKeys: [SPEC_REGISTRY_QUERY_KEY],
    onCommitted: onDeleted,
  });

  // A built-in specification carries no Delete item at all (AC-S3.8): it ships with
  // the product and would just reappear on the next deploy, so there is nothing this
  // action could honestly offer.
  const canDeleteThis = !!specKey && specKey.source === 'user' && canDelete;
  const actions: RecordAction[] = canDeleteThis
    ? [
        {
          key: 'spec_key.delete',
          label: 'Delete specification',
          icon: Trash2,
          kind: 'destructive',
          disabled: deletion.isPending,
          run: deletion.start,
        },
      ]
    : [];

  return { actions, dialogs: null, pending: deletion.countdown };
}

/** The registry grid row's "..." cell - the same items the record gear shows (D15). */
export function SpecKeyRowActions({ specKey }: { specKey: SpecRegistryKey }) {
  const { actions } = useSpecKeyActions(specKey, { surface: 'toast' });

  return <RowActionsMenu actions={actions} ariaLabel="specification" />;
}
