'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from '@/lib/toast';
import { DEFAULT_ASK_SORT, normalizeSort, type AskSort, type AskTodoPayload } from '@/lib/stock-asks-todo';
import { NotASalesAgentError, getCustomerAsksTodo, updateCustomerAsk } from '../lib/customer-asks-service';
import type { StockAskPatch } from '@/lib/stock-asks';

/**
 * The portal's to-do state. The portal has no QueryClient (it runs on a portal token, outside
 * the CRM session), so this is plain state over the service: load once, refetch quietly after
 * every Done / Reopen / Note so the row moves without a spinner.
 */
export function useCustomerAsksTodo() {
  const [payload, setPayload] = useState<AskTodoPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notAgent, setNotAgent] = useState(false);
  /** Bumped after each write so the Show done history reloads too. */
  const [version, setVersion] = useState(0);

  const load = useCallback(() => {
    return getCustomerAsksTodo()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof NotASalesAgentError) setNotAgent(true);
        else setError(e instanceof Error ? e.message : 'Failed to load customer asks');
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = useCallback(
    (askId: string, patch: StockAskPatch) =>
      updateCustomerAsk(askId, patch)
        .then(() => load())
        .then(() => setVersion((v) => v + 1))
        .catch((e: unknown) => toast.error(e instanceof Error ? e.message : 'Failed to update the ask')),
    [load],
  );

  return {
    payload,
    loading,
    error,
    notAgent,
    version,
    done: (askId: string) => save(askId, { state: 'done' }),
    reopen: (askId: string) => save(askId, { state: 'open' }),
    note: (askId: string, note: string) => save(askId, { note }),
  };
}

const SORT_KEY_PREFIX = 'sorento.portalAsksSort.';

/**
 * The to-do's sort, remembered per contact in localStorage (the landing's default-tab pattern,
 * `sorento.portalDefaultTab.<contact_id>`); the portal has no user row to key a server
 * preference on. A stored value that is not one of the choices reads as the default.
 */
export function usePortalAsksSort(contactId: string | null | undefined) {
  const [sort, setSortState] = useState<AskSort>(DEFAULT_ASK_SORT);

  useEffect(() => {
    if (!contactId || typeof window === 'undefined') {
      setSortState(DEFAULT_ASK_SORT);
      return;
    }
    try {
      const raw = window.localStorage.getItem(`${SORT_KEY_PREFIX}${contactId}`);
      setSortState(normalizeSort(raw ? JSON.parse(raw) : null));
    } catch {
      setSortState(DEFAULT_ASK_SORT);
    }
  }, [contactId]);

  const setSort = useCallback(
    (next: AskSort) => {
      setSortState(next);
      if (contactId && typeof window !== 'undefined') {
        window.localStorage.setItem(`${SORT_KEY_PREFIX}${contactId}`, JSON.stringify(next));
      }
    },
    [contactId],
  );

  return [sort, setSort] as const;
}
