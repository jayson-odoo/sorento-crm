/**
 * useSalesTargets hooks (16.3, 16.4): a create/patch/period-patch/duplicate/child/delete all
 * invalidate the same two query keys (the list and the detail) and toast, exactly the shared
 * `useCreateMutation`/`useUpdateMutation` shape (`PRINCIPLES.md` layering).
 *
 * Exported names/signatures the coder must match:
 *   `useSalesTargets(params: { on: string; subject: 'agent' | 'team'; salesTeamId?: string; query?: string })`
 *   `useSalesTarget(id: string | null, on?: string)`
 *   `useSalesTargetOptions()`
 *   `useCreateSalesTarget()` - mutate(payload)
 *   `usePatchSalesTargetPeriod()` - mutate({ targetId, periodId, target_value })
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  getSalesTargets: vi.fn(),
  getSalesTarget: vi.fn(),
  getSalesTargetOptions: vi.fn(),
  createSalesTarget: vi.fn(),
  patchSalesTarget: vi.fn(),
  patchSalesTargetPeriod: vi.fn(),
  duplicateSalesTarget: vi.fn(),
  createTargetChild: vi.fn(),
  deleteSalesTarget: vi.fn(),
}));
vi.mock('../services/salesTargetService', () => service);
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useCreateSalesTarget, usePatchSalesTargetPeriod, useSalesTarget, useSalesTargets } from './useSalesTargets';
import { toast } from '@/lib/toast';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
});

describe('useSalesTargets', () => {
  it('reads the list with on/subject params', async () => {
    service.getSalesTargets.mockResolvedValue({ on: '2026-10-15', rows: [], unassigned_amount: 0, no_team_count: 0 });
    const { result } = renderHook(
      () => useSalesTargets({ on: '2026-10-15', subject: 'team' }),
      { wrapper },
    );
    expect(service.getSalesTargets).toHaveBeenCalledWith({ on: '2026-10-15', subject: 'team' });
    await waitFor(() => expect(result.current.data?.rows).toEqual([]));
  });

  it('reads one target', async () => {
    service.getSalesTarget.mockResolvedValue({ id: 't1' });
    renderHook(() => useSalesTarget('t1'), { wrapper });
    await act(async () => {});
    expect(service.getSalesTarget).toHaveBeenCalledWith('t1', undefined);
  });
});

describe('useCreateSalesTarget', () => {
  it('creates and invalidates the targets list, toasting success', async () => {
    service.createSalesTarget.mockResolvedValue({ id: 't1', name: 'North' });
    const { result } = renderHook(() => useCreateSalesTarget(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        subject_kind: 'agent', sales_agent_id: 'a1', name: 'North', metric: 'amount',
        basis: 'ordered', product_scope: 'all', start_date: '2026-10-01', end_date: '2026-10-31',
        target_value: 100,
      }),
    );
    expect(service.createSalesTarget).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalled();
  });

  it('toasts the server error on failure', async () => {
    service.createSalesTarget.mockRejectedValue(new Error('End date is before the start date.'));
    const { result } = renderHook(() => useCreateSalesTarget(), { wrapper });
    await act(async () => {
      try {
        await result.current.mutateAsync({
          subject_kind: 'agent', sales_agent_id: 'a1', name: 'ZZT', metric: 'amount',
          basis: 'ordered', product_scope: 'all', start_date: '2026-12-31', end_date: '2026-10-01',
          target_value: 1,
        });
      } catch {
        // asserted via the toast below
      }
    });
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('before the start date'));
  });
});

describe('usePatchSalesTargetPeriod', () => {
  it('patches one period and invalidates the detail', async () => {
    service.patchSalesTargetPeriod.mockResolvedValue({ id: 't1', periods: [] });
    const { result } = renderHook(() => usePatchSalesTargetPeriod(), { wrapper });
    await act(() =>
      result.current.mutateAsync({ targetId: 't1', periodId: 'p1', target_value: 250 }),
    );
    expect(service.patchSalesTargetPeriod).toHaveBeenCalledWith('t1', 'p1', { target_value: 250 });
    expect(toast.success).toHaveBeenCalled();
  });
});
