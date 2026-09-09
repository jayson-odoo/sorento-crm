/**
 * PI detail's Packing tab (S2, AC-B9/B10) - the supplier's packing list as filed.
 *
 * What this pins:
 * - Empty state: no rows at all -> "No packing list attached yet" + Attach packing list CTA
 *   (AC-B10), and the CTA calls back to the page's own upload dialog opener.
 * - Populated state: rows present but NO packing file on record (a combined invoice+packing
 *   sheet, or a packing list attached before this lane filed anything, fix round 1 item 3) -
 *   the grid renders off the ROWS, never gated on `file`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ProformaInvoiceDetail } from '../../../services/proformaInvoiceService';
import type { ProformaInvoicePackingLine } from '../../types/packingLine.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn().mockResolvedValue({
    id: 'pa-1',
    action_key: 'proforma_invoice_packing_line.dismiss',
    entity_type: 'proforma_invoice_packing_line',
    entity_id: 'row-1',
    commit_at: '2026-09-10T10:00:05',
    window_seconds: 5,
  }),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { ProformaInvoicePackingTab } from './ProformaInvoicePackingTab';

function baseInvoice(lines: ProformaInvoiceDetail['lines'] = []): ProformaInvoiceDetail {
  return {
    id: 'pi-1',
    supplier_id: 'sup-1',
    supplier_code: 'KAILU',
    supplier_name: 'Kailu Hardware Factory',
    pi_number: 'PI-2609-001',
    invoice_date: '2026-07-30',
    currency: 'CNY',
    container_no: null,
    bl_no: null,
    total_amount: 1000,
    line_count: lines.length,
    source_ref: 'kailu.xlsx',
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-07-30T02:00:00',
    updated_at: '2026-07-30T02:00:00',
    total_cbm: 1,
    unmeasured_lines: 0,
    status: 'current',
    revision_no: 1,
    revision_count: 1,
    adjusted_by: null,
    adjusted_at: null,
    is_adjusted: false,
    placement: 'not_converted',
    placed_qty: 0,
    total_qty: 10,
    remaining_qty: 10,
    packing_lists: [],
    lines,
    converted_shipments: [],
    revisions: [],
    revision_of_pi_number: null,
    diff: null,
  } as unknown as ProformaInvoiceDetail;
}

function packingRow(over: Partial<ProformaInvoicePackingLine> = {}): ProformaInvoicePackingLine {
  return {
    id: 'row-1',
    proforma_invoice_line_id: null,
    row_no: 1,
    item_code: 'SRTSC14-GM',
    supplier_code: 'SRTSC14-GM',
    description: 'Ceramic bowl',
    product_id: null,
    product_set_id: null,
    qty: 50,
    cartons: 1,
    pcs_per_carton: 50,
    carton_length_cm: 38,
    carton_width_cm: 37,
    carton_height_cm: 14.5,
    cbm_per_carton: 0.02037,
    cbm_total: 0.02037,
    net_weight: 19,
    gross_weight: 21.3,
    total_net_weight: 19,
    total_gross_weight: 21.3,
    material: null,
    container_no: null,
    remark: null,
    match_state: 'unmatched',
    unmatched_reason: null,
    ...over,
  };
}

function renderTab(invoice: ProformaInvoiceDetail, over: { onAttach?: () => void; onReplace?: () => void } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onAttach = over.onAttach ?? vi.fn();
  const onReplace = over.onReplace ?? vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ProformaInvoicePackingTab
        invoice={invoice}
        canAdjust={true}
        onAttach={onAttach}
        onReplace={onReplace}
      />
    </QueryClientProvider>,
  );
  return { onAttach, onReplace };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ProformaInvoicePackingTab - empty state (AC-B10)', () => {
  it('shows "No packing list attached yet" and an Attach packing list CTA when there are no rows', async () => {
    const invoice = baseInvoice();
    const { onAttach } = renderTab(invoice);

    expect(await screen.findByText('No packing list attached yet')).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: 'Attach packing list' });
    fireEvent.click(cta);
    expect(onAttach).toHaveBeenCalledTimes(1);
  });

  it('offers no Attach CTA when the caller cannot adjust the invoice', async () => {
    const invoice = baseInvoice();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ProformaInvoicePackingTab
          invoice={invoice}
          canAdjust={false}
          onAttach={vi.fn()}
          onReplace={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('No packing list attached yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Attach packing list' })).not.toBeInTheDocument();
  });
});

describe('ProformaInvoicePackingTab - populated state renders off the ROWS, not the file (fix round 1 item 3)', () => {
  it('renders the grid when rows exist even though no packing_file is on record', async () => {
    const invoice = {
      ...baseInvoice(),
      // A combined invoice+packing sheet, or a packing list filed before this lane
      // existed - the packing FILE metadata is optional header dressing.
      packing_file: null,
      packing_lines: [packingRow()],
    } as unknown as ProformaInvoiceDetail;

    renderTab(invoice);

    expect(await screen.findByText('SRTSC14-GM')).toBeInTheDocument();
    expect(screen.queryByText('No packing list attached yet')).not.toBeInTheDocument();
    // The Matched cell for an unmatched row (AC-B12).
    expect(screen.getByText('Not in catalogue')).toBeInTheDocument();
  });

  it('shows the filed packing file name and date once one is on record', async () => {
    const invoice = {
      ...baseInvoice(),
      packing_file: { name: 'packing-list.xls', uploaded_at: '2026-08-02T01:00:00' },
      packing_lines: [packingRow({ match_state: 'matched' })],
    } as unknown as ProformaInvoiceDetail;

    renderTab(invoice);

    expect(await screen.findByText(/packing-list\.xls/)).toBeInTheDocument();
    // 'Matched' appears twice: the column header and the row's own badge.
    expect(screen.getAllByText('Matched').length).toBeGreaterThanOrEqual(2);
  });
});
