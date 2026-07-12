'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import {
  claimHandling,
  getFormHandlingTrackers,
  releaseHandling,
  takeOverHandling,
  type FormHandlingTracker,
  type FormSLASourceType,
} from './formSLAService';
import {
  businessCtasEnabledForState,
  resolveHandlingLockState,
  type HandlingLockState,
  type HandlingLockTracker,
} from './handlingLock';

export interface UseHandlingLockInput {
  /** Active tracker's form type (PR component passes purchase_request | sponsorship_form). */
  sourceEntityType: FormSLASourceType;
  /** The form row id. Null/empty disables the query (e.g. the "new" route). */
  sourceEntityId: string | null | undefined;
  /**
   * Extra query-key segment so the lock refetches the moment the entity's status changes
   * (mirrors the escalation-banner query keyed on updated_at / status). Optional.
   */
  entityKey?: string | number | Date | null;
  /** Master enable flag (defaults true; combined with a truthy sourceEntityId). */
  enabled?: boolean;
}

export interface UseHandlingLockResult {
  state: HandlingLockState;
  /** True when the state-changing business CTAs should be enabled (ANDed on top of today's gates). */
  businessCtasEnabled: boolean;
  /** The active tracker (or null) — convenience passthrough for the banner/actions. */
  tracker: HandlingLockTracker | null;
  /** Non-null only when a banner should render (state !== 'not_escalated'). */
  banner: { state: HandlingLockState; tracker: HandlingLockTracker | null } | null;
  /** Claim the lock ("I'm handling this"). No-op when there is no active tracker. */
  claim: () => void;
  /** Take over the lock from the current holder (passes the holder id for optimistic concurrency). */
  takeOver: () => void;
  /** Release the lock (holder only). No-op when there is no active tracker. */
  release: () => void;
  /** True while a claim / take-over / release request is in flight. */
  isMutating: boolean;
}

/** Map the API row onto the framework-free lock shape (`tracking_id` → `id`). */
function toLockTracker(row: FormHandlingTracker | null): HandlingLockTracker | null {
  if (!row) return null;
  return {
    id: row.tracking_id,
    source_entity_type: row.source_entity_type,
    current_tier: row.current_tier,
    is_resolved: row.is_resolved,
    handled_by_id: row.handled_by_id,
    handled_by_name: row.handled_by_name,
    handled_at: row.handled_at,
    assigned_to_id: row.assigned_to_id,
  };
}

/**
 * Resolve the handling-lock state for the current (impersonation-aware) viewer and expose
 * the claim / take-over / release mutations.
 *
 * Sources the active tracker from the form-SLA handling query (GET /form-sla-tracking),
 * which carries the viewer-scoped `flag_enabled` / `viewer_eligible` / `viewer_is_admin`
 * that `resolveHandlingLockState` cannot compute client-side. Uses `useEffectiveUserId`
 * (the acting user under impersonation, not the NextAuth session user) for the "is this
 * me?" check — same rule as SlaExtendAction.
 */
export function useHandlingLock(input: UseHandlingLockInput): UseHandlingLockResult {
  const { sourceEntityType, sourceEntityId, entityKey, enabled = true } = input;
  const currentUserId = useEffectiveUserId();
  const queryClient = useQueryClient();

  const queryEnabled = enabled && !!sourceEntityId;
  const { data: rows } = useQuery({
    queryKey: ['form-handling-tracker', sourceEntityType, sourceEntityId, entityKey ?? null],
    queryFn: () => getFormHandlingTrackers(sourceEntityType, sourceEntityId as string),
    enabled: queryEnabled,
  });

  const activeRow = (rows ?? []).find((t) => !t.is_resolved) ?? null;
  const tracker = toLockTracker(activeRow);

  const state = resolveHandlingLockState({
    activeTracker: tracker,
    currentUserId,
    isEligible: Boolean(activeRow?.viewer_eligible),
    isAdmin: Boolean(activeRow?.viewer_is_admin),
    flagEnabledForType: Boolean(activeRow?.flag_enabled),
  });

  const invalidate = () => {
    // Refetch the lock state + the escalation-banner tracker query (keyed on entity status).
    queryClient.invalidateQueries({
      queryKey: ['form-handling-tracker', sourceEntityType, sourceEntityId],
    });
    queryClient.invalidateQueries({ queryKey: ['form-sla-trackers'] });
  };

  const claimMutation = useMutation({
    mutationFn: () => claimHandling(activeRow!.tracking_id),
    onSuccess: () => {
      toast.success("You're now handling this form.");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const takeOverMutation = useMutation({
    // ALWAYS pass the current holder's id — the backend 409s on a null/mismatched expectation.
    mutationFn: () => takeOverHandling(activeRow!.tracking_id, activeRow?.handled_by_id ?? null),
    onSuccess: () => {
      toast.success('You have taken over handling.');
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const releaseMutation = useMutation({
    mutationFn: () => releaseHandling(activeRow!.tracking_id),
    onSuccess: () => {
      toast.success('Handling released.');
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return {
    state,
    businessCtasEnabled: businessCtasEnabledForState(state),
    tracker,
    banner: state === 'not_escalated' ? null : { state, tracker },
    claim: () => {
      if (activeRow) claimMutation.mutate();
    },
    takeOver: () => {
      if (activeRow) takeOverMutation.mutate();
    },
    release: () => {
      if (activeRow) releaseMutation.mutate();
    },
    isMutating:
      claimMutation.isPending || takeOverMutation.isPending || releaseMutation.isPending,
  };
}
