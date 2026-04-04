'use client';

import { Table } from '@tanstack/react-table';
import { useEffect, useMemo, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { debounce } from '@/lib/helpers';
import {
  getUserListColumnConfig,
  resetUserListColumnConfig,
  upsertUserListColumnConfig,
  type UserListColumnConfigPayload,
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

    if (Array.isArray(payload.columnOrder) && payload.columnOrder.length > 0) {
      const leafIds = table.getAllLeafColumns().map((c) => c.id);
      const allowed = new Set(leafIds);
      const filteredOrder = payload.columnOrder.filter((id) => allowed.has(id));
      const mergedOrder = mergeColumnOrderWithLeafColumns(filteredOrder, leafIds);
      skipSaveOnceRef.current = true;
      table.setColumnOrder(mergedOrder);
    }

    if (payload.columnVisibility && typeof payload.columnVisibility === 'object') {
      const filteredVisibility: ColumnVisibilityState = {};
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
      skipSaveOnceRef.current = true;
      table.setColumnSizing(filteredSizing);
    }

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
  });

  const resetToDefaults = async () => {
    if (!key) return;
    // Prevent the reset operation from being immediately persisted back as "saved defaults".
    skipSaveOnceRef.current = true;
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

