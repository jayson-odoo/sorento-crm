/**
 * The already-converted state's Delete action (`PLAN-scm-proforma-to-spo.md`'s third
 * amendment, captain live case 21 Aug): the AlertDialog names the SPO numbers and count
 * per ADR-PRODUCT-STANDARDS, the delete actually fires the DELETE route, and a self-heal
 * note (a stale link cleaned up on read) shows as an informational banner rather than a
 * toast. The confirm-table (non-converted) path is exercised by `CreateSpoPanel.test.tsx`'s
 * older sibling; this file covers what changed on `SpoPlannerTable` itself.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const suggestionFn: (...args: unknown[]) => Promise<unknown> = () => Promise.resolve(state.suggestion);

const state = {
  suggestion: null as unknown,
  suggestionFn,
  create: vi.fn(),
  deleteSpo: vi.fn(),
  worksheet: vi.fn(),
};

vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  getSpoSuggestion: (...args: unknown[]) => state.suggestionFn(...args),
  createSpo: (...args: unknown[]) => state.create(...args),
  deleteSpo: (...args: unknown[]) => state.deleteSpo(...args),
  downloadSpoWorksheet: (...args: unknown[]) => state.worksheet(...args),
}));

import { toast } from 'sonner';
import { SpoPlannerTable } from './SpoPlannerTable';

function suggestion(over: Record<string, unknown> = {}) {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    shipment_status: 'in_transit',
    already_converted: false,
    existing_spos: [],
    lines: [],
    self_heal_note: null,
    ...over,
  };
}

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SpoPlannerTable shipmentId="sh-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  state.suggestion = suggestion();
  state.suggestionFn = () => Promise.resolve(state.suggestion);
  state.deleteSpo = vi.fn().mockResolvedValue({
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    deleted_po_numbers: ['CRM-SPO-0001'],
    deleted_spo_count: 1,
    deleted_allocation_count: 0,
  });
  state.worksheet = vi.fn().mockResolvedValue(undefined);
});

const existingSpos = () => [
  { purchase_order_id: 'po-1', po_number: 'CRM-SPO-0001', supplier_id: 'sup-1', supplier_name: 'Kailu' },
];

describe('SpoPlannerTable - already-converted Delete action', () => {
  it('offers a Delete SPO action alongside the worksheet download', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    expect(await screen.findByRole('button', { name: /delete spo/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download worksheet/i })).toBeInTheDocument();
  });

  it('names the SPO number and uses the standard "cannot be undone" copy in the confirm dialog', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/This deletes CRM-SPO-0001/)).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
  });

  it('names every SPO and the count when more than one was created from this shipment', async () => {
    state.suggestion = suggestion({
      already_converted: true,
      existing_spos: [
        ...existingSpos(),
        { purchase_order_id: 'po-2', po_number: 'CRM-SPO-0002', supplier_id: 'sup-2', supplier_name: 'Jiangmen' },
      ],
    });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));

    expect(
      await screen.findByText(/This deletes 2 SPOs: CRM-SPO-0001, CRM-SPO-0002/),
    ).toBeInTheDocument();
  });

  it('does not delete until the AlertDialog is confirmed', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');

    expect(state.deleteSpo).not.toHaveBeenCalled();
  });

  it('deletes on confirm and toasts the deleted SPO number', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(state.deleteSpo).toHaveBeenCalledWith('sh-1'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Deleted SPO CRM-SPO-0001.'),
    );
  });

  it('closes the dialog on cancel without deleting anything', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument());
    expect(state.deleteSpo).not.toHaveBeenCalled();
  });

  it('surfaces the crm_spo-only guard message as an error toast on a refused delete', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    state.deleteSpo = vi.fn().mockRejectedValue(
      new Error('CRM-SPO-0001 was not created by Create SPO and cannot be deleted from this screen.'),
    );
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'CRM-SPO-0001 was not created by Create SPO and cannot be deleted from this screen.',
      ),
    );
  });

  it('shows a self-heal note as an informational banner, not a toast', async () => {
    state.suggestion = suggestion({
      already_converted: true,
      existing_spos: existingSpos(),
      self_heal_note: '1 SPO previously linked to this shipment no longer exists and has been cleared.',
    });
    renderTable();

    expect(
      await screen.findByText(/no longer exists and has been cleared/),
    ).toBeInTheDocument();
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
  });
});
