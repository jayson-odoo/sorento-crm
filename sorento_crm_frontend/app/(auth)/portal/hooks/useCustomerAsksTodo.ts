'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from '@/lib/toast';
import { DEFAULT_ASK_SORT, normalizeAskSort, type AskTodoPayload } from '@/lib/stock-asks-todo';
import type { LandingSort } from '../lib/landing-fields';
import {
  NotASalesAgentError,
  getAskConversationPage,
  getCustomerAsksTodo,
  searchAskConversation,
  updateCustomerAsk,
} from '../lib/customer-asks-service';
import type { StockAskPatch } from '@/lib/stock-asks';
import { useAskThread, type AskThreadService } from '@/hooks/useAskThread';

/** The portal-keyed pair of thread loaders (a module constant, so the hook sees one identity). */
const PORTAL_ASK_THREAD: AskThreadService = { getPage: getAskConversationPage, search: searchAskConversation };

/** The opened ask's contact thread, read on the portal token (ASKS-UX item 3). */
export function usePortalAskThread(askId: string | null) {
  return useAskThread(askId, PORTAL_ASK_THREAD, 'portal-customer-ask');
}

/**
 * The portal's to-do state: plain state over the service (the portal runs on a portal token,
 * not the CRM session): load once, refetch quietly after every Done / Reopen / Note so the row
 * moves without a spinner.
 */
export function useCustomerAsksTodo() {
  const [payload, setPayload] = useState<AskTodoPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notAgent, setNotAgent] = useState(false);
  /** Bumped after each write so the Show done history reloads too. */
  const [version, setVersion] = useState(0);
  /** The ask whose PATCH is in flight; its Done / Reopen button is disabled meanwhile. */
  const [pendingAskId, setPendingAskId] = useState<string | null>(null);

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
    (askId: string, patch: StockAskPatch) => {
      setPendingAskId(askId);
      return updateCustomerAsk(askId, patch)
        .then(() => load())
        .then(() => setVersion((v) => v + 1))
        .catch((e: unknown) => toast.error(e instanceof Error ? e.message : 'Failed to update the ask'))
        .finally(() => setPendingAskId(null));
    },
    [load],
  );

  return {
    payload,
    loading,
    error,
    notAgent,
    version,
    pendingAskId,
    done: (askId: string) => save(askId, { state: 'done' }),
    reopen: (askId: string) => save(askId, { state: 'open' }),
    /** Rejects when the save fails (after toasting), so the opened card shows "Saved" only when it was. */
    note: async (askId: string, note: string) => {
      setPendingAskId(askId);
      try {
        await updateCustomerAsk(askId, { note });
        await load();
        setVersion((v) => v + 1);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Failed to update the ask');
        throw e;
      } finally {
        setPendingAskId(null);
      }
    },
  };
}

const SORT_KEY_PREFIX = 'sorento.portalAsksSort.';

/**
 * The to-do's sort, remembered per contact in localStorage (the landing's default-tab pattern,
 * `sorento.portalDefaultTab.<contact_id>`); the portal has no user row to key a server
 * preference on. A stored value that names no field of the asks kind reads as the default.
 */
export function usePortalAsksSort(contactId: string | null | undefined) {
  const [sort, setSortState] = useState<LandingSort>(DEFAULT_ASK_SORT);

  useEffect(() => {
    if (!contactId || typeof window === 'undefined') {
      setSortState(DEFAULT_ASK_SORT);
      return;
    }
    try {
      const raw = window.localStorage.getItem(`${SORT_KEY_PREFIX}${contactId}`);
      setSortState(normalizeAskSort(raw ? JSON.parse(raw) : null));
    } catch {
      setSortState(DEFAULT_ASK_SORT);
    }
  }, [contactId]);

  const setSort = useCallback(
    (next: LandingSort) => {
      setSortState(next);
      if (contactId && typeof window !== 'undefined') {
        window.localStorage.setItem(`${SORT_KEY_PREFIX}${contactId}`, JSON.stringify(next));
      }
    },
    [contactId],
  );

  return [sort, setSort] as const;
}
