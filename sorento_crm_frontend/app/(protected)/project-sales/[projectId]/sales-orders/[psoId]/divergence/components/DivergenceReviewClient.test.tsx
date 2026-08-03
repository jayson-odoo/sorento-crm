/**
 * P8a - the reconciliation screen (AC-N3, AC-N4, AC-N7).
 *
 * Ours, theirs and the difference, per row. The three things worth pinning here are the
 * ones a reviewer would be misled by if they drifted:
 *
 * - rows that AGREE are collapsed behind a count, never dropped. Without them a reviewer
 *   cannot tell a matching document from an unread one.
 * - both actions go through a reason box, because AC-N7 asks WHY and not only which side.
 * - the consequence copy differs per row kind: accepting AutoCount on a header row records
 *   the decision and rewrites nothing, and a reviewer who was not told that would
 *   reasonably expect the customer PO to change.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  DivergenceDetail,
  DivergenceRow,
  DivergenceSummary,
} from '../../../../../_shared/types/soDivergence.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1/divergence',
  useSearchParams: () => new URLSearchParams(''),
}));

const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));

const listDivergences = vi.fn();
const getDivergence = vi.fn();
const ingestSalesOrderFile = vi.fn();
const resolveDivergenceRow = vi.fn();
const downloadCorrectiveImportFile = vi.fn();

vi.mock('../../../../../_shared/services/soDivergenceService', () => ({
  listDivergences: (...args: unknown[]) => listDivergences(...args),
  getDivergence: (...args: unknown[]) => getDivergence(...args),
  ingestSalesOrderFile: (...args: unknown[]) => ingestSalesOrderFile(...args),
  resolveDivergenceRow: (...args: unknown[]) => resolveDivergenceRow(...args),
  downloadCorrectiveImportFile: (...args: unknown[]) =>
    downloadCorrectiveImportFile(...args),
}));

import { DivergenceReviewClient } from './DivergenceReviewClient';

function lineRow(overrides: Partial<DivergenceRow> = {}): DivergenceRow {
  return {
    id: '7f3a9c11-row',
    scope: 'line',
    presence: 'both',
    so_line_id: 'l1',
    line_no: 7,
    product_code: 'CB6633',
    ours: { qty: '600.0000', unit_price: '12.50000', delivery_date: '2026-03-10' },
    theirs: { qty: '550.0000', unit_price: '12.50000', delivery_date: '2026-03-10' },
    differing_fields: ['qty'],
    needs_answer: true,
    resolution: null,
    reason: null,
    resolved_by: null,
    resolved_at: null,
    ...overrides,
  };
}

function agreeingRow(id: string, code: string): DivergenceRow {
  return lineRow({
    id,
    product_code: code,
    differing_fields: [],
    needs_answer: false,
    theirs: { qty: '600.0000', unit_price: '12.50000', delivery_date: '2026-03-10' },
  });
}

function detail(overrides: Partial<DivergenceDetail> = {}): DivergenceDetail {
  return {
    id: 'd1',
    project_sales_order_id: '5e6d7c88-order',
    project_id: 'p1',
    project_title: 'Tuju Residences',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO397450',
    status: 'open',
    ingest_source: 'upload',
    compared_count: 3,
    agreeing_count: 2,
    differing_count: 1,
    unresolved_count: 1,
    corrective_publish_required: false,
    corrective_publish_taken_at: null,
    detected_at: '2026-08-01T02:00:00',
    resolved_at: null,
    resolved_by: null,
    rows: [lineRow(), agreeingRow('4b2e8d22-row', 'AB1200'), agreeingRow('9c1f7a33-row', 'DD3000')],
    ...overrides,
  };
}

function summary(overrides: Partial<DivergenceSummary> = {}): DivergenceSummary {
  return {
    id: 'd1',
    project_sales_order_id: '5e6d7c88-order',
    project_id: 'p1',
    project_title: 'Tuju Residences',
    sales_order_ref: 'SO397450',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO397450',
    status: 'open',
    compared_count: 3,
    agreeing_count: 2,
    differing_count: 1,
    unresolved_count: 1,
    corrective_publish_required: false,
    detected_at: '2026-08-01T02:00:00',
    resolved_at: null,
    age_days: 2,
    ...overrides,
  };
}

function renderReview() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DivergenceReviewClient projectId="p1" psoId="5e6d7c88-order" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listDivergences.mockResolvedValue({ data: [summary()], total: 1, page: 1, limit: 100 });
  getDivergence.mockResolvedValue(detail());
  resolveDivergenceRow.mockResolvedValue(detail());
  ingestSalesOrderFile.mockResolvedValue({
    outcome: 'divergent',
    project_sales_order_id: '5e6d7c88-order',
    divergence_id: 'd1',
    differing_count: 1,
    candidate_ids: [],
    message: '',
  });
});

describe('DivergenceReviewClient', () => {
  it('shows our value beside theirs for the field that differs', async () => {
    renderReview();

    expect(await screen.findByText('CB6633 · line 7')).toBeInTheDocument();
    expect(screen.getByText('600.0000')).toBeInTheDocument();
    expect(screen.getByText('550.0000')).toBeInTheDocument();
  });

  it('says amendments are blocked while anything is unanswered', async () => {
    renderReview();

    expect(await screen.findByText(/1 difference still to answer/i)).toBeInTheDocument();
    expect(screen.getByText(/amendments on this sales order are blocked/i)).toBeInTheDocument();
  });

  it('collapses the rows that agree behind a count rather than dropping them', async () => {
    renderReview();

    const toggle = await screen.findByRole('button', { name: /2 rows agree/i });
    expect(screen.queryByText('AB1200')).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(await screen.findByText(/AB1200/)).toBeInTheDocument();
    expect(screen.getByText(/DD3000/)).toBeInTheDocument();
  });

  it('asks for a reason before either side can win', async () => {
    renderReview();

    fireEvent.click(await screen.findByRole('button', { name: /accept autocount/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: /^accept autocount$/i })).toBeDisabled();
    expect(resolveDivergenceRow).not.toHaveBeenCalled();
  });

  it('records the resolution with the reason the reviewer typed', async () => {
    renderReview();

    fireEvent.click(await screen.findByRole('button', { name: /accept autocount/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/why does this side win/i), {
      target: { value: 'Customer cut it by phone' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^accept autocount$/i }));

    await waitFor(() =>
      expect(resolveDivergenceRow).toHaveBeenCalledWith(
        'd1',
        '7f3a9c11-row',
        'accept_theirs',
        'Customer cut it by phone',
      ),
    );
  });

  it('warns that keeping ours sends a corrective file back', async () => {
    renderReview();

    fireEvent.click(await screen.findByRole('button', { name: /keep ours/i }));

    expect(
      await screen.findByText(/a corrective file is prepared to send back to autocount/i),
    ).toBeInTheDocument();
  });

  it('says a cancelled line is zeroed rather than deleted', async () => {
    getDivergence.mockResolvedValue(
      detail({
        rows: [lineRow({ presence: 'ours_only', theirs: {}, differing_fields: [] })],
      }),
    );
    renderReview();

    fireEvent.click(await screen.findByRole('button', { name: /accept autocount/i }));

    expect(
      await screen.findByText(/cancelled to zero rather than deleted/i),
    ).toBeInTheDocument();
  });

  it('says accepting a header difference does not rewrite the customer PO', async () => {
    getDivergence.mockResolvedValue(
      detail({
        rows: [
          lineRow({
            scope: 'header',
            so_line_id: null,
            line_no: null,
            product_code: null,
            ours: { terms: '*Net 60 days' },
            theirs: { terms: '*Net 30 days' },
            differing_fields: ['terms'],
          }),
        ],
      }),
    );
    renderReview();

    expect(await screen.findByText('Document header')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /accept autocount/i }));

    expect(
      await screen.findByText(/the customer PO is not rewritten/i),
    ).toBeInTheDocument();
  });

  it('labels a row only AutoCount has as added on their side', async () => {
    getDivergence.mockResolvedValue(
      detail({
        rows: [
          lineRow({
            presence: 'theirs_only',
            so_line_id: null,
            ours: {},
            differing_fields: [],
          }),
        ],
      }),
    );
    renderReview();

    expect(await screen.findByText('Added in AutoCount')).toBeInTheDocument();
  });

  it('shows the answer and its reason once a row is decided', async () => {
    getDivergence.mockResolvedValue(
      detail({
        rows: [
          lineRow({
            resolution: 'keep_ours',
            reason: 'The PO says 600',
            resolved_by: 'u1',
            resolved_at: '2026-08-02T01:00:00',
          }),
        ],
      }),
    );
    renderReview();

    expect(await screen.findByText('Ours kept')).toBeInTheDocument();
    expect(screen.getByText('The PO says 600')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /accept autocount/i })).not.toBeInTheDocument();
  });

  it('offers the corrective file only once something was kept', async () => {
    getDivergence.mockResolvedValue(detail({ corrective_publish_required: false }));
    renderReview();

    await screen.findByText('CB6633 · line 7');
    expect(screen.queryByRole('button', { name: /corrective file/i })).not.toBeInTheDocument();

    getDivergence.mockResolvedValue(
      detail({ status: 'resolved', corrective_publish_required: true, unresolved_count: 0 }),
    );
    renderReview();

    expect(await screen.findByRole('button', { name: /corrective file/i })).toBeInTheDocument();
  });

  it('says the order can be amended again once every row is answered', async () => {
    getDivergence.mockResolvedValue(
      detail({
        status: 'resolved',
        unresolved_count: 0,
        rows: [lineRow({ resolution: 'accept_theirs', reason: 'Agreed' })],
      }),
    );
    renderReview();

    expect(await screen.findByText('Reconciled')).toBeInTheDocument();
    expect(
      screen.getByText(/this sales order can be amended again/i),
    ).toBeInTheDocument();
  });

  it('offers the upload as a next step when no difference is on record', async () => {
    listDivergences.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 });
    renderReview();

    expect(
      await screen.findByText(/no difference is on record for this sales order/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/drop the autocount export/i)).toBeInTheDocument();
  });

  it('keeps showing the reconciliation after the last row is answered', async () => {
    // Regression, found in the browser. The OPEN lookup stops returning the row the
    // instant it closes, so the screen used to fall back to "no difference is on record"
    // at exactly the moment the reviewer finished - reading as if the work had vanished.
    renderReview();
    await screen.findByText('CB6633 · line 7');

    listDivergences.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 });
    getDivergence.mockResolvedValue(
      detail({
        status: 'resolved',
        unresolved_count: 0,
        rows: [lineRow({ resolution: 'accept_theirs', reason: 'Agreed' })],
      }),
    );

    const dialogRow = screen.getByRole('button', { name: /keep ours/i });
    fireEvent.click(dialogRow);
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/why does this side win/i), {
      target: { value: 'The PO says 600' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^keep ours$/i }));

    expect(await screen.findByText('Reconciled')).toBeInTheDocument();
    expect(
      screen.queryByText(/no difference is on record/i),
    ).not.toBeInTheDocument();
  });

  it('never renders a raw id', async () => {
    const { container } = renderReview();

    await screen.findByText('CB6633 · line 7');
    expect(container.textContent).not.toContain('5e6d7c88-order');
    expect(container.textContent).not.toContain('7f3a9c11-row');
  });
});
