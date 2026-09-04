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
  SupplyProposal,
} from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getReconciliation = vi.fn();
const rerunReconciliation = vi.fn();
const getSupply = vi.fn();
const confirmSupply = vi.fn();

// The real module with its calls replaced, so the Supply composition section below the
// reconciliation card reads a composition rather than an error, and still gets the real
// ConfirmSupplyError it tells a refusal by.
vi.mock('../../_shared/services/fulfilmentPlanningService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../_shared/services/fulfilmentPlanningService')>();
  return {
    ...actual,
    listFulfilmentPlanning: vi.fn(),
    getReconciliation: (...args: unknown[]) => getReconciliation(...args),
    rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
    getSupply: (...args: unknown[]) => getSupply(...args),
    confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  };
});

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
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
        reason: 'Matched on product and delivery date 01 Jul 2026.',
      },
    ],
    exceptions: [],
    lines_total: 1,
    lines_linked: 1,
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

const WH_BRW = 'a1000000-0000-4000-8000-000000000001';
const PROJECT_LINE_ID = 'd4000000-0000-4000-8000-000000000001';

function supply(overrides: Partial<SupplyProposal> = {}): SupplyProposal {
  return {
    project_sales_order_id: PSO_ID,
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: PROJECT_ID,
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    status: 'published',
    review_state: 'needs_cs_review',
    lines: [
      {
        project_line_id: PROJECT_LINE_ID,
        line_no: 1,
        item_code: 'CB6633',
        description: 'CABANA S/STEEL FLOOR GRATING 6"',
        uom: 'UNIT',
        open_qty: '600',
        required_date: '2026-07-01',
        fulfilment_location: 'BRW-BB',
        is_dealer_hot_selling: false,
        is_project_hot_selling: false,
        dealer_classified: false,
        project_classified: false,
        classification_unavailable: false,
        is_discontinued: false,
        pool_location: 'BRW-BB',
        pool_cap: null,
        pool_reorder_level: '120',
        components: [
          {
            kind: 'reserve',
            qty: '200',
            reason: 'Free stock at BRW-BB covers the need by the delivery date.',
            source_location: 'BRW-BB',
            source_warehouse_id: WH_BRW,
          },
          { kind: 'buy', qty: '400', reason: 'Remaining uncovered need.' },
        ],
        timely_spo: [],
        advisory_spo: [],
        borrow_candidates: [],
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getSupply.mockResolvedValue(supply());
});

describe('FulfilmentPlanningSheet', () => {
  it('states an absent field rather than hiding it, in the header strip and the reconciliation card', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        autocount_doc_no: null,
        customer_name: null,
        po_number: null,
        area_group: null,
        header: { outcome: 'no_document', core_so_number: null, reason: 'No document yet.' },
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
    await waitFor(() => expect(within(dialog).getByText('Not linked')).toBeInTheDocument());
    // The header strip's own absent state for the core sales order, distinct from the
    // reconciliation card's "Not linked" above.
    expect(within(dialog).getByText('Not linked yet')).toBeInTheDocument();
    expect(within(dialog).getByText('Not recorded')).toBeInTheDocument();
    expect(within(dialog).getByText('None')).toBeInTheDocument();
    expect(within(dialog).getByText('No area group')).toBeInTheDocument();
  });

  it('reads the header strip from the summary, so a re-run refreshes what it states', async () => {
    // The row is what the worklist last fetched; the summary is what the reconciliation
    // just answered. An order that has since adopted a document number must not keep
    // reading "Not uploaded" behind a linked core sales order.
    getReconciliation.mockResolvedValue(
      summary({ autocount_doc_no: 'SO376299', customer_name: 'Hong Bee Hardware Sdn Bhd' }),
    );

    renderSheet(row({ autocount_doc_no: null, customer_name: null }));

    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getAllByText('SO376299').length).toBeGreaterThan(0),
    );
    expect(within(dialog).getByText('Hong Bee Hardware Sdn Bhd')).toBeInTheDocument();
    expect(within(dialog).queryByText('Not uploaded')).not.toBeInTheDocument();
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

  it('shows Linked, Missing, Ambiguous(k) and Duplicate per line, never a workflow state', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        lines: [
          { id: 'l1', line_no: 1, product_code: 'CB6633', description: 'Grating', qty: '600', uom: 'UNIT', delivery_date: '2026-07-01', stock_location: 'BRW-BB', link: 'linked', candidate_count: 1, reason: 'Matched.' },
          { id: 'l2', line_no: 2, product_code: 'SRT501-CP', description: 'Mixer', qty: '80', uom: 'UNIT', delivery_date: '2026-07-20', stock_location: 'BRW-BB', link: 'missing', candidate_count: 0, reason: 'No AutoCount line.' },
          { id: 'l3', line_no: 3, product_code: 'SRT382-6', description: 'Sink mixer', qty: '50', uom: 'UNIT', delivery_date: '2026-07-10', stock_location: 'BRW-BB', link: 'ambiguous', candidate_count: 2, reason: 'Two lines carry this item.' },
          { id: 'l4', line_no: 4, product_code: 'CB2201', description: 'Floor trap', qty: '200', uom: 'UNIT', delivery_date: '2026-08-05', stock_location: 'HQ', link: 'duplicate', candidate_count: 0, reason: 'This core line is already linked to Project SO PSO-000124, line 2.' },
        ],
        lines_total: 4,
        lines_linked: 1,
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Linked')).toBeInTheDocument();
    expect(within(dialog).getByText('Missing')).toBeInTheDocument();
    expect(within(dialog).getByText('Ambiguous (2 candidates)')).toBeInTheDocument();
    expect(within(dialog).getByText('Duplicate')).toBeInTheDocument();
  });

  it('says "1 candidate" rather than "1 candidates"', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        lines: [
          { id: 'l1', line_no: 1, product_code: 'SRT382-6', description: 'Sink mixer', qty: '50', uom: 'UNIT', delivery_date: '2026-07-10', stock_location: 'BRW-BB', link: 'ambiguous', candidate_count: 1, reason: 'Two of our lines carry this item on this date.' },
        ],
        lines_total: 1,
        lines_linked: 0,
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Ambiguous (1 candidate)')).toBeInTheDocument();
  });

  it('names the sales order holding a duplicated core line, and never an id', async () => {
    getReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          {
            line_no: 7,
            item_code: 'CB2201',
            kind: 'duplicate',
            message: 'This core line is already linked to Project SO PSO-000124, line 2.',
          },
        ],
      }),
    );

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Line 7, CB2201')).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        'This core line is already linked to Project SO PSO-000124, line 2.',
      ),
    ).toBeInTheDocument();
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

  // ---------------------------------------------------- Stage 1C: the supply
  it('composes the supply below the reconciliation once the lines are linked', async () => {
    getReconciliation.mockResolvedValue(summary({ review_state: 'needs_cs_review' }));

    renderSheet(row());

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Supply composition')).toBeInTheDocument();
    expect(await within(dialog).findByText('Line 1 · CB6633')).toBeInTheDocument();
    await waitFor(() => expect(getSupply).toHaveBeenCalledWith(PSO_ID));
  });

  it('composes nothing while the lines are still being reconciled, and says why', async () => {
    getReconciliation.mockResolvedValue(summary({ review_state: 'awaiting_reconciliation' }));

    renderSheet(row({ review_state: 'awaiting_reconciliation' }));

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText('Nothing can be composed for this sales order yet'),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText('Every line needs its core sales order line first.'),
    ).toBeInTheDocument();
    expect(getSupply).not.toHaveBeenCalled();
  });

  it('reads a confirmed sales order as Confirmed, and shows its frozen composition', async () => {
    getReconciliation.mockResolvedValue(summary({ review_state: 'confirmed' }));
    getSupply.mockResolvedValue(
      supply({
        review_state: 'confirmed',
        decision: {
          revision_no: 2,
          state: 'active',
          confirmed_by_name: 'Nurul Aina',
          confirmed_at: '2026-08-16T09:30:00',
        },
        lines: [
          {
            ...supply().lines[0],
            frozen: {
              open_qty: '600',
              components: [
                {
                  kind: 'reserve',
                  qty: '200',
                  reason: 'Free stock at BRW-BB covers the need by the delivery date.',
                  source_location: 'BRW-BB',
                  source_warehouse_id: WH_BRW,
                },
                { kind: 'buy', qty: '400', reason: 'Remaining uncovered need.' },
              ],
            },
          },
        ],
      }),
    );

    renderSheet(row({ review_state: 'confirmed' }));

    const dialog = await screen.findByRole('dialog');
    // The pill reads the whole SO's one state, and it is the only "Confirmed" here.
    expect(await within(dialog).findByText('Confirmed')).toBeInTheDocument();
    expect(await within(dialog).findByText('Revision 2')).toBeInTheDocument();
    expect(
      within(dialog).queryByRole('button', { name: 'Confirm Project SO' }),
    ).not.toBeInTheDocument();
  });

  it('renders no UUID-looking id on a confirmed sales order either', async () => {
    // The Confirmed pill is allowed; the ids the composition is addressed by are not. Every
    // id in these fixtures is UUID-shaped on purpose, so this can only pass by not printing
    // them: the line is named by number and item code, the location by its warehouse code.
    getReconciliation.mockResolvedValue(summary({ review_state: 'confirmed' }));
    getSupply.mockResolvedValue(
      supply({
        review_state: 'confirmed',
        decision: {
          revision_no: 2,
          state: 'active',
          confirmed_by_name: 'Nurul Aina',
          confirmed_at: '2026-08-16T09:30:00',
        },
      }),
    );

    renderSheet(row({ review_state: 'confirmed' }));

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Confirmed');
    await within(dialog).findByText('Line 1 · CB6633');

    expect(dialog.textContent).toContain('Confirmed');
    expect(dialog.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});

/**
 * The sheet on an order ADOPTED from the AutoCount sales-order book
 * (PLAN-fulfilment-planning-from-autocount-so, journey steps 3 and 4).
 *
 * Two things have to hold. The reconciliation card is rendered even though there is nothing
 * to reconcile against - "no separately authored Project SO exists" is the answer CS came
 * for, and a card that disappears reads as a screen that has not finished loading. And the
 * fulfilment location is the LINE's own, shown per line, never asked for.
 */
describe('FulfilmentPlanningSheet, an adopted sales order', () => {
  const SALES_ORDER_ID = 'e5000000-0000-4000-8000-000000000001';

  function adoptedRow(): FulfilmentPlanningRow {
    return row({
      row_kind: 'sales_order',
      sales_order_id: SALES_ORDER_ID,
      so_number: 'SO368874',
      origin: 'adopted',
      provisional_ref: 'SO368874',
      autocount_doc_no: 'SO368874',
      project_id: null,
      project_code: null,
      project_name: null,
      project_label: 'EMB EMPRESS / PINNACLE ARA DAMANSARA - TOWER A',
      status: 'adopted',
    });
  }

  function adoptedSummary(): ReconciliationSummary {
    return summary({
      provisional_ref: 'SO368874',
      autocount_doc_no: 'SO368874',
      project_id: null,
      project_code: null,
      project_name: null,
      status: 'adopted',
      header: {
        outcome: 'adopted',
        core_so_number: 'SO368874',
        reason:
          'This order came from the AutoCount sales-order book, so there is no separately authored Project SO to compare it against.',
      },
    });
  }

  it('renders the reconciliation card with its empty state, never hides it', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText(/no separately authored Project SO/i);
    expect(within(dialog).getByText('Core sales order')).toBeInTheDocument();
    expect(within(dialog).getByText('Exceptions')).toBeInTheDocument();
    expect(
      within(dialog).getByText('Every line is in step with the sales order book.'),
    ).toBeInTheDocument();
  });

  it('offers Re-sync as the action, not "Re-run reconciliation"', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    const resync = await within(dialog).findByRole('button', { name: 'Re-sync' });
    expect(
      within(dialog).queryByRole('button', { name: 'Re-run reconciliation' }),
    ).not.toBeInTheDocument();

    fireEvent.click(resync);
    await waitFor(() => expect(rerunReconciliation).toHaveBeenCalledWith(PSO_ID));
  });

  it('never shows the same number twice: the Project SO cell says nobody authored one here', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Not authored here');
    expect(within(dialog).getByText('Sales order')).toBeInTheDocument();
  });

  it('links to the SCM sales order, which is where the fulfilment location is stated', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    const link = await within(dialog).findByRole('link', { name: 'Open the sales order' });
    expect(link).toHaveAttribute('href', `/scm/sales-orders/${SALES_ORDER_ID}`);
  });

  it('shows each line’s OWN fulfilment location beside its proposed split', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());
    getSupply.mockResolvedValue(
      supply({
        sales_order_number: 'SO368874',
        sales_order_id: SALES_ORDER_ID,
        project_id: null,
        status: 'adopted',
      }),
    );

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Line 1 · CB6633');
    // The location off the core line, and no question anywhere asking for one: no
    // "Fulfil from" select at order level, no per-line override.
    expect(within(dialog).getAllByText('BRW-BB').length).toBeGreaterThan(0);
    expect(
      within(dialog).queryByRole('combobox', { name: /fulfil|location|warehouse/i }),
    ).toBeNull();
    expect(
      within(dialog).queryByRole('button', { name: /fulfil from|set the location/i }),
    ).toBeNull();
  });

  it('blocks a line whose sales order states no location, and names it rather than guessing', async () => {
    getReconciliation.mockResolvedValue(adoptedSummary());
    const proposal = supply({
      sales_order_number: 'SO366992',
      sales_order_id: SALES_ORDER_ID,
      project_id: null,
      status: 'adopted',
    });
    getSupply.mockResolvedValue({
      ...proposal,
      lines: [
        {
          ...proposal.lines[0],
          fulfilment_location: null,
          fulfilment_location_missing: true,
          components: [],
          timely_spo: [],
        },
      ],
    });

    renderSheet(adoptedRow());

    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText(
      'No fulfilment location on the sales order line, so nothing can be composed for it.',
    );
    // The blocker names the line the only way it may be: number and item code, no id.
    expect(
      within(dialog).getByText(
        'Line 1, CB6633: no fulfilment location on the sales order line.',
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Confirm Project SO' })).toBeDisabled();
  });
});
