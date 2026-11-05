'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { localStore } from '@/lib/storage';
import {
  upsertUserListColumnConfig,
  type ListViewMode,
  type UserListColumnConfigResponse,
} from './listColumnPreferencesService';
import {
  USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX,
  useUserListColumnConfigQuery,
} from './useUserListColumnConfigQuery';

/**
 * Remembers which view (board / grid / list) a user left a page in, PER USER, on the
 * server: the `view` key of the same `user_list_column_configs` row the listing's
 * columns, sort and page size already live in. A browser-only memory did not follow
 * the user to another device or origin (PROJECTS-BOARD-VIEW-PREF, 5 Nov 2026).
 *
 * - Nothing stored: `defaultView`, and nothing is written until the user picks.
 * - `legacyStorageKey`: the browser value an older build wrote, read only when the
 *   server holds nothing, so nobody loses the pick they already made.
 * - `isLoading` stays true until the stored view is known, so a page can hold its
 *   data query and fetch once, in the right view. A failed read resolves as "nothing
 *   stored" rather than never resolving.
 * - The PUT is a partial merge, so writing `view` leaves the other keys alone; its
 *   fully merged response seeds the shared cache entry.
 */
export function useListingViewMode<T extends ListViewMode>({
  listingKey,
  allowed,
  defaultView,
  legacyStorageKey,
}: {
  listingKey: string;
  allowed: readonly T[];
  defaultView: T;
  legacyStorageKey?: string;
}): { view: T; setView: (next: T) => void; isLoading: boolean } {
  const key = listingKey.trim();
  const queryClient = useQueryClient();
  const { data: saved, isError: loadFailed } = useUserListColumnConfigQuery(key);
  const [view, setViewState] = useState<T>(defaultView);
  const [applied, setApplied] = useState(false);
  const appliedRef = useRef(false);
  const allowedRef = useRef(allowed);
  // The view on screen once known, so re-clicking it writes nothing.
  const shownRef = useRef<T | null>(null);

  useEffect(() => {
    if (appliedRef.current) return;
    if (!saved && !loadFailed) return;
    const isAllowed = (v: unknown): v is T =>
      typeof v === 'string' && (allowedRef.current as readonly string[]).includes(v);
    const stored = saved?.config?.view;
    const legacy = legacyStorageKey ? localStore.getItem(legacyStorageKey) : null;
    const initial = isAllowed(stored) ? stored : isAllowed(legacy) ? legacy : null;
    if (initial) setViewState(initial);
    shownRef.current = initial ?? null;
    appliedRef.current = true;
    setApplied(true);
  }, [saved, loadFailed, legacyStorageKey]);

  const upsert = useMutation({
    mutationFn: (next: T) => upsertUserListColumnConfig(key, { view: next }),
    onSuccess: (result: UserListColumnConfigResponse) => {
      queryClient.setQueryData([USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX, key], result);
    },
  });
  const mutate = upsert.mutate;

  const setView = useCallback(
    (next: T) => {
      if (shownRef.current === next) return;
      shownRef.current = next;
      // A pick made before the stored value arrived wins over it.
      appliedRef.current = true;
      setApplied(true);
      setViewState(next);
      mutate(next);
    },
    [mutate],
  );

  return { view, setView, isLoading: !applied };
}
