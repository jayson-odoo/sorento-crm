'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useIsFetching, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

import {
  ctasDisabledForView,
  resolveFormActionView,
  watchedOutcome,
  type FormActionOutcome,
  type FormActionView,
} from './formAction';
import {
  cancelFormAction,
  getCurrentFormAction,
  getUndoEligibility,
  undoFormAction,
} from './formActionService';
import {
  FORM_ACTION_FIXTURES,
  isFormActionScenario,
} from './__mocks__/formActions';
import type { FormSLASourceType } from './formSLAService';

/* -------------------------------------------------------------------------------------
 * Live against the API. `?formActionMock=<scenario>` still short-circuits to a fixture -
 * it is how the nine UI states stay reachable in a browser without contriving real data,
 * and it is inert unless the query param is present.
 * ----------------------------------------------------------------------------------- */

export interface UseFormActionInput {
  sourceEntityType: FormSLASourceType;
  sourceEntityId: string | null | undefined;
  /** Extra key segment so the read refetches when the entity itself changes. */
  entityKey?: string | number | Date | null;
  enabled?: boolean;
}

export interface UseFormActionResult {
  view: FormActionView;
  ctasDisabled: boolean;
  cancel: () => void;
  undo: (reason: string) => void;
  refresh: () => void;
  isMutating: boolean;
}

export function useFormAction(input: UseFormActionInput): UseFormActionResult {
  const { sourceEntityType, sourceEntityId, entityKey, enabled = true } = input;
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const scenario = searchParams?.get('formActionMock') ?? null;
  const mocked = isFormActionScenario(scenario);

  const queryEnabled = enabled && !!sourceEntityId && !mocked;

  const { data: current } = useQuery({
    queryKey: ['form-action-current', sourceEntityType, sourceEntityId, entityKey ?? null],
    queryFn: () => getCurrentFormAction(sourceEntityType, sourceEntityId as string),
    enabled: queryEnabled,
    // While an action is pending the server is the clock; poll so the commit shows up
    // without the user reloading.
    refetchInterval: (query) => (query.state.data?.pending ? 2000 : false),
  });

  const { data: eligibility } = useQuery({
    queryKey: ['form-action-eligibility', sourceEntityType, sourceEntityId, entityKey ?? null],
    queryFn: () => getUndoEligibility(sourceEntityType, sourceEntityId as string),
    enabled: queryEnabled,
  });

  // Ticks the view from `pending` into `committing` when commit_at passes.
  const [now, setNow] = useState(() => Date.now());
  const lastPendingId = useRef<string | null>(null);
  // The window closes server-side, so `pending` goes null a beat BEFORE the entity
  // refetch lands. Without holding the CTAs down across that gap the old Approve /
  // Reject buttons flash back for a moment - long enough to mis-click.
  const [settling, setSettling] = useState(false);
  const pending = mocked
    ? FORM_ACTION_FIXTURES[scenario!].pending
    : (current?.pending ?? null);

  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [pending]);

  /** Refetch everything keyed on this form, not just our own reads. */
  const invalidateEntity = useCallback(() => {
    queryClient.invalidateQueries({
      // The entity's own query key differs per form type ('purchase-request',
      // 'complaint', ...), so match on the id instead of naming each one.
      predicate: (query) =>
        Array.isArray(query.queryKey) &&
        query.queryKey.some((part) => part === sourceEntityId),
    });
  }, [queryClient, sourceEntityId]);

  const invalidate = useCallback(() => {
    // `refresh` doubles as the outcome dismiss (the banner's onDismissOutcome).
    setOutcome(null);
    queryClient.invalidateQueries({ queryKey: ['form-action-current'] });
    queryClient.invalidateQueries({ queryKey: ['form-action-eligibility'] });
    // The lock banner and the SLA banner are separate queries; a reversal moves the
    // stage, so both must refetch or one of them lags a reload.
    queryClient.invalidateQueries({ queryKey: ['form-handling-tracker'] });
    queryClient.invalidateQueries({ queryKey: ['form-sla-trackers'] });
    invalidateEntity();
  }, [queryClient, invalidateEntity]);

  // A parked action that did NOT apply (voided under a changed premise, or failed at
  // commit) must say so - `pending` just going null looks identical to success, and
  // the user walks away believing their action landed. The server reports the most
  // recent terminal outcome; it is shown only when it belongs to the action THIS
  // viewer was watching, and dismissed client-side.
  const [outcome, setOutcome] = useState<FormActionOutcome | null>(null);

  // The grace window closes on the SERVER - by a sweep, or by the lazy commit inside
  // the poll below. Either way the first the client hears of it is `pending` going
  // null, and without this the page keeps rendering the pre-action state (stale
  // Approve / Reject buttons) until someone reloads.
  useEffect(() => {
    const currentId = pending?.id ?? null;
    if (lastPendingId.current && !currentId) {
      setSettling(true);
      invalidateEntity();
      const terminal = watchedOutcome(current?.last_outcome, lastPendingId.current);
      if (terminal) setOutcome(terminal);
    }
    if (currentId) setOutcome(null);
    lastPendingId.current = currentId;
  }, [pending, current, invalidateEntity]);

  // Release the CTAs only once the refetch this triggered has actually finished.
  const entityFetching = useIsFetching({
    predicate: (query) =>
      Array.isArray(query.queryKey) &&
      query.queryKey.some((part) => part === sourceEntityId),
  });
  useEffect(() => {
    if (settling && entityFetching === 0) setSettling(false);
  }, [settling, entityFetching]);

  const cancelMutation = useMutation({
    mutationFn: (actionId: string) => cancelFormAction(actionId),
    onSuccess: () => {
      toast.success('Action withdrawn. Nothing was sent.');
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const undoMutation = useMutation({
    mutationFn: (reason: string) =>
      undoFormAction(sourceEntityType, sourceEntityId as string, reason),
    onSuccess: () => {
      toast.success('Action reversed. Everyone involved has been notified.');
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const view = resolveFormActionView({
    pending,
    outcome: mocked ? FORM_ACTION_FIXTURES[scenario!].outcome : outcome,
    eligibility: mocked
      ? FORM_ACTION_FIXTURES[scenario!].eligibility
      : (eligibility ?? null),
    now,
  });

  return {
    view,
    ctasDisabled: ctasDisabledForView(view) || settling,
    cancel: () => {
      if (pending) cancelMutation.mutate(pending.id);
    },
    undo: (reason: string) => {
      if (reason.trim()) undoMutation.mutate(reason);
    },
    refresh: invalidate,
    isMutating: cancelMutation.isPending || undoMutation.isPending,
  };
}
