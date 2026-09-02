/**
 * useSalesAgents / useAnnotateSalesAgent - the hook layer in isolation.
 *
 * The point of the mutation test is the invalidation: a save that does not invalidate
 * `sales-agents` leaves the grid showing the old class, which reads as the save having
 * failed. The service is mocked, so this is the hook's own behaviour, not the network.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const svc = vi.hoisted(() => ({
  getSalesAgents: vi.fn(),
  annotateSalesAgent: vi.fn(),
}));
vi.mock('../services/salesAgentService', () => svc);

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import { useAnnotateSalesAgent, useSalesAgents } from './useSalesAgents';

let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  Object.values(svc).forEach((f) => f.mockReset());
  toastSuccess.mockReset();
  toastError.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useSalesAgents', () => {
  it('resolves the list page from the service', async () => {
    svc.getSalesAgents.mockResolvedValue({
      data: [{ id: 'agent-1' }],
      empty: false,
      pagination: { total: 1, page: 1 },
    });

    const { result } = renderHook(() => useSalesAgents({ pageIndex: 0, pageSize: 50 }), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.pagination.total).toBe(1);
    expect(svc.getSalesAgents).toHaveBeenCalledWith({ pageIndex: 0, pageSize: 50 });
  });
});

describe('useAnnotateSalesAgent', () => {
  it('calls the service, invalidates the list and toasts', async () => {
    svc.annotateSalesAgent.mockResolvedValue({ id: 'agent-1' });
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useAnnotateSalesAgent(), { wrapper });
    await result.current.mutateAsync({
      id: 'agent-1',
      data: { person_label: 'Sean', demand_class: 'project' },
    });

    expect(svc.annotateSalesAgent).toHaveBeenCalledWith('agent-1', {
      person_label: 'Sean',
      demand_class: 'project',
    });
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['sales-agents'] }),
    );
    expect(toastSuccess).toHaveBeenCalled();
  });

  it('toasts the extracted message when the save is refused', async () => {
    svc.annotateSalesAgent.mockRejectedValue(
      new Error("'dealer' is not a demand class the fulfilment policy can weigh."),
    );

    const { result } = renderHook(() => useAnnotateSalesAgent(), { wrapper });
    await expect(
      result.current.mutateAsync({ id: 'agent-1', data: { demand_class: 'dealer' } }),
    ).rejects.toThrow();

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        "'dealer' is not a demand class the fulfilment policy can weigh.",
      ),
    );
  });
});
