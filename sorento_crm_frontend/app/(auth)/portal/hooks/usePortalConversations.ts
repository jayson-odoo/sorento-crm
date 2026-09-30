'use client';

import { useCallback, useEffect, useState } from 'react';
import type { LandingSort } from '../lib/landing-fields';
import { NotASalesAgentError } from '../lib/customer-asks-service';
import {
  CONVERSATION_LIST_LIMIT,
  listConversations,
  type PortalConversation,
} from '../lib/conversations-service';
import {
  DEFAULT_CONVERSATION_SORT,
  normalizeConversationSort,
} from '../lib/conversation-landing';

/** A customer's reply arrives on their schedule: the list re-reads itself while it is open. */
export const CONVERSATION_LIST_POLL_MS = 30_000;

/**
 * The Conversation kind's list state: plain state over the service (the portal runs on a
 * portal token, not the CRM session), like `useCustomerAsksTodo`. One read holds the whole
 * list (an agent's customers with a chat), re-read on a search change and every 30s while the
 * tab is visible, quietly, so a new message moves its card without a spinner.
 */
export function usePortalConversations(search: string) {
  const [rows, setRows] = useState<PortalConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notAgent, setNotAgent] = useState(false);

  const load = useCallback(() => {
    return listConversations({
      page: 1,
      limit: CONVERSATION_LIST_LIMIT,
      q: search,
    })
      .then((page) => {
        setRows(page.data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof NotASalesAgentError) setNotAgent(true);
        else
          setError(
            e instanceof Error ? e.message : 'Failed to load conversations',
          );
      })
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, CONVERSATION_LIST_POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  return { rows, loading, error, notAgent, reload: load };
}

const SORT_KEY_PREFIX = 'sorento.portalConversationSort.';

/**
 * The list's sort, remembered per contact in localStorage (the same pattern as the asks
 * kind's `usePortalAsksSort`: the portal has no user row to key a server preference on).
 */
export function usePortalConversationSort(
  contactId: string | null | undefined,
) {
  const [sort, setSortState] = useState<LandingSort>(DEFAULT_CONVERSATION_SORT);

  useEffect(() => {
    if (!contactId || typeof window === 'undefined') {
      setSortState(DEFAULT_CONVERSATION_SORT);
      return;
    }
    try {
      const raw = window.localStorage.getItem(`${SORT_KEY_PREFIX}${contactId}`);
      setSortState(normalizeConversationSort(raw ? JSON.parse(raw) : null));
    } catch {
      setSortState(DEFAULT_CONVERSATION_SORT);
    }
  }, [contactId]);

  const setSort = useCallback(
    (next: LandingSort) => {
      setSortState(next);
      if (contactId && typeof window !== 'undefined') {
        window.localStorage.setItem(
          `${SORT_KEY_PREFIX}${contactId}`,
          JSON.stringify(next),
        );
      }
    },
    [contactId],
  );

  return [sort, setSort] as const;
}
