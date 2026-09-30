/**
 * useAutocountPullAction - Delivery Orders (lane DO-PULL-CRM, AC-DP-40).
 *
 * The Delivery Orders list calls the SAME shared hook Products and Stock Balance call, with
 * the third entity and its own slug. Same harness as `useAutocountPullAction.test.tsx`.
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
  startPullErrorMessage: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  getPull: vi.fn(),
  getPullRows: vi.fn(),
  downloadPullXlsx: vi.fn(),
  comparePull: vi.fn(),
  confirmPull: vi.fn(),
  discardPull: vi.fn(),
}));

import { useAutocountPullAction } from './useAutocountPull';
import { AUTOCOUNT_PULL_PERMISSION } from '../types/autocountPull.types';

const SLUG = 'order_management.orders.autocount_pull';

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

describe('useAutocountPullAction - Delivery Orders (AC-DP-40)', () => {
  it('defaults the gate to the entity\'s own slug, the one OrdersList relies on (review blocker 2)', async () => {
    expect(AUTOCOUNT_PULL_PERMISSION.delivery_orders).toBe(SLUG);
    expect(AUTOCOUNT_PULL_PERMISSION.products).toBe('master_data.products.autocount_pull');
    expect(AUTOCOUNT_PULL_PERMISSION.stock_balances).toBe('inventory.stock.autocount_pull');
    useHasPermission.mockReturnValue(false);
    getCurrentPull.mockResolvedValue(null);

    renderHook(() => useAutocountPullAction('delivery_orders'), { wrapper });

    expect(useHasPermission).toHaveBeenCalledWith(SLUG);
  });

  it('is gated on order_management.orders.autocount_pull', async () => {
    useHasPermission.mockReturnValue(false);
    getCurrentPull.mockResolvedValue(null);

    const { result } = renderHook(() => useAutocountPullAction('delivery_orders', SLUG), { wrapper });

    expect(useHasPermission).toHaveBeenCalledWith(SLUG);
    expect(result.current.visible).toBe(false);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(getCurrentPull).not.toHaveBeenCalled();
  });

  it('starts a delivery_orders pull with no scope (the 31-day default) and navigates to it', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue(null);
    startPull.mockResolvedValue({ job_id: 'new-do-job', entity: 'delivery_orders', phase: 'building' });

    const { result } = renderHook(() => useAutocountPullAction('delivery_orders', SLUG), { wrapper });

    await waitFor(() => expect(result.current.visible).toBe(true));
    expect(result.current.label).toBe('Pull from AutoCount');
    await act(async () => {
      await result.current.onSelect();
    });
    expect(startPull).toHaveBeenCalledWith('delivery_orders');
    expect(push).toHaveBeenCalledWith('/system-management/import-jobs/new-do-job');
  });

  it('reads "Review pull" with an open delivery_orders pull and navigates without starting one', async () => {
    useHasPermission.mockReturnValue(true);
    getCurrentPull.mockResolvedValue({ job_id: 'open-do-job', entity: 'delivery_orders', phase: 'review' });

    const { result } = renderHook(() => useAutocountPullAction('delivery_orders', SLUG), { wrapper });

    await waitFor(() => expect(result.current.label).toBe('Review pull'));
    await act(async () => {
      await result.current.onSelect();
    });
    expect(startPull).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith('/system-management/import-jobs/open-do-job');
  });
});
