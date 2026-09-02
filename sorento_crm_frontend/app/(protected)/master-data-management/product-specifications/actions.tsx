'use client';

/**
 * The Product Specifications record action set (D15): Delete.
 *
 * The gear (and the registry grid's row "..." menu, `SpecKeyRowActions`) is
 * ALWAYS present - both surfaces render the same one-item array. Delete itself is
 * disabled on a seed key (it ships with the product and would simply reappear on
 * the next deploy, so the backend refuses it too - B.1, B.6) and without
 * `master_data.spec_registry.delete`; no tooltip explains why, per the no-explanation
 * rule (A.2, D14, D15b). One hook, two surfaces: the record page's gear renders it
 * inline, next to Save/Cancel; the row menu renders the same array, with the
 * countdown in a toast instead - a row has nowhere to put one.
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

  const actions: RecordAction[] = [
    {
      key: 'spec_key.delete',
      label: 'Delete specification',
      icon: Trash2,
      kind: 'destructive',
      disabled: !specKey || specKey.source !== 'user' || !canDelete || deletion.isPending,
      run: deletion.start,
    },
  ];

  return { actions, dialogs: null, pending: deletion.countdown };
}

/** The registry grid row's "..." cell - the same items the record gear shows (D15). */
export function SpecKeyRowActions({ specKey }: { specKey: SpecRegistryKey }) {
  const { actions } = useSpecKeyActions(specKey, { surface: 'toast' });

  return <RowActionsMenu actions={actions} ariaLabel="specification" />;
}
