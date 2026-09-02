'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import { useHasPermission } from '@/hooks/usePermissions';
import { getFormHandlingTrackers, type FormSLASourceType } from './formSLAService';
import { skipFormStage, type FormSkipResult } from './formSkipService';

export interface UseFormSkipInput {
  sourceEntityType: FormSLASourceType;
  sourceEntityId: string | null | undefined;
  /**
   * The permission slug that authorises the skip for THIS entity type. Per-entity by
   * design - a config row must never be able to mint authority, so the caller (which
   * knows its own domain) supplies it rather than the config. The backend re-checks the
   * same slug via the adapter, so this only decides whether the item is offered.
   */
  permission: string;
  /**
   * Extra query-key segment so the capability refetches the moment the entity's status
   * changes - same rule as useHandlingLock, which is keyed on updated_at / status.
   */
  entityKey?: string | number | Date | null;
  enabled?: boolean;
  /** Fired after a successful skip so the page can invalidate its own entity query. */
  onSkipped?: (result: FormSkipResult) => void;
}

export interface UseFormSkipResult {
  /** True when the gear item should render: skippable stage + permission + tracker. */
  canSkip: boolean;
  /** Config-authored button label ("Settled on site"). Null when not skippable. */
  actionLabel: string | null;
  /** Submit the skip with an optional note. */
  submit: (note?: string) => void;
  isSubmitting: boolean;
}

/**
 * Resolve whether the active SLA stage can be skipped, and expose the skip mutation.
 *
 * Reuses the handling-lock tracker query (`form-handling-tracker`) rather than adding a
 * second round-trip - that query already runs on every form detail page, and the backend
 * rides `skip_event` / `skip_action_label` / `can_skip` along on the same active row.
 *
 * On success BOTH tracker queries are invalidated: the lock banner reads
 * `form-handling-tracker` while the SLA escalation banner reads `form-sla-trackers`.
 * Invalidating one leaves the other rendering a stage that no longer exists.
 */
export function useFormSkip(input: UseFormSkipInput): UseFormSkipResult {
  const { sourceEntityType, sourceEntityId, permission, entityKey, enabled = true, onSkipped } =
    input;
  const queryClient = useQueryClient();
  const hasPermission = useHasPermission(permission);

  const queryEnabled = enabled && !!sourceEntityId;
  const { data: rows } = useQuery({
    queryKey: ['form-handling-tracker', sourceEntityType, sourceEntityId, entityKey ?? null],
    queryFn: () => getFormHandlingTrackers(sourceEntityType, sourceEntityId as string),
    enabled: queryEnabled,
  });

  const activeRow = (rows ?? []).find((t) => !t.is_resolved) ?? null;
  const skipEvent = activeRow?.skip_event ?? null;
  const actionLabel = activeRow?.skip_action_label ?? null;
  // `can_skip` is the server's own verdict (stage skippable AND viewer holds the
  // adapter's permission). ANDed with the client-side check so the item disappears
  // immediately on a permission change without waiting for a tracker refetch.
  const backendAllows = Boolean(activeRow?.can_skip);

  const invalidate = () => {
    queryClient.invalidateQueries({
      queryKey: ['form-handling-tracker', sourceEntityType, sourceEntityId],
    });
    queryClient.invalidateQueries({ queryKey: ['form-sla-trackers'] });
  };

  const mutation = useMutation({
    mutationFn: (note?: string) =>
      skipFormStage(sourceEntityType, sourceEntityId as string, note ? { note } : {}),
    onSuccess: (result) => {
      toast.success(result.message);
      invalidate();
      onSkipped?.(result);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return {
    canSkip:
      enabled && Boolean(sourceEntityId) && hasPermission && backendAllows && !!skipEvent,
    actionLabel,
    submit: (note?: string) => mutation.mutate(note),
    isSubmitting: mutation.isPending,
  };
}
