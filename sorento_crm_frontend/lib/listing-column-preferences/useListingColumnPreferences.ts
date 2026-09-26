'use client';

import { Table } from '@tanstack/react-table';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { debounce } from '@/lib/helpers';
import { MAX_LIST_PAGE_SIZE } from '@/lib/listNavQuery';
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

/**
 * The one predicate that decides whether a `pageSize` is usable - on READ (apply a
 * saved value) and on WRITE (save a size change) alike, per review round 1. Bounded
 * int, NOT a fixed list of sizes: several listings default their own Rows-per-page
 * menu outside 25/50/100 (e.g. 10, `roles/role-list.tsx`), and the BE bound mirrors
 * this exactly (`MAX_LIST_PAGE_SIZE`, `lib/listNavQuery.ts`).
 */
function isValidPageSize(n: unknown): n is number {
  return typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= MAX_LIST_PAGE_SIZE;
}

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
  suppressPersist = false,
}: {
  table: Table<TData>;
  listingKey?: string | null;
  debounceMs?: number;
  /**
   * B1 (PR #489 review round): true while something OTHER than the reader's own
   * hands is driving `columnOrder`/`columnVisibility` - a saved segment applying,
   * for instance (`components/list/SavedViewsMenu.tsx`). Without this, a segment's
   * columns flow through this hook's own save effect and overwrite the reader's
   * personal layout the moment it applies - worse, a PUBLISHED default segment then
   * clobbers EVERY reader's layout on page open, since it auto-applies (AC-4.4).
   */
  suppressPersist?: boolean;
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

  // The caller's own default rows-per-page (the `pageSize` prop `PanelDataGrid` or
  // `useListPager` was given), captured once at mount the same way the three column
  // defaults above are - `resetToDefaults` returns the grid to this, not to a hardcoded
  // number.
  const defaultPageSize = useMemo(() => {
    return table.getState().pagination?.pageSize;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // capture once at mount

  const appliedRef = useRef(false);
  /**
   * State twin of `appliedRef`, read-only outside this hook (`isLoading` below).
   *
   * Review round 2 (SF2) asked for this to be dropped, on the premise that no case
   * exists where it changes the outcome - the reviewer's own example was a `{
   * pageSize: 25 }`-only row against a table already at 25. Re-checked against the
   * two round-1 tests that predate this round, WITHOUT the twin (verified: both fail
   * with `ready-state` stuck at `'loading'`):
   *
   * - Red 2 (a saved `pageSize` OUTSIDE the bound, e.g. 500): no column keys AND an
   *   invalid size apply to nothing, so no `table.set*` call fires.
   * - B2 (no saved row at all, `config: null` - review round 1): the single most
   *   common real case there is, since it is every listing for a user who has never
   *   customized it. Same reason: nothing to apply, no `table.set*` call.
   *
   * The consequence is not cosmetic: `DataGridProvider` defaults `loadingMode` to
   * `'skeleton'` (`components/ui/data-grid.tsx:276`, every grid unless a call site
   * opts out) and `useBodySkeleton` (`data-grid-table.tsx`) draws the skeleton
   * whenever `isColumnPreferencesLoading` is true regardless of `hasRows` - so a
   * `false` `appliedRef` that a ref-only `isLoading` cannot surface until some
   * UNRELATED re-render happens to occur reads, in the worst case (a page nothing
   * else ever re-renders), as a grid stuck on its loading skeleton forever, on the
   * single most common case there is. Kept for this reason; flagged to the captain
   * rather than silently overridden.
   */
  const [applied, setApplied] = useState(false);
  const skipSaveOnceRef = useRef(false);
  // Own one-shot guard for the page-size save effect below, distinct from
  // `skipSaveOnceRef`: the two effects run in the same commit, and a shared flag would
  // be consumed by whichever runs first, leaving the other free to write back the very
  // state the apply effect just set.
  const skipPageSizeSaveOnceRef = useRef(false);
  const persistedPageSizeRef = useRef<number | null>(null);
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
  //
  // `saved.config` is treated as `{}` when there is no row yet (first open) or the row
  // carries no config, NOT as an early return (review round 2, N3): the block below
  // already handles an absent key correctly (each `if (Array.isArray(payload.columnOrder)
  // ...)` guard is a no-op when the key is missing, falling through to the table's own
  // LIVE column model), so running "no saved row" through the exact same path as "a saved
  // row with no column keys" means both agree on what "already saved" means - the live
  // model, not a separate snapshot of the mount-time defaults. Before this, the two
  // branches fingerprinted from different sources and could disagree for a grid whose
  // columns arrive after mount (a report's data-dependent columns).
  useEffect(() => {
    if (!key) return;
    if (!saved) return;
    if (appliedRef.current) return;

    const payload = (saved.config ?? {}) as UserListColumnConfigPayload;

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

    // A saved size outside the bound is dropped, never applied (AC-5) - it can only
    // reach here from a row written before the BE bound existed (or a restore).
    const savedPageSize = payload.pageSize;
    if (isValidPageSize(savedPageSize)) {
      const currentPageSize = table.getState().pagination?.pageSize;
      if (currentPageSize !== savedPageSize) {
        skipPageSizeSaveOnceRef.current = true;
        // S3 (review round 1): TanStack's `setPageSize` keeps the TOP ROW visible
        // (`old.pageSize * old.pageIndex / newPageSize`), it does not reset
        // `pageIndex`. A saved size is a different page boundary, so this hook wants
        // page 1 of it, not wherever the mount-time index happened to land.
        table.setPagination({ pageIndex: 0, pageSize: savedPageSize });
      }
      persistedPageSizeRef.current = savedPageSize;
    } else {
      persistedPageSizeRef.current = table.getState().pagination?.pageSize ?? null;
    }

    appliedRef.current = true;
    setApplied(true);
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

  /**
   * The one payload every save writes into before it is sent, so a column change and a
   * page-size change land in the SAME PUT when they fall inside the same debounce
   * window (review round 2, SF1 - blocker). Two independent debounce instances each
   * still called `upsertMutation.mutate` on their own, which is two concurrent PUTs to
   * the SAME row: the endpoint's read-modify-write
   * (`app/api/v1/list_query.py:296-313`) is not concurrency-safe against itself, so
   * whichever request's SELECT ran first and committed last could silently lose the
   * OTHER request's key, or a first-ever save on a listing (no row yet) could 500 on
   * the row's unique constraint. One writer, one debounce, one merged payload removes
   * the race instead of narrowing it.
   */
  const pendingPayloadRef = useRef<UserListColumnConfigPayload>({});

  const debouncedFlushRef = useRef(
    debounce(() => {
      const payload = pendingPayloadRef.current;
      pendingPayloadRef.current = {};
      if (Object.keys(payload).length === 0) return;

      // Advance the "known-saved" refs only from what is ACTUALLY being sent, not
      // eagerly when an effect merges a key in - a key that gets merged in and then
      // changes back before this flush fires must not be recorded as saved when it
      // was never written.
      if (
        payload.columnOrder !== undefined ||
        payload.columnVisibility !== undefined ||
        payload.columnSizing !== undefined
      ) {
        persistedRef.current = columnStateFingerprint({
          columnOrder: payload.columnOrder ?? [],
          columnVisibility: payload.columnVisibility ?? {},
          columnSizing: payload.columnSizing ?? {},
        });
      }
      if (payload.pageSize !== undefined) {
        persistedPageSizeRef.current = payload.pageSize ?? null;
      }

      upsertMutation.mutate(payload);
    }, debounceMs),
  );

  useEffect(() => {
    if (!key) return;
    if (isFetching) return;
    if (!appliedRef.current) return;
    if (suppressPersist) return;
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
    if (persistedRef.current === fingerprint) {
      // Matches what the server already holds - including "matches again, having
      // changed and changed back inside this same debounce window". An EARLIER run in
      // that window may have staged the since-reverted value into the pending
      // payload; drop it rather than let the eventual flush send state the user no
      // longer has (`persistedRef` only advances once a flush actually sends, so this
      // gate compares against the server, not against whatever is merely pending).
      if (
        pendingPayloadRef.current.columnOrder !== undefined ||
        pendingPayloadRef.current.columnVisibility !== undefined ||
        pendingPayloadRef.current.columnSizing !== undefined
      ) {
        const next = { ...pendingPayloadRef.current };
        delete next.columnOrder;
        delete next.columnVisibility;
        delete next.columnSizing;
        delete next.version;
        pendingPayloadRef.current = next;
      }
      return;
    }

    pendingPayloadRef.current = {
      ...pendingPayloadRef.current,
      version: 1,
      columnOrder: filteredOrder,
      columnVisibility: filteredVisibility,
      columnSizing: filteredSizing,
    };
    debouncedFlushRef.current();
  }, [key, orderFingerprint, visibilityFingerprint, sizingFingerprint, isFetching, table, suppressPersist]); // eslint-disable-line react-hooks/exhaustive-deps

  const pageSizeState = table.getState().pagination?.pageSize;

  // Rows-per-page, merged into the SAME pending payload as the column keys above
  // (SF1) - the endpoint's partial merge (`exclude_unset`) leaves whichever keys a
  // given save omits untouched either way, so a page-size-only save still reaches the
  // server as `{ pageSize }` alone when no column key is pending alongside it.
  useEffect(() => {
    if (!key) return;
    if (isFetching) return;
    if (!appliedRef.current) return;
    if (suppressPersist) return;
    if (skipPageSizeSaveOnceRef.current) {
      skipPageSizeSaveOnceRef.current = false;
      return;
    }
    // Same predicate as the apply gate above (`isValidPageSize`): a caller-driven
    // pagination change this hook did not originate must still never write an
    // out-of-bound value.
    if (!isValidPageSize(pageSizeState)) return;

    // Never write back what the server already holds (or what this hook just applied).
    if (persistedPageSizeRef.current === pageSizeState) {
      // Same revert-inside-the-window case as the column effect above.
      if (pendingPayloadRef.current.pageSize !== undefined) {
        const next = { ...pendingPayloadRef.current };
        delete next.pageSize;
        pendingPayloadRef.current = next;
      }
      return;
    }

    pendingPayloadRef.current = {
      ...pendingPayloadRef.current,
      pageSize: pageSizeState,
    };
    debouncedFlushRef.current();
  }, [key, pageSizeState, isFetching, suppressPersist]);

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
    skipPageSizeSaveOnceRef.current = true;
    // A change from just before the reset can still be sitting in the shared pending
    // payload with its debounce timer armed. Clearing it here (rather than relying on
    // a cancel the `debounce` helper does not expose) means that timer's eventual
    // flush finds nothing to send.
    pendingPayloadRef.current = {};
    persistedRef.current = columnStateFingerprint({
      columnOrder: mergeColumnOrderWithLeafColumns(
        defaultOrder,
        table.getAllLeafColumns().map((c) => c.id),
      ),
      columnVisibility: defaultVisibility,
      columnSizing: defaultSizing,
    });
    persistedPageSizeRef.current = defaultPageSize ?? null;
    table.setColumnOrder(defaultOrder);
    table.setColumnVisibility(defaultVisibility);
    table.setColumnSizing(defaultSizing);
    if (typeof defaultPageSize === 'number') {
      // S3 (review round 1): `setPageSize` alone keeps the top row, not `pageIndex`
      // 0 - the same gap as the apply effect. A reset is a fresh view of the grid.
      table.setPagination({ pageIndex: 0, pageSize: defaultPageSize });
    }
    await resetMutation.mutateAsync();
  };

  return {
    isLoading: Boolean(key) && !applied,
    isFetching,
    resetToDefaults,
  };
}

