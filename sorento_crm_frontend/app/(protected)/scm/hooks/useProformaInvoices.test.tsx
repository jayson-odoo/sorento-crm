/**
 * The proforma-invoice hooks: offset paging passed straight through to the service (no
 * `page`/`sort`/`query` params - the backend contract is fixed `created_at DESC`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const success = vi.fn();
const errorToast = vi.fn();
const listProformaInvoices = vi.fn();
const getProformaInvoice = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => success(...a), error: (...a: unknown[]) => errorToast(...a) },
}));

vi.mock('../services/proformaInvoiceService', () => ({
  listProformaInvoices: (...a: unknown[]) => listProformaInvoices(...a),
  getProformaInvoice: (...a: unknown[]) => getProformaInvoice(...a),
}));

import { useProformaInvoice, useProformaInvoices } from './useProformaInvoices';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  success.mockReset();
  errorToast.mockReset();
  listProformaInvoices.mockReset();
  getProformaInvoice.mockReset();
});

describe('useProformaInvoices', () => {
  it('passes the supplier filter and offset paging straight through', async () => {
    listProformaInvoices.mockResolvedValue({ data: [], total: 0, limit: 25, offset: 50 });
    const { result } = renderHook(
      () => useProformaInvoices('sup-1', { limit: 25, offset: 50 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listProformaInvoices).toHaveBeenCalledWith({ supplierId: 'sup-1', limit: 25, offset: 50 });
  });

  it('reads every supplier when none is chosen', async () => {
    listProformaInvoices.mockResolvedValue({ data: [], total: 0, limit: 25, offset: 0 });
    const { result } = renderHook(() => useProformaInvoices(null), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listProformaInvoices).toHaveBeenCalledWith({ supplierId: null });
  });
});

describe('useProformaInvoice', () => {
  it('does not fetch without an id', () => {
    const { result } = renderHook(() => useProformaInvoice(null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(getProformaInvoice).not.toHaveBeenCalled();
  });

  it('fetches the detail once an id is given', async () => {
    getProformaInvoice.mockResolvedValue({ id: 'pi-1' });
    const { result } = renderHook(() => useProformaInvoice('pi-1'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getProformaInvoice).toHaveBeenCalledWith('pi-1');
  });
});
