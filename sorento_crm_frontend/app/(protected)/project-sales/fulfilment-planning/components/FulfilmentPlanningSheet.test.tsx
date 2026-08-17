/**
 * Stage 1B - the reconciliation side sheet (journey step 2, AC-A02, AC-A03, AC-G02).
 *
 * Every section renders whatever the answer is: a sales order with no lines, no core order
 * or no exceptions states that in place rather than dropping the section (AC-G02). The
 * sheet's one binding rule is AC-A03 - a reconciled, unconfirmed sales order reads "Needs CS
 * review" everywhere in it, and no line or the whole SO is ever labeled partially
 * confirmed, confirmed, or purchasing-ready. Every subject is named by line number and item
 * code, never by the ids this file deliberately makes UUID-shaped to prove it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  FulfilmentPlanningRow,
  ReconciliationSummary,
} from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getReconciliation = vi.fn();
const rerunReconciliation = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: (...args: unknown[]) => getReconciliation(...args),
  rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
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

import { FulfilmentPlanningSheet } from './FulfilmentPlanningSheet';

const PROJECT_ID = 'b6a1f2e0-1111-4a11-8a11-111111111111';
const PSO_ID = 'c7b2a3f1-2222-4b22-9b22-222222222222';

function row(overrides: Partial<FulfilmentPlanningRow> = {}): FulfilmentPlanningRow {
  return {
    id: PSO_ID,
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: PROJECT_ID,
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    line_count: 4,
    lines_linked: 4,
    exception_count: 0,
    review_state: 'needs_cs_review',
    updated_at: '2026-08-14T02:41:00',
    ...overrides,
  };
}

function summary(overrides: Partial<ReconciliationSummary> = {}): ReconciliationSummary {
  return {
    project_sales_order_id: PSO_ID,
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: PROJECT_ID,
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    review_state: 'needs_cs_review',
    header: { outcome: 'linked', core_so_number: 'SO376201', reason: 'Linked to sales order SO376201.' },
    lines: [
      {
        id: 'line-1',
        line_no: 1,
        product_code: 'CB6633',
        description: 'CABANA S/STEEL FLOOR GRATING 6"',
        qty: '600',
        uom: 'UNIT',
        delivery_date: '2026-07-01',
        stock_location: 'BRW-BB',
        link: 'linked',
        candidate_count: 1,
        reason: 'Matched on product and required date 01 Jul 2026.',
      },
    ],
    exceptions: [],
    lines_total: 1,
    lines_linked: 1,
    reconciled_at: '2026-08-14T02:41:00',
    ...overrides,
  };
}

function renderSheet(
  planningRow: FulfilmentPlanningRow | null,
  open = true,
  onOpenChange: (open: boolean) => void = vi.fn(),
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentPlanningSheet row={planningRow} open={open} onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FulfilmentPlanningSheet', () => {
  it('states an absent field rather than hiding it, in the header strip and the reconciliation card', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        header: { outcome: 'no_document', core_so_number: null, reason: 'No document yet.' },
        reconciled_at: null,
      }),
    );

    renderSheet(
      row({
        autocount_doc_no: null,
        customer_name: null,
        po_number: null,
        area_group: null,
      }),
    );

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Not uploaded')).toBeInTheDocument();
    expect(within(dialog).getByText('Not recorded')).toBeInTheDocument();
    expect(within(dialog).getByText('None')).toBeInTheDocument();
    expect(within(dialog).getByText('No area group')).toBeInTheDocument();

    await waitFor(() => expect(within(dialog).getByText('Never run')).toBeInTheDocument());
    expect(within(dialog).getByText('Not linked')).toBeInTheDocument();
  });

  it('links to the AutoCount upload screen only when no document has been uploaded', async () => {
    getReconciliation.mockResolvedValue(
      summary({ header: { outcome: 'no_document', core_so_number: null, reason: 'No document yet.' } }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    const link = await within(dialog).findByRole('link', {
      name: /upload the autocount document/i,
    });
    expect(link).toHaveAttribute(
      'href',
      `/project-sales/${PROJECT_ID}/sales-orders/${PSO_ID}/divergence`,
    );
  });

  it('offers no upload link once the header is linked', async () => {
    getReconciliation.mockResolvedValue(summary({ header: { outcome: 'linked', core_so_number: 'SO376201', reason: 'Linked.' } }));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Reconciliation');
    expect(
      within(dialog).queryByRole('link', { name: /upload the autocount document/i }),
    ).not.toBeInTheDocument();
  });

  it('offers no upload link while the header has no core SO either', async () => {
    getReconciliation.mockResolvedValue(
      summary({ header: { outcome: 'no_core_so', core_so_number: null, reason: 'Not carried yet.' } }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Reconciliation');
    expect(
      within(dialog).queryByRole('link', { name: /upload the autocount document/i }),
    ).not.toBeInTheDocument();
  });

  it('says every line is linked rather than showing an empty exception list', async () => {
    getReconciliation.mockResolvedValue(summary({ exceptions: [] }));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(
        'Every line is linked, and nothing on the AutoCount document is spare.',
      ),
    ).toBeInTheDocument();
  });

  it('names each exception by line number and item code, and states its reason', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          { line_no: 2, item_code: 'SRT501-CP', kind: 'missing', message: 'The AutoCount document has no line for this item.' },
          { item_code: 'SRT770-BK', kind: 'surplus', message: 'On the AutoCount document and not on this sales order.' },
        ],
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Line 2, SRT501-CP')).toBeInTheDocument();
    expect(
      within(dialog).getByText('The AutoCount document has no line for this item.'),
    ).toBeInTheDocument();
    // A surplus core line has no Project line, so it is named by item code alone.
    expect(within(dialog).getByText('SRT770-BK')).toBeInTheDocument();
  });

  it('shows Linked, Missing and Ambiguous(k) per line, never a workflow state', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        lines: [
          { id: 'l1', line_no: 1, product_code: 'CB6633', description: 'Grating', qty: '600', uom: 'UNIT', delivery_date: '2026-07-01', stock_location: 'BRW-BB', link: 'linked', candidate_count: 1, reason: 'Matched.' },
          { id: 'l2', line_no: 2, product_code: 'SRT501-CP', description: 'Mixer', qty: '80', uom: 'UNIT', delivery_date: '2026-07-20', stock_location: 'BRW-BB', link: 'missing', candidate_count: 0, reason: 'No AutoCount line.' },
          { id: 'l3', line_no: 3, product_code: 'SRT382-6', description: 'Sink mixer', qty: '50', uom: 'UNIT', delivery_date: '2026-07-10', stock_location: 'BRW-BB', link: 'ambiguous', candidate_count: 2, reason: 'Two lines carry this item.' },
        ],
        lines_total: 3,
        lines_linked: 1,
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Linked')).toBeInTheDocument();
    expect(within(dialog).getByText('Missing')).toBeInTheDocument();
    expect(within(dialog).getByText('Ambiguous (2 candidates)')).toBeInTheDocument();
  });

  it('states that a sales order has no lines rather than an empty table', async () => {
    getReconciliation.mockResolvedValue(summary({ lines: [], lines_total: 0, lines_linked: 0 }));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('This sales order has no lines')).toBeInTheDocument();
    expect(
      within(dialog).getByText('Nothing can be reconciled until it carries at least one line.'),
    ).toBeInTheDocument();
  });

  it('reports a failed reconciliation load and offers a retry', async () => {
    getReconciliation.mockRejectedValue(new Error('That order was rebuilt'));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText('The reconciliation could not be loaded'),
    ).toBeInTheDocument();
    expect(within(dialog).getByText('That order was rebuilt')).toBeInTheDocument();

    getReconciliation.mockResolvedValue(summary());
    fireEvent.click(within(dialog).getByRole('button', { name: 'Try again' }));

    await within(dialog).findByText('Reconciliation');
    // The hook retries once on its own before surfacing the error, so the manual "Try
    // again" click is the third call, and the one that finally succeeds.
    expect(getReconciliation.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('re-runs and celebrates a clean result, refetching the reconciliation', async () => {
    getReconciliation.mockResolvedValue(summary({ exceptions: [] }));
    rerunReconciliation.mockResolvedValue(summary({ exceptions: [] }));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Reconciliation');

    fireEvent.click(within(dialog).getByRole('button', { name: /re-run reconciliation/i }));

    await waitFor(() => expect(rerunReconciliation).toHaveBeenCalledWith(PSO_ID));
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        'Reconciled. This sales order is ready for CS review.',
      ),
    );
    // Invalidated queries refetch: the reconciliation read runs again.
    await waitFor(() => expect(getReconciliation.mock.calls.length).toBeGreaterThan(1));
  });

  it('re-runs and warns how many exceptions are still open', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          { line_no: 2, item_code: 'SRT501-CP', kind: 'missing', message: 'No AutoCount line.' },
        ],
      }),
    );
    rerunReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          { line_no: 2, item_code: 'SRT501-CP', kind: 'missing', message: 'No AutoCount line.' },
        ],
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: /re-run reconciliation/i }));

    await waitFor(() =>
      expect(toastWarning).toHaveBeenCalledWith(
        '1 exception still to clear on this sales order.',
      ),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------- AC-A03
  it('AC-A03: a needs-CS-review order reads that state everywhere, and no line reads confirmed, partial or purchasing-ready', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        review_state: 'needs_cs_review',
        header: { outcome: 'linked', core_so_number: 'SO376201', reason: 'Linked to sales order SO376201.' },
        lines: [
          { id: 'l1', line_no: 1, product_code: 'CB6633', description: 'Grating', qty: '600', uom: 'UNIT', delivery_date: '2026-07-01', stock_location: 'BRW-BB', link: 'linked', candidate_count: 1, reason: 'Matched.' },
          { id: 'l2', line_no: 2, product_code: 'SRT382-6', description: 'Sink mixer', qty: '40', uom: 'UNIT', delivery_date: '2026-07-01', stock_location: 'BRW-BB', link: 'linked', candidate_count: 1, reason: 'Matched.' },
        ],
        exceptions: [],
        lines_total: 2,
        lines_linked: 2,
      }),
    );

    const { container } = renderSheet(row({ review_state: 'needs_cs_review', exception_count: 0 }));

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Reconciliation');

    expect(container.textContent).not.toMatch(/confirmed|partial|purchasing/i);
    // The pill reads exactly the state, with no exception suffix since there are none.
    expect(within(dialog).getByText('Needs CS review')).toBeInTheDocument();
  });

  it('renders no UUID-looking id anywhere in the sheet', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          { line_no: 2, item_code: 'SRT501-CP', kind: 'missing', message: 'No AutoCount line.' },
        ],
      }),
    );

    const { container } = renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Reconciliation');

    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});
