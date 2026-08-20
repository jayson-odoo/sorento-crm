'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { OnChangeFn, SortingState } from '@tanstack/react-table';
import { debounce } from '@/lib/helpers';
import type {
  ListSortEntry,
  UserListColumnConfigPayload,
  UserListColumnConfigResponse,
} from './listColumnPreferencesService';
// TODO(phase-2): THE SEAM. Swap these two for `getUserListColumnConfig` /
// `upsertUserListColumnConfig` from './listColumnPreferencesService' and swap
// VIEW_QUERY_KEY_PREFIX for 'list-column-config' (see below). Nothing else in this
// file changes.
import { readListViewPreferences, writeListViewPreferences } from './listViewPreferencesStub';

/**
 * Remembers the sort and the filter a user left a listing in, per user, per listing.
 *
 * Sits beside `useListingColumnPreferences` (which owns column order / visibility /
 * width from inside DataGrid) and follows the same shape: fetch once, apply once via
 * `appliedRef`, never write back what it just applied, debounce every later change by
 * 800ms. It guards that write with a fingerprint rather than the column hook's one-shot
 * flag - see `persistedFingerprintRef` for why the flag is not sufficient here.
 *
 * The `filters` blob is opaque to this hook: the page owns its shape and declares a
 * `filtersVersion`. A stored blob written by an older shape is DISCARDED rather than
 * applied, so refactoring a page's filter cannot break the listing for the users who
 * had a filter saved (AC-B4).
 *
 * `isLoading` stays true until the stored view has been applied, so the page can gate
 * its data query and fetch exactly once, already filtered and sorted (AC-B3).
 */

// TODO(phase-2): becomes 'list-column-config', the key the column hook already uses,
// so both hooks share a single GET of the single row. It is separate in Phase 1 only
// because the column hook talks to the real endpoint while this one talks to the stub.
const VIEW_QUERY_KEY_PREFIX = 'list-view-config';

function stableStringify(value: unknown): string {
  if (value === undefined) return 'undefined';
  if (value === null) return 'null';
  if (typeof value === 'object' && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return JSON.stringify(
      keys.reduce((acc, k) => ((acc[k] = obj[k]), acc), {} as Record<string, unknown>),
    );
  }
  return JSON.stringify(value);
}

/** Keeps only well-formed `{id, desc}` entries; a malformed blob applies nothing. */
function parseStoredSorting(raw: unknown): SortingState | null {
  if (!Array.isArray(raw)) return null;
  const parsed: SortingState = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== 'object') continue;
    const { id, desc } = entry as { id?: unknown; desc?: unknown };
    if (typeof id !== 'string' || !id) continue;
    parsed.push({ id, desc: Boolean(desc) });
  }
  return parsed.length > 0 ? parsed : null;
}

export function useListingViewPreferences<TFilters extends Record<string, unknown>>({
  listingKey,
  defaultSorting,
  filtersVersion,
  debounceMs = 800,
}: {
  listingKey?: string | null;
  defaultSorting: SortingState;
  /** Bump when the page changes the shape of what it puts in `filters`. */
  filtersVersion: number;
  debounceMs?: number;
}): {
  sorting: SortingState;
  setSorting: OnChangeFn<SortingState>;
  filters: TFilters | null;
  setFilters: (next: TFilters | null) => void;
  isLoading: boolean;
} {
  const key = (listingKey || '').trim();
  const queryClient = useQueryClient();

  // Captured once: the page re-creates the array literal on every render.
  const defaultSortingRef = useRef<SortingState>(defaultSorting);

  const [sorting, setSortingState] = useState<SortingState>(defaultSortingRef.current);
  const [filters, setFiltersState] = useState<TFilters | null>(null);
  // Mirrored into state as well as a ref: the ref guards the effects, the state is
  // what makes `isLoading` flip for a user who has nothing stored (applying nothing
  // renders nothing, so a ref alone would leave the page gated forever).
  const [applied, setApplied] = useState(false);
  const appliedRef = useRef(false);
  /**
   * Fingerprint of the view as last READ from storage or last WRITTEN to it. A save
   * runs only when the current view differs from it.
   *
   * The column hook's one-shot `skipSaveOnceRef` is not enough here and was measured
   * failing: its applies all land in a single commit, whereas ours set React state, so
   * the save effect runs twice (once when `applied` flips, once when the applied state
   * lands) and, under StrictMode's double-invoked effects, twice more. The first run
   * ate the flag and the second wrote - which erased a version-mismatched blob that
   * AC-B4 says to leave alone, and wrote a config for a first-time user, which AC-B2
   * forbids. Comparing by value cannot be consumed by an extra render.
   */
  const persistedFingerprintRef = useRef<string | null>(null);

  const { data: saved } = useQuery({
    queryKey: [VIEW_QUERY_KEY_PREFIX, key],
    queryFn: () => readListViewPreferences(key),
    enabled: Boolean(key),
    staleTime: Infinity,
    retry: 0,
  });

  const setSorting = useCallback<OnChangeFn<SortingState>>((updater) => {
    setSortingState((prev) => (typeof updater === 'function' ? updater(prev) : updater));
  }, []);

  const setFilters = useCallback((next: TFilters | null) => {
    setFiltersState(next);
  }, []);

  // Apply the stored view once, on first resolve.
  useEffect(() => {
    if (!key) return;
    if (!saved) return;
    if (appliedRef.current) return;

    const payload = saved.config as UserListColumnConfigPayload | null;

    const storedSorting = payload ? parseStoredSorting(payload.sorting) : null;
    const nextSorting = storedSorting ?? defaultSortingRef.current;
    if (storedSorting) setSortingState(storedSorting);

    // A blob from an older filter shape is dropped, not applied (AC-B4). It stays in
    // the row until the user's next filter change overwrites it.
    const storedFilters =
      payload &&
      payload.filters &&
      typeof payload.filters === 'object' &&
      payload.filtersVersion === filtersVersion
        ? (payload.filters as TFilters)
        : null;
    if (storedFilters) setFiltersState(storedFilters);

    // What the listing now shows IS what storage holds, so nothing is written back:
    // not for a first-time user (AC-B2), not for the sort/filter we just applied.
    persistedFingerprintRef.current = stableStringify({
      sorting: nextSorting,
      filters: storedFilters,
    });
    appliedRef.current = true;
    setApplied(true);
  }, [key, saved, filtersVersion]);

  const viewFingerprint = useMemo(
    () => stableStringify({ sorting, filters }),
    [sorting, filters],
  );

  const upsertMutation = useMutation({
    mutationFn: (payload: UserListColumnConfigPayload) => writeListViewPreferences(key, payload),
    // Seed the cache with the row the write returned. The query is `staleTime:
    // Infinity` and nothing invalidates it, so without this a re-mount within the
    // same SPA session re-applies the PRE-save value - it reads as "it forgot my
    // filter", the exact failure this feature exists to prevent (AC-B7, PLAN 3.3).
    onSuccess: (result: UserListColumnConfigResponse) => {
      if (!key) return;
      queryClient.setQueryData([VIEW_QUERY_KEY_PREFIX, key], result);
    },
  });

  const debouncedSaveRef = useRef(
    debounce((arg: unknown) => {
      const { fingerprint, payload } = arg as {
        fingerprint: string;
        payload: UserListColumnConfigPayload;
      };
      // Decided at FIRE time, not at schedule time: a user who toggles a status on and
      // straight back off has changed nothing, and the debounce has already collapsed
      // the two into this single call.
      if (fingerprint === persistedFingerprintRef.current) return;
      persistedFingerprintRef.current = fingerprint;
      upsertMutation.mutate(payload);
    }, debounceMs),
  );

  useEffect(() => {
    if (!key) return;
    if (!appliedRef.current) return;

    const sortingPayload: ListSortEntry[] = sorting.map((s) => ({
      id: s.id,
      desc: Boolean(s.desc),
    }));

    // An explicit null is a CLEAR, not "I am not writing that key" - that is the
    // distinction the chip's Clear affordance needs (AC-A3 / AC-C2). The column keys
    // are deliberately absent from this body: the other writer owns them.
    const payload: UserListColumnConfigPayload = {
      version: 1,
      sorting: sortingPayload.length > 0 ? sortingPayload : null,
      filters: filters ?? null,
      filtersVersion: filters ? filtersVersion : null,
    };
    debouncedSaveRef.current({ fingerprint: viewFingerprint, payload });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, viewFingerprint, applied]);

  return {
    sorting,
    setSorting,
    filters,
    setFilters,
    isLoading: Boolean(key) && !applied,
  };
}
