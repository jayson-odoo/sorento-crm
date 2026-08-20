/**
 * "Create SPO" - the shipment page's own confirm screen (`PLAN-scm-proforma-to-spo.md`'s
 * Amendment, second decision). What is asserted is what a buyer would be misled by: a line
 * that should be pre-checked left unticked (or the reverse), a covered/no-supplier line that
 * disappears instead of explaining itself, a re-run on an already-converted shipment that
 * offers Create again, and a confirm that does not say which SPOs it actually made.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  suggestion: null as unknown,
  suggestionFn: () => Promise.resolve(state.suggestion),
  create: vi.fn(),
  worksheet: vi.fn(),
};

vi.mock('../../services/fulfilmentService', () => ({
  getSpoSuggestion: (...args: unknown[]) => state.suggestionFn(...args),
  createSpo: (...args: unknown[]) => state.create(...args),
  downloadSpoWorksheet: (...args: unknown[]) => state.worksheet(...args),
}));

import { toast } from 'sonner';
import { CreateSpoPanel } from './CreateSpoPanel';

function line(over: Record<string, unknown> = {}) {
  return {
    shipment_line_id: 'sl-1',
    product_id: 'p-1',
    item_code: 'SRT-100',
    product_name: 'Widget',
    supplier_id: 'sup-1',
    supplier_name: 'Kailu',
    packed_qty: 100,
    po_covered_qty: 0,
    matched_po_number: null,
    matched_by: null,
    on_hand: 0,
    incoming_spo: 0,
    suggested_qty: 100,
    covered: false,
    cannot_convert: false,
    reason: null,
    unit_cost: 10,
    currency: 'USD',
    ...over,
  };
}

function suggestion(over: Record<string, unknown> = {}) {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    shipment_status: 'in_transit',
    already_converted: false,
    existing_spos: [],
    lines: [line()],
    ...over,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CreateSpoPanel shipmentId="sh-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  state.suggestion = suggestion();
  state.suggestionFn = () => Promise.resolve(state.suggestion);
  state.create = vi.fn().mockResolvedValue({
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    created_spos: [
      { purchase_order_id: 'po-1', po_number: 'CRM-SPO-0001', supplier_id: 'sup-1', supplier_name: 'Kailu', currency: 'USD', lines: 1, qty: 100 },
    ],
    skipped: [],
  });
  state.worksheet = vi.fn().mockResolvedValue(undefined);
});

describe('CreateSpoPanel', () => {
  it('shows a loading state before the suggestion answers', () => {
    // Never-resolving promise: the query stays pending for the life of the test.
    state.suggestionFn = () => new Promise(() => {});
    const { container } = renderPanel();
    expect(container.querySelector('[class*="animate-pulse"]')).toBeTruthy();
  });

  it('pre-checks a line at its suggested quantity', async () => {
    renderPanel();

    const checkbox = await screen.findByRole('checkbox');
    await waitFor(() => expect(checkbox).toHaveAttribute('data-state', 'checked'));
    const qtyInput = screen.getByRole('spinbutton') as HTMLInputElement;
    expect(qtyInput.value).toBe('100');
  });

  it('leaves a covered line unticked and says why', async () => {
    state.suggestion = suggestion({
      lines: [
        line({
          shipment_line_id: 'sl-covered',
          suggested_qty: 0,
          covered: true,
          po_covered_qty: 100,
          matched_po_number: 'PO-2026-001',
          matched_by: 'product',
          reason: 'Fully covered - already ordered on PO-2026-001.',
        }),
      ],
    });
    renderPanel();

    expect(await screen.findByText(/already ordered on PO-2026-001/)).toBeInTheDocument();
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toHaveAttribute('data-state', 'unchecked');
  });

  it('explains a line with no supplier and disables it rather than dropping it', async () => {
    state.suggestion = suggestion({
      lines: [
        line({
          shipment_line_id: 'sl-nosup',
          supplier_id: null,
          supplier_name: null,
          cannot_convert: true,
          suggested_qty: 0,
          po_covered_qty: 0,
          reason: 'No supplier recorded on this shipment line, so it cannot be added to an SPO.',
        }),
      ],
    });
    renderPanel();

    expect(
      await screen.findByText(/no supplier recorded on this shipment line/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('shows the existing SPOs instead of a confirm screen once already converted', async () => {
    state.suggestion = suggestion({
      already_converted: true,
      existing_spos: [
        { purchase_order_id: 'po-1', po_number: 'CRM-SPO-0001', supplier_id: 'sup-1', supplier_name: 'Kailu' },
        { purchase_order_id: 'po-2', po_number: 'CRM-SPO-0002', supplier_id: 'sup-2', supplier_name: 'Jiangmen' },
      ],
      lines: [],
    });
    renderPanel();

    expect(await screen.findByText(/CRM-SPO-0001/)).toBeInTheDocument();
    expect(screen.getByText(/CRM-SPO-0002/)).toBeInTheDocument();
    expect(screen.getByText(/already created from this shipment/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create spo/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download worksheet/i })).toBeInTheDocument();
  });

  it('surfaces a 409 (already converted mid-flight) as an error toast rather than pretending it worked', async () => {
    state.create = vi.fn().mockRejectedValue(
      new Error('An SPO has already been created from this shipment: CRM-SPO-0001.'),
    );
    renderPanel();

    const button = await screen.findByRole('button', { name: /create spo/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'An SPO has already been created from this shipment: CRM-SPO-0001.',
      ),
    );
  });

  it('lets the buyer trim the suggested quantity before confirming', async () => {
    renderPanel();

    const qtyInput = await screen.findByRole('spinbutton');
    fireEvent.change(qtyInput, { target: { value: '40' } });

    const button = screen.getByRole('button', { name: /create spo/i });
    fireEvent.click(button);

    await waitFor(() =>
      expect(state.create).toHaveBeenCalledWith('sh-1', [
        { shipment_line_id: 'sl-1', qty: 40, include: true },
      ]),
    );
  });

  it('confirms and names the SPOs it made', async () => {
    renderPanel();

    const button = await screen.findByRole('button', { name: /create spo/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Created SPO: CRM-SPO-0001.'),
    );
  });

  it('renders an empty container with a reason rather than a blank panel', async () => {
    state.suggestion = suggestion({ lines: [] });
    renderPanel();

    expect(
      await screen.findByText(/no line we hold a product for/i),
    ).toBeInTheDocument();
  });
});
