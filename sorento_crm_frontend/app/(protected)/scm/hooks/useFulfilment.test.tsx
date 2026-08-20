/**
 * The loading-plan toast quotes volumes, so it has to quote them the way the trade does.
 *
 * Three decimals: the panel the user is looking at while the toast appears prints
 * `68.125 cbm`, and a toast rounding the same figure to `68.13` reads as two different
 * numbers for one plan.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const success = vi.fn();
const error = vi.fn();
const createLoadingPlan = vi.fn();
const buildContainerRequest = vi.fn();
const sendContainerRequest = vi.fn();
const getSupplierNotices = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => success(...a), error: (...a: unknown[]) => error(...a) },
}));

vi.mock('../services/fulfilmentService', () => ({
  createLoadingPlan: (...a: unknown[]) => createLoadingPlan(...a),
  updateLoadingPlan: vi.fn(),
  approveLoadingPlan: vi.fn(),
  getContainerSizes: vi.fn(),
  getSupplierStock: vi.fn(),
  getUnfinishedStock: vi.fn(),
  getSupplierStockListFile: vi.fn(),
  getLoadingPlans: vi.fn(),
  applyStockList: vi.fn(),
  previewStockList: vi.fn(),
  buildContainerRequest: (...a: unknown[]) => buildContainerRequest(...a),
  sendContainerRequest: (...a: unknown[]) => sendContainerRequest(...a),
  getSupplierNotices: (...a: unknown[]) => getSupplierNotices(...a),
}));

import { useBuildLoadingPlan, useContainerRequestBuild, useSendContainerRequest } from './useFulfilment';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  success.mockReset();
  error.mockReset();
  createLoadingPlan.mockReset();
  buildContainerRequest.mockReset();
  sendContainerRequest.mockReset();
  getSupplierNotices.mockReset();
});

describe('useBuildLoadingPlan', () => {
  it('quotes both volumes to three decimals', async () => {
    createLoadingPlan.mockResolvedValue({
      supplier_id: 'sup-1',
      planned_cbm: 34.125,
      capacity_cbm: 68.125,
    });
    const { result } = renderHook(() => useBuildLoadingPlan(), { wrapper });

    result.current.mutate({ supplier_id: 'sup-1' } as never);

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(success).toHaveBeenCalledWith('Planned 34.125 of 68.125 cbm.');
  });

  it('does not pad whole volumes with decimals they were not given', async () => {
    createLoadingPlan.mockResolvedValue({
      supplier_id: 'sup-1',
      planned_cbm: 34,
      capacity_cbm: 68,
    });
    const { result } = renderHook(() => useBuildLoadingPlan(), { wrapper });

    result.current.mutate({ supplier_id: 'sup-1' } as never);

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(success).toHaveBeenCalledWith('Planned 34 of 68 cbm.');
  });
});

describe('useContainerRequestBuild', () => {
  it('does not fetch with no supplier chosen yet', () => {
    const { result } = renderHook(() => useContainerRequestBuild(null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(buildContainerRequest).not.toHaveBeenCalled();
  });

  it('fetches the build once a supplier is chosen', async () => {
    buildContainerRequest.mockResolvedValue({
      supplier_id: 'sup-1', stock_list_as_of: '2026-08-18T00:00:00', rows: [], not_on_stock_list: 0,
    });
    const { result } = renderHook(() => useContainerRequestBuild('sup-1'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(buildContainerRequest).toHaveBeenCalledWith('sup-1', undefined);
    expect(result.current.data?.supplier_id).toBe('sup-1');
  });

  it('forwards the "Plan until" horizon date to the build', async () => {
    buildContainerRequest.mockResolvedValue({
      supplier_id: 'sup-1', stock_list_as_of: '2026-08-18T00:00:00', rows: [], not_on_stock_list: 0,
    });
    const { result } = renderHook(() => useContainerRequestBuild('sup-1', '2026-09-01'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(buildContainerRequest).toHaveBeenCalledWith('sup-1', '2026-09-01');
  });
});

describe('useSendContainerRequest', () => {
  it('sends the lines and toasts the supplier by name, not id', async () => {
    sendContainerRequest.mockResolvedValue({ notices: [], document_filename: 'x.pdf' });
    const { result } = renderHook(() => useSendContainerRequest(), { wrapper });

    result.current.mutate({
      supplierId: 'sup-1',
      supplierName: 'Foshan Ceramics',
      lines: [{ product_id: 'p1', qty: 10 }],
    });

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(sendContainerRequest).toHaveBeenCalledWith('sup-1', [{ product_id: 'p1', qty: 10 }]);
    expect(success).toHaveBeenCalledWith('Request sent to Foshan Ceramics.');
  });

  it('surfaces the server\'s own failure message rather than a generic one', async () => {
    sendContainerRequest.mockRejectedValue(new Error('This supplier has no email on file.'));
    const { result } = renderHook(() => useSendContainerRequest(), { wrapper });

    result.current.mutate({
      supplierId: 'sup-1', supplierName: 'Foshan Ceramics',
      lines: [{ product_id: 'p1', qty: 10 }],
    });

    await waitFor(() => expect(error).toHaveBeenCalledWith('This supplier has no email on file.'));
    expect(success).not.toHaveBeenCalled();
  });
});
