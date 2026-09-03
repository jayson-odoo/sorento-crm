/**
 * S9 - the one decision per line.
 *
 * What is asserted is what a user would be misled by: a proposal presented without the reason
 * it won or the orders it beat, an Approve that is offered when a line has nowhere to land, and
 * a line that is already allocated being offered for allocation again.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  suggestion: null as unknown,
  approve: vi.fn(),
};

vi.mock('../../services/fulfilmentService', () => ({
  getAllocationSuggestion: () => Promise.resolve(state.suggestion),
  approveAllocations: (...args: unknown[]) => state.approve(...args),
}));

import { AllocationPanel } from './AllocationPanel';

function option(over: Record<string, unknown> = {}) {
  return {
    po_line_id: 'pol-1',
    po_number: 'PO-2026-001',
    warehouse_id: 'wh-1',
    warehouse_code: 'BRW',
    outstanding: 10,
    expected_date: null,
    score: 1,
    factors: [],
    qty: 10,
    ...over,
  };
}

function line(over: Record<string, unknown> = {}) {
  return {
    shipment_line_id: 'sl-1',
    product_id: 'p-1',
    quantity_shipped: 10,
    quantity_allocated: 0,
    quantity_to_allocate: 10,
    reason: 'highest_priority',
    suggestion: option(),
    alternatives: [option({ po_line_id: 'pol-2', po_number: 'PO-2026-002', warehouse_code: 'KLW' })],
    ...over,
  };
}

function suggestion(lines: unknown[]) {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    container_no: 'ABCU1000001',
    supplier_id: 'sup-1',
    lines,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AllocationPanel shipmentId="sh-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.suggestion = suggestion([line()]);
  state.approve = vi
    .fn()
    .mockResolvedValue({ allocations_written: 1, purchase_order_lines_advanced: 1 });
});

describe('AllocationPanel', () => {
  it('arrives with an answer, and says why it is the answer', async () => {
    renderPanel();

    expect(await screen.findByText(/highest priority of the open orders/i)).toBeInTheDocument();
    // Twice on purpose: in the reason line, and in the picker showing what it beat.
    expect(screen.getAllByText(/PO-2026-001/).length).toBeGreaterThan(0);
  });

  it('states how much is still to allocate', async () => {
    renderPanel();

    expect(await screen.findByText(/10 to allocate/)).toBeInTheDocument();
  });

  it('does not offer a line that is already fully allocated', async () => {
    // Re-opening the screen after approving must not propose the same units twice.
    state.suggestion = suggestion([
      line({ quantity_allocated: 10, quantity_to_allocate: 0 }),
    ]);
    renderPanel();

    expect(await screen.findByText('Allocated')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled();
  });

  it('says a single open order is the only one rather than that it won a comparison', async () => {
    state.suggestion = suggestion([line({ reason: 'only_open_order', alternatives: [] })]);
    renderPanel();

    expect(await screen.findByText(/the only open order for this item/i)).toBeInTheDocument();
  });

  it('says plainly when nothing can be drawn down, and what that means', async () => {
    state.suggestion = suggestion([
      line({ reason: 'no_open_order', suggestion: null, alternatives: [] }),
    ]);
    renderPanel();

    expect(await screen.findByText(/no open order for this item/i)).toBeInTheDocument();
    expect(
      screen.getByText(/leaves the ordered figure unchanged/i),
    ).toBeInTheDocument();
  });

  it('refuses to approve while a line has nowhere to land', async () => {
    // The rule the server enforces, said before the click rather than in the error afterwards.
    state.suggestion = suggestion([
      line({ suggestion: option({ warehouse_id: null, warehouse_code: null }), alternatives: [] }),
    ]);
    renderPanel();

    expect(await screen.findByText(/nowhere to land/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled();
  });

  it('approves the quantity that is left, against the chosen order', async () => {
    renderPanel();
    // The button starts disabled until the proposal has been adopted as the current choice,
    // so waiting for it to enable is waiting for the state the user would actually click in.
    const button = await screen.findByRole('button', { name: /approve/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() =>
      expect(state.approve).toHaveBeenCalledWith('sh-1', [
        {
          shipment_line_id: 'sl-1',
          splits: [{ po_line_id: 'pol-1', warehouse_id: 'wh-1', qty: 10 }],
        },
      ]),
    );
  });

  it('names the container it is deciding for', async () => {
    renderPanel();

    expect(await screen.findByText('ABCU1000001')).toBeInTheDocument();
  });

  it('renders an empty container with a reason rather than a blank panel', async () => {
    state.suggestion = suggestion([]);
    renderPanel();

    expect(
      await screen.findByText(/no line we hold a product for/i),
    ).toBeInTheDocument();
  });
});
