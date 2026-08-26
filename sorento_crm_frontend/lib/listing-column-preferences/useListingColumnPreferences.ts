'use client';

import { Table } from '@tanstack/react-table';
import { useEffect, useMemo, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { debounce } from '@/lib/helpers';
import {
  getUserListColumnConfig,
  resetUserListColumnConfig,
  upsertUserListColumnConfig,
  type UserListColumnConfigPayload,
  type UserListColumnConfigResponse,
} from './listColumnPreferencesService';
import { mergeColumnOrderWithLeafColumns } from './mergeColumnOrder';

type ColumnVisibilityState = Record<string, boolean>;
type ColumnStateFromTanStack = {
  columnOrder?: string[];
  columnVisibility?: ColumnVisibilityState;
  columnSizing?: Record<string, number>;
};

function stableStringify(value: unknown): string {
  if (value === undefined) return 'undefined';
  if (value === null) return 'null';
  // Ensure deterministic ordering for objects.
  if (typeof value === 'object' && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return JSON.stringify(keys.reduce((acc, k) => ((acc[k] = obj[k]), acc), {} as Record<string, unknown>));
  }
  return JSON.stringify(value);
}

/**
 * One comparable string for the three column keys, insensitive to key ORDER.
 *
 * `stableStringify` only sorts the top level, and both the applied config and the payload
 * about to be saved build their visibility/sizing maps by iterating the column model - so a
 * plain JSON compare would report a difference the moment a column moved.
 */
function columnStateFingerprint(state: {
  columnOrder: string[];
  columnVisibility: ColumnVisibilityState;
  columnSizing: Record<string, number>;
}): string {
  const record = (obj: Record<string, unknown>) =>
    Object.keys(obj)
      .sort()
      .map((k) => `${k}=${String(obj[k])}`)
      .join(',');
  return [
    state.columnOrder.join('|'),
    record(state.columnVisibility),
    record(state.columnSizing),
  ].join(';');
}

export function useListingColumnPreferences<TData extends object>({
  table,
  listingKey,
  debounceMs = 800,
}: {
  table: Table<TData>;
  listingKey?: string | null;
  debounceMs?: number;
}) {
  const key = (listingKey || '').trim();
  const queryClient = useQueryClient();

  const defaultOrder = useMemo(() => {
    const stateOrder = (table.getState() as ColumnStateFromTanStack)?.columnOrder;
    if (Array.isArray(stateOrder) && stateOrder.length > 0) return [...stateOrder];
    return table.getAllLeafColumns().map((c) => c.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // capture once at mount

  const defaultVisibility = useMemo(() => {
    const out: ColumnVisibilityState = {};
    for (const c of table.getAllLeafColumns()) {
      if (c.getCanHide()) out[c.id] = c.getIsVisible();
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // capture once at mount

  const defaultSizing = useMemo(() => {
    const out: Record<string, number> = {};
    for (const c of table.getAllLeafColumns()) {
      if (c.getCanResize()) out[c.id] = c.getSize();
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // capture once at mount

  const appliedRef = useRef(false);
  const skipSaveOnceRef = useRef(false);
  /**
   * The column state the SERVER already holds, as the save effect below would fingerprint
   * it. A payload identical to this one is never written.
   *
   * `skipSaveOnceRef` alone was not enough: the save effect runs once in the same commit as
   * the apply effect (with the PRE-apply fingerprints, since a render has not happened yet),
   * and that run consumed the one-shot flag - so the run that actually carried the applied
   * state saved it. Harmless on a listing whose applied state matched its defaults, and the
   * reason column ORDER regressed on the report screen, where it did not.
   */
  const persistedRef = useRef<string | null>(null);

  const { data: saved, isFetching } = useQuery({
    queryKey: ['list-column-config', key],
    queryFn: () => getUserListColumnConfig(key),
    enabled: Boolean(key),
    staleTime: Infinity,
    retry: 0,
  });

  // Apply saved config to the TanStack table.
  useEffect(() => {
    if (!key) return;
    if (!saved) return;
    if (appliedRef.current) return;

    const payload = saved.config as UserListColumnConfigPayload | null;
    if (!payload) {
      appliedRef.current = true;
      return;
    }

    const canHideIds = new Set(table.getAllLeafColumns().filter((c) => c.getCanHide()).map((c) => c.id));
    const leafIds = table.getAllLeafColumns().map((c) => c.id);

    // Filled with the value each set below actually applies, so the state the table will
    // hold once they commit can be recorded as "what the server has".
    const orderBeforeApply = (table.getState() as ColumnStateFromTanStack)?.columnOrder;
    let appliedOrder = mergeColumnOrderWithLeafColumns(
      Array.isArray(orderBeforeApply) && orderBeforeApply.length > 0 ? orderBeforeApply : leafIds,
      leafIds,
    );
    let appliedSizing: Record<string, number> | null = null;

    if (Array.isArray(payload.columnOrder) && payload.columnOrder.length > 0) {
      const allowed = new Set(leafIds);
      const filteredOrder = payload.columnOrder.filter((id) => allowed.has(id));
      const mergedOrder = mergeColumnOrderWithLeafColumns(filteredOrder, leafIds);
      appliedOrder = mergedOrder;
      skipSaveOnceRef.current = true;
      table.setColumnOrder(mergedOrder);
    }

    if (payload.columnVisibility && typeof payload.columnVisibility === 'object') {
      // MERGE over the listing's own defaults, never replace them. A saved payload
      // predates any column added since it was written, so replacing would silently
      // reveal every new column to users who happen to have a saved config - a column
      // the listing deliberately ships hidden would appear for them and stay hidden
      // for everyone else. Only ids the payload actually mentions are overridden.
      const filteredVisibility: ColumnVisibilityState = {
        ...((table.getState() as ColumnStateFromTanStack)?.columnVisibility ?? {}),
      };
      for (const [colId, visible] of Object.entries(payload.columnVisibility as Record<string, unknown>)) {
        if (canHideIds.has(colId)) filteredVisibility[colId] = Boolean(visible);
      }
      skipSaveOnceRef.current = true;
      table.setColumnVisibility(filteredVisibility);
    }

    if (payload.columnSizing && typeof payload.columnSizing === 'object') {
      const canResizeIds = new Set(table.getAllLeafColumns().filter((c) => c.getCanResize()).map((c) => c.id));
      const filteredSizing: Record<string, number> = {};
      for (const [colId, size] of Object.entries(payload.columnSizing as Record<string, unknown>)) {
        if (!canResizeIds.has(colId)) continue;
        const n = typeof size === 'number' ? size : Number(size);
        if (Number.isFinite(n) && n > 0) filteredSizing[colId] = n;
      }
      appliedSizing = filteredSizing;
      skipSaveOnceRef.current = true;
      table.setColumnSizing(filteredSizing);
    }

    // The state the three sets above leave behind, derived exactly as the save effect
    // derives its payload: a hideable column keeps its current visibility unless the
    // payload names it, and a resizable column falls back to its own size unless the
    // payload sizes it.
    const appliedVisibility: ColumnVisibilityState = {};
    for (const c of table.getAllLeafColumns()) {
      if (!c.getCanHide()) continue;
      const fromPayload = (payload.columnVisibility as Record<string, unknown> | undefined)?.[c.id];
      appliedVisibility[c.id] = fromPayload === undefined ? c.getIsVisible() : Boolean(fromPayload);
    }
    const appliedSizes: Record<string, number> = {};
    for (const c of table.getAllLeafColumns()) {
      if (!c.getCanResize()) continue;
      appliedSizes[c.id] = appliedSizing?.[c.id] ?? c.getSize();
    }
    persistedRef.current = columnStateFingerprint({
      columnOrder: appliedOrder,
      columnVisibility: appliedVisibility,
      columnSizing: appliedSizes,
    });

    appliedRef.current = true;
  }, [key, saved, table]);

  const columnOrderState = (table.getState() as ColumnStateFromTanStack)?.columnOrder;
  const columnVisibilityState = (table.getState() as ColumnStateFromTanStack)?.columnVisibility;
  const columnSizingState = (table.getState() as ColumnStateFromTanStack)?.columnSizing;

  // Fingerprints must be derived from the current column model values (not state object references),
  // because TanStack can mutate `table.getState()` in-place and React won't reliably detect changes.
  const orderFingerprint = useMemo(() => {
    const leafIds = table.getAllLeafColumns().map((c) => c.id);
    const raw =
      Array.isArray(columnOrderState) && columnOrderState.length > 0 ? columnOrderState : leafIds;
    return stableStringify(mergeColumnOrderWithLeafColumns(raw, leafIds));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, stableStringify(columnOrderState)]);

  const visibilityFingerprint = useMemo(() => {
    const canHideCols = table.getAllLeafColumns().filter((c) => c.getCanHide());
    const vis: ColumnVisibilityState = {};
    for (const c of canHideCols) {
      vis[c.id] = c.getIsVisible();
    }
    return stableStringify(vis);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, stableStringify(columnVisibilityState)]);

  const sizingFingerprint = useMemo(() => {
    const canResizeCols = table.getAllLeafColumns().filter((c) => c.getCanResize());
    const canResizeIds = new Set(canResizeCols.map((c) => c.id));

    // TanStack may mutate state objects in-place; fingerprint uses stableStringify on the current sizing values.
    const sizing: Record<string, number> = {};
    for (const c of canResizeCols) {
      const raw = columnSizingState?.[c.id];
      const n = typeof raw === 'number' ? raw : Number(raw);
      if (canResizeIds.has(c.id) && Number.isFinite(n) && n > 0) sizing[c.id] = n;
      else sizing[c.id] = c.getSize();
    }

    return stableStringify(sizing);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, stableStringify(columnSizingState)]);

  const upsertMutation = useMutation({
    mutationFn: (payload: UserListColumnConfigPayload) => upsertUserListColumnConfig(key, payload),
    /**
     * Seed the cache with the row the write returned, rather than invalidating: we
     * already know the value, and a refetch would race the debounce.
     *
     * The query is `staleTime: Infinity` and nothing invalidated it, so a re-mount
     * within the same SPA session re-read the PRE-save config and re-applied the OLD
     * columns. Rarely noticed here (few people reorder columns and come straight
     * back), but `useListingViewPreferences` shares this cache entry and its sort and
     * filter change constantly, where the same staleness reads as "it forgot my
     * filter". PLAN-listing-view-memory 3.3.
     *
     * Seeding the RESPONSE, not the payload, is what makes this safe: the endpoint
     * merges, so the response carries the view keys this hook never sends. Seeding
     * the partial body would drop them and re-create the clobber in the cache.
     */
    onSuccess: (result: UserListColumnConfigResponse) => {
      if (!key) return;
      queryClient.setQueryData(['list-column-config', key], result);
    },
  });

  const debouncedSaveRef = useRef(
    debounce((payload: unknown) => {
      upsertMutation.mutate(payload as UserListColumnConfigPayload);
    }, debounceMs),
  );

  useEffect(() => {
    if (!key) return;
    if (isFetching) return;
    if (!appliedRef.current) return;
    if (skipSaveOnceRef.current) {
      skipSaveOnceRef.current = false;
      return;
    }

    const leafIds = table.getAllLeafColumns().map((c) => c.id);
    const rawOrder =
      Array.isArray(columnOrderState) && columnOrderState.length > 0
        ? columnOrderState
        : leafIds;
    const filteredOrder = mergeColumnOrderWithLeafColumns(rawOrder, leafIds);

    const canHideCols = table.getAllLeafColumns().filter((c) => c.getCanHide());
    const filteredVisibility: ColumnVisibilityState = {};
    for (const c of canHideCols) {
      filteredVisibility[c.id] = c.getIsVisible();
    }

    const canResizeCols = table.getAllLeafColumns().filter((c) => c.getCanResize());
    const filteredSizing: Record<string, number> = {};
    for (const c of canResizeCols) {
      filteredSizing[c.id] = c.getSize();
    }

    // Never write back what the server already holds. Reconciling an order against the
    // columns currently on screen (a report's tick columns are data-dependent) or simply
    // re-deriving the same state on a re-render must not count as a change the user made.
    const fingerprint = columnStateFingerprint({
      columnOrder: filteredOrder,
      columnVisibility: filteredVisibility,
      columnSizing: filteredSizing,
    });
    if (persistedRef.current === fingerprint) return;
    persistedRef.current = fingerprint;

    const payload: UserListColumnConfigPayload = {
      version: 1,
      columnOrder: filteredOrder,
      columnVisibility: filteredVisibility,
      columnSizing: filteredSizing,
    };
    debouncedSaveRef.current(payload);
  }, [key, orderFingerprint, visibilityFingerprint, sizingFingerprint, isFetching, table]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetMutation = useMutation({
    mutationFn: () => resetUserListColumnConfig(key),
    // The row is gone, so the seeded cache entry must go with it - otherwise a
    // re-mount would re-apply the config the user just reset.
    onSuccess: () => {
      if (!key) return;
      queryClient.setQueryData(['list-column-config', key], {
        listing_key: key,
        config: null,
      } satisfies UserListColumnConfigResponse);
    },
  });

  const resetToDefaults = async () => {
    if (!key) return;
    // Prevent the reset operation from being immediately persisted back as "saved defaults"
    // - the row is about to be DELETED, so re-creating it with the defaults would undo it.
    skipSaveOnceRef.current = true;
    persistedRef.current = columnStateFingerprint({
      columnOrder: mergeColumnOrderWithLeafColumns(
        defaultOrder,
        table.getAllLeafColumns().map((c) => c.id),
      ),
      columnVisibility: defaultVisibility,
      columnSizing: defaultSizing,
    });
    table.setColumnOrder(defaultOrder);
    table.setColumnVisibility(defaultVisibility);
    table.setColumnSizing(defaultSizing);
    await resetMutation.mutateAsync();
  };

  return {
    isLoading: Boolean(key) && !appliedRef.current,
    isFetching,
    resetToDefaults,
  };
}

