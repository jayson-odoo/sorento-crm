/**
 * Planning changes mutations (`PLAN-so-book-diff-replanning.md`).
 *
 * What is worth pinning: a decision write - `accept`/`keep`/`board` as much as the newer
 * `confirm`/`amend` - is invisible unless it says so (the captain, 19 August 2026: "clicking
 * accept here has no effect"), so every successful write toasts. `composition` travels through
 * to the service call untouched. Apply's own success toast is `PlanningChangeBatchClient`'s job
 * (it needs the refetched per-order revision numbers this hook does not have) - this hook only
 * covers the `already_applied` / partial-failure edges it CAN say something about immediately.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConfirmLine } from '../types/fulfilmentPlanning.types';

const updatePlanningChangeRow = vi.fn();
const applyPlanningChanges = vi.fn();

vi.mock('../services/planningChangeService', () => ({
  listPlanningChangeBatches: vi.fn(),
  getPlanningChangeBatch: vi.fn(),
  updatePlanningChangeRow: (...args: unknown[]) => updatePlanningChangeRow(...args),
  applyPlanningChanges: (...args: unknown[]) => applyPlanningChanges(...args),
}));

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    warning: (...args: unknown[]) => toastWarning(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

import { usePlanningChangeMutations } from './usePlanningChanges';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('usePlanningChangeMutations - updateDecision', () => {
  it('toasts that the write is saved, so it is never silent', async () => {
    updatePlanningChangeRow.mockResolvedValue({ id: 'pcr-1', decision: 'keep' });
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.updateDecision.mutate({ rowId: 'pcr-1', decision: 'keep' });

    await waitFor(() => expect(result.current.updateDecision.isSuccess).toBe(true));
    expect(toastSuccess).toHaveBeenCalledWith('Saved - applied when you press Apply');
  });

  it('carries the composition through to the service call, for amend', async () => {
    const composition: ConfirmLine = {
      project_line_id: 'line-1',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-own', qty: '40' }],
      borrow: [],
      buy_qty: '6',
      amend_reason: 'Own location has stock the proposal did not use.',
    };
    updatePlanningChangeRow.mockResolvedValue({ id: 'pcr-1', decision: 'amend', composition });
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.updateDecision.mutate({ rowId: 'pcr-1', decision: 'amend', composition });

    await waitFor(() => expect(result.current.updateDecision.isSuccess).toBe(true));
    expect(updatePlanningChangeRow).toHaveBeenCalledWith('pcb-1', 'pcr-1', {
      decision: 'amend',
      composition,
    });
  });

  it('says why on failure, rather than leaving the control silent', async () => {
    updatePlanningChangeRow.mockRejectedValue(new Error('The board confirmed a newer revision.'));
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.updateDecision.mutate({ rowId: 'pcr-1', decision: 'confirm' });

    await waitFor(() => expect(result.current.updateDecision.isError).toBe(true));
    expect(toastError).toHaveBeenCalledWith('The board confirmed a newer revision.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});

describe('usePlanningChangeMutations - apply', () => {
  it('toasts already_applied on a no-op re-apply', async () => {
    applyPlanningChanges.mockResolvedValue({
      applied_orders: ['SO403765'],
      failed_orders: [],
      already_applied: true,
    });
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.apply.mutate();

    await waitFor(() => expect(result.current.apply.isSuccess).toBe(true));
    expect(toastSuccess).toHaveBeenCalledWith('This batch was already applied.');
  });

  it('warns when every order failed, since nothing was written', async () => {
    applyPlanningChanges.mockResolvedValue({
      applied_orders: [],
      failed_orders: [{ so_number: 'SO403765', reason: 'stale reserve' }],
      already_applied: false,
    });
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.apply.mutate();

    await waitFor(() => expect(result.current.apply.isSuccess).toBe(true));
    expect(toastWarning).toHaveBeenCalledWith('Applied, but 1 order could not be written.');
  });

  it('does not toast a success message itself when orders applied - the batch page does, off the refetch', async () => {
    applyPlanningChanges.mockResolvedValue({
      applied_orders: ['SO403765'],
      failed_orders: [],
      already_applied: false,
    });
    const { result } = renderHook(() => usePlanningChangeMutations('pcb-1'), { wrapper });

    result.current.apply.mutate();

    await waitFor(() => expect(result.current.apply.isSuccess).toBe(true));
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastWarning).not.toHaveBeenCalled();
  });
});
