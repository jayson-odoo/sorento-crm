/**
 * useSalesOpportunities hooks (plan section 16; UAC S2-12, S2-13).
 *
 * `useSaveSalesOpportunity` is create-or-update off the presence of an id, same split as
 * `useSaveSalesTeam` (`useSalesTeams.test.tsx`). `useCustomerOpportunities` backs the customer
 * page's Opportunities section (UAC S2-12: "No opportunities yet" with Log opportunity).
 *
 * `./useSalesOpportunities` does not exist yet on this branch, so this whole file is expected to
 * fail to resolve the import.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const service = vi.hoisted(() => ({
  createSalesOpportunity: vi.fn(),
  updateSalesOpportunity: vi.fn(),
  getSalesOpportunities: vi.fn(),
  getSalesOpportunity: vi.fn(),
  deleteSalesOpportunity: vi.fn(),
}));
vi.mock('../services/salesOpportunityService', () => service);
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useCustomerOpportunities, useSaveSalesOpportunity } from './useSalesOpportunities';

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.createSalesOpportunity.mockResolvedValue({ id: 'o1' });
  service.updateSalesOpportunity.mockResolvedValue({ id: 'o1' });
});

describe('useSaveSalesOpportunity', () => {
  it('creates through createSalesOpportunity when there is no id', async () => {
    const { result } = renderHook(() => useSaveSalesOpportunity(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        title: 'ZZT Opp',
        expected_amount: '500',
        expected_close_date: '2026-11-01',
        prospect_name: 'ZZT Prospect',
      }),
    );
    expect(service.createSalesOpportunity).toHaveBeenCalledWith({
      title: 'ZZT Opp',
      expected_amount: '500',
      expected_close_date: '2026-11-01',
      prospect_name: 'ZZT Prospect',
    });
    expect(service.updateSalesOpportunity).not.toHaveBeenCalled();
  });

  it('updates through updateSalesOpportunity(id, payload) when called with {id, ...payload}', async () => {
    const { result } = renderHook(() => useSaveSalesOpportunity(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        id: 'o1',
        title: 'ZZT Renamed',
      }),
    );
    expect(service.updateSalesOpportunity).toHaveBeenCalledWith('o1', { title: 'ZZT Renamed' });
    expect(service.createSalesOpportunity).not.toHaveBeenCalled();
  });
});

describe('useCustomerOpportunities', () => {
  it('calls getSalesOpportunities with customerId and returns the rows array', async () => {
    service.getSalesOpportunities.mockResolvedValue({
      data: [{ id: 'o1' }, { id: 'o2' }],
      pagination: { total: 2, page: 1, limit: 20 },
    });

    const { result } = renderHook(() => useCustomerOpportunities('cust-1'), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());

    expect(service.getSalesOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: 'cust-1' }),
    );
    expect(result.current.data).toEqual([{ id: 'o1' }, { id: 'o2' }]);
  });
});
