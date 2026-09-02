'use client';

/**
 * The Product Specifications record action set (D15): Delete.
 *
 * Only a user-made specification carries it - a seed key ships with the product and
 * would simply reappear on the next deploy, so the backend refuses it and the UI
 * never offers it (B.1, B.6). There is no list row menu (A.2): a key has this one
 * secondary action and it lives in the record gear only.
 */

import { Trash2 } from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { SPEC_REGISTRY_QUERY_KEY } from './hooks/useSpecRegistryQuery';
import type { SpecRegistryKey } from './types/productSpec.types';

export interface UseSpecKeyActionsOptions {
  onDeleted?: () => void;
}

export function useSpecKeyActions(
  specKey: SpecRegistryKey | undefined | null,
  { onDeleted }: UseSpecKeyActionsOptions = {},
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
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Specification deleted',
    invalidateKeys: [SPEC_REGISTRY_QUERY_KEY],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!specKey || specKey.source !== 'user') return { actions, dialogs: null, pending: null };

  if (canDelete) {
    actions.push({
      key: 'spec_key.delete',
      label: 'Delete specification',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    });
  }

  return { actions, dialogs: null, pending: deletion.countdown };
}
