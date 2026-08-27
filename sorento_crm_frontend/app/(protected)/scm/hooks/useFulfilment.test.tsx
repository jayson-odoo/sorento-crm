/**
 * The fulfilment hooks: what each one asks the service for, and what it says afterwards.
 *
 * Since part 4 (R2) the build and the send are scoped to a PLAN, not a supplier, so what these
 * pin is that the plan id is what travels - a hook that still passed a supplier would build the
 * right numbers against the wrong row of edits.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const success = vi.fn();
const error = vi.fn();
const buildContainerRequest = vi.fn();
const sendContainerRequest = vi.fn();
const getSupplierNotices = vi.fn();
const deleteSpo = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => success(...a), error: (...a: unknown[]) => error(...a) },
}));

vi.mock('../services/fulfilmentService', () => ({
  approveLoadingPlan: vi.fn(),
  cancelLoadingPlan: vi.fn(),
  createLoadingPlanRecord: vi.fn(),
  updateLoadingPlanCutOff: vi.fn(),
  saveLoadingPlanEdits: vi.fn(),
  getLoadingPlanList: vi.fn(),
  deleteLoadingPlan: vi.fn(),
  getContainerSizes: vi.fn(),
  getSupplierStock: vi.fn(),
  getUnfinishedStock: vi.fn(),
  getSupplierStockListFile: vi.fn(),
  getFulfilmentSuppliers: vi.fn(),
  getPlanNotices: vi.fn(),
  getContainerRequestHistory: vi.fn(),
  getConsolidatedPackingList: vi.fn(),
  getSpoSuggestion: vi.fn(),
  createSpo: vi.fn(),
  downloadSpoWorksheet: vi.fn(),
  downloadContainerRequestDocument: vi.fn(),
  applyStockList: vi.fn(),
  previewStockList: vi.fn(),
  buildContainerRequest: (...a: unknown[]) => buildContainerRequest(...a),
  sendContainerRequest: (...a: unknown[]) => sendContainerRequest(...a),
  getSupplierNotices: (...a: unknown[]) => getSupplierNotices(...a),
  deleteSpo: (...a: unknown[]) => deleteSpo(...a),
}));

import { useContainerRequestBuild, useDeleteSpo, useSendContainerRequest } from './useFulfilment';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  success.mockReset();
  error.mockReset();
  buildContainerRequest.mockReset();
  sendContainerRequest.mockReset();
  getSupplierNotices.mockReset();
  deleteSpo.mockReset();
});

describe('useContainerRequestBuild', () => {
  it('does not fetch until there is a plan to build', () => {
    const { result } = renderHook(() => useContainerRequestBuild(null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(buildContainerRequest).not.toHaveBeenCalled();
  });

  it('builds against the PLAN, which is where the supplier and the cut-off live (R2)', async () => {
    buildContainerRequest.mockResolvedValue({
      plan: { id: 'plan-1', supplier_id: 'sup-1' },
      supplier_id: 'sup-1',
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [],
    });
    const { result } = renderHook(() => useContainerRequestBuild('plan-1'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(buildContainerRequest).toHaveBeenCalledWith('plan-1');
    expect(result.current.data?.plan.id).toBe('plan-1');
  });
});

describe('useSendContainerRequest', () => {
  it('sends the lines and toasts the supplier by name, not id', async () => {
    sendContainerRequest.mockResolvedValue({ notices: [], document_filename: 'x.pdf' });
    const { result } = renderHook(() => useSendContainerRequest(), { wrapper });

    result.current.mutate({
      planId: 'plan-1',
      supplierId: 'sup-1',
      supplierName: 'Foshan Ceramics',
      lines: [{ product_id: 'p1', qty: 10 }],
      options: { channel: 'email', recipients: ['sales@foshan.test'] },
    });

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(sendContainerRequest).toHaveBeenCalledWith(
      'plan-1',
      [{ product_id: 'p1', qty: 10 }],
      { channel: 'email', recipients: ['sales@foshan.test'] },
    );
    expect(success).toHaveBeenCalledWith('Request sent to Foshan Ceramics.');
  });

  it('leaves a refusal on the mutation for the dialog to print, not on a toast (AC-C5)', async () => {
    // S3: the send dialog stays open on a refusal and says the reason beside the field that
    // can fix it. A toast would say the same thing where it cannot be acted on, and would
    // take it away while she is still reading it.
    sendContainerRequest.mockRejectedValue(new Error('This supplier has no email on file.'));
    const { result } = renderHook(() => useSendContainerRequest(), { wrapper });

    result.current.mutate({
      planId: 'plan-1', supplierId: 'sup-1', supplierName: 'Foshan Ceramics',
      lines: [{ product_id: 'p1', qty: 10 }],
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('This supplier has no email on file.');
    expect(error).not.toHaveBeenCalled();
    expect(success).not.toHaveBeenCalled();
  });
});

describe('useDeleteSpo', () => {
  it('toasts the single deleted SPO by number', async () => {
    deleteSpo.mockResolvedValue({
      shipment_id: 'ship-1',
      shipment_number: 'SH-1',
      deleted_po_numbers: ['CRM-SPO-0001'],
      deleted_spo_count: 1,
      deleted_allocation_count: 0,
    });
    const { result } = renderHook(() => useDeleteSpo('ship-1'), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(deleteSpo).toHaveBeenCalledWith('ship-1');
    expect(success).toHaveBeenCalledWith('Deleted SPO CRM-SPO-0001.');
  });

  it('toasts the count and every number when more than one SPO is deleted', async () => {
    deleteSpo.mockResolvedValue({
      shipment_id: 'ship-1',
      shipment_number: 'SH-1',
      deleted_po_numbers: ['CRM-SPO-0001', 'CRM-SPO-0002'],
      deleted_spo_count: 2,
      deleted_allocation_count: 1,
    });
    const { result } = renderHook(() => useDeleteSpo('ship-1'), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(success).toHaveBeenCalled());
    expect(success).toHaveBeenCalledWith('Deleted 2 SPOs: CRM-SPO-0001, CRM-SPO-0002.');
  });

  it('surfaces the guard message on a refused delete rather than a generic one', async () => {
    deleteSpo.mockRejectedValue(
      new Error('CRM-SPO-9999 was not created by Create SPO and cannot be deleted from this screen.'),
    );
    const { result } = renderHook(() => useDeleteSpo('ship-1'), { wrapper });

    result.current.mutate();

    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        'CRM-SPO-9999 was not created by Create SPO and cannot be deleted from this screen.',
      ),
    );
    expect(success).not.toHaveBeenCalled();
  });
});
