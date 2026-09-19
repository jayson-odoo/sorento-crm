/**
 * useAutocountPullAction - SR2 red test (AC-PL-1, AC-PL-5).
 *
 * The Products list and Stock Balance grid each need one more secondary action beside Import,
 * gated by permission, whose label and click behaviour depend on whether the caller has an open
 * pull. Today that logic is written inline, twice, in `ProductsList.tsx` and
 * `StockBalanceGrid.tsx`, each ALSO OR'd with the Phase 1 `hasAutocountPullPermissionMock()`
 * escape hatch that SR2's DoD retires. Rendering either whole list component under jsdom is
 * impractical here (DataGrid + many cross-cutting hooks) - this pins the smallest exported unit
 * that should own the label + gate instead: a shared `useAutocountPullAction(entity,
 * permissionSlug)` hook returning `{ visible, label, onSelect }`, which the two lists then call
 * (replacing their own inline copies and the mock OR).
 *
 * RED reason today: `useAutocountPullAction` does not exist yet - this import fails with
 * "does not provide an export named 'useAutocountPullAction'". Once the coder extracts it, the
 * inline logic in the two list components should be replaced with a call to this hook.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useHasPermission = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (...a: unknown[]) => useHasPermission(...a),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const getCurrentPull = vi.fn();
const startPull = vi.fn();
vi.mock('../services/autocountPullService', () => ({
  getCurrentPull: (...a: unknown[]) => getCurrentPull(...a),
  startPull: (...a: unknown[]) => startPull(...a),
  getPull: vi.fn(),
  getPullRows: vi.fn(),
  downloadPullXlsx: vi.fn(),
  comparePull: vi.fn(),
  confirmPull: vi.fn(),
}));

import { useAutocountPullAction } from './useAutocountPull';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  useHasPermission.mockReset();
  getCurrentPull.mockReset();
  startPull.mockReset();
  push.mockClear();
});

describe('useAutocountPullAction - Products (AC-PL-1, AC-PL-5, master_data.products.autocount_pull)', () => {
  it('B1a: not visible without the permission', async () => {
    useHasPermission.mockReturnValue(false);
    getCurrentPull.mockResolvedValue(null);

    const { result } = renderHook(
      () => useAutocountPullAction('products', 'master_data.products.autocount_pull'),
      { wrapper },
    );

    expect(useHasPermission).toHaveBeenCalledWith('master_data.products.autocount_pull');
    expect(result.current.visible).toBe(false);
  });

  it('B1b: visible + "Pull from AutoCount" with no open pull; activating it starts a pull', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue(null);
    startPull.mockResolvedValue({ job_id: 'new-job-1', entity: 'products', phase: 'building' });

    const { result } = renderHook(
      () => useAutocountPullAction('products', 'master_data.products.autocount_pull'),
      { wrapper },
    );

    await waitFor(() => expect(result.current.visible).toBe(true));
    expect(result.current.label).toBe('Pull from AutoCount');

    await act(async () => {
      await result.current.onSelect();
    });

    expect(startPull).toHaveBeenCalledWith('products');
  });

  it('B1c: visible + "Review pull" with an open pull; activating it navigates without calling startPull', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue({ job_id: 'open-job-1', entity: 'products', phase: 'review' });

    const { result } = renderHook(
      () => useAutocountPullAction('products', 'master_data.products.autocount_pull'),
      { wrapper },
    );

    await waitFor(() => expect(result.current.label).toBe('Review pull'));

    await act(async () => {
      await result.current.onSelect();
    });

    expect(startPull).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/system-management/import-jobs/open-job-1');
  });
});

describe('useAutocountPullAction - Stock Balance (AC-PL-1, AC-PL-5, inventory.stock.autocount_pull)', () => {
  it('B2a: not visible without the permission', async () => {
    useHasPermission.mockReturnValue(false);
    getCurrentPull.mockResolvedValue(null);

    const { result } = renderHook(
      () => useAutocountPullAction('stock_balances', 'inventory.stock.autocount_pull'),
      { wrapper },
    );

    expect(useHasPermission).toHaveBeenCalledWith('inventory.stock.autocount_pull');
    expect(result.current.visible).toBe(false);
  });

  it('B2b: visible + "Pull from AutoCount" with no open pull; activating it starts a pull', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue(null);
    startPull.mockResolvedValue({ job_id: 'new-job-2', entity: 'stock_balances', phase: 'building' });

    const { result } = renderHook(
      () => useAutocountPullAction('stock_balances', 'inventory.stock.autocount_pull'),
      { wrapper },
    );

    await waitFor(() => expect(result.current.visible).toBe(true));
    expect(result.current.label).toBe('Pull from AutoCount');

    await act(async () => {
      await result.current.onSelect();
    });

    expect(startPull).toHaveBeenCalledWith('stock_balances');
  });

  it('B2c: visible + "Review pull" with an open pull; activating it navigates without calling startPull', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue({ job_id: 'open-job-2', entity: 'stock_balances', phase: 'review' });

    const { result } = renderHook(
      () => useAutocountPullAction('stock_balances', 'inventory.stock.autocount_pull'),
      { wrapper },
    );

    await waitFor(() => expect(result.current.label).toBe('Review pull'));

    await act(async () => {
      await result.current.onSelect();
    });

    expect(startPull).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/system-management/import-jobs/open-job-2');
  });
});
