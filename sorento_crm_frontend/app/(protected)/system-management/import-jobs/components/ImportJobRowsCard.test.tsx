import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { ImportJobRowsCard } from './ImportJobRowsCard';
import type { ImportJobResultEnvelope, ImportJobRow } from '../types/importJob.types';

const useImportJobRows = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useImportJobs', () => ({ useImportJobRows }));
vi.mock('../services/importJobService', () => ({
  downloadImportJobRowsCsv: vi.fn(),
}));

const ROWS: ImportJobRow[] = [
  {
    id: 'r1',
    row_number: 3482,
    outcome: 'skipped',
    code: 'order_not_found',
    label: 'Order not found',
    message: 'Order not found: 202607-3978',
    value: '202607-3978',
    identity: { doc_no: '202607-3978', item_code: 'SRTKT1861SS', location: 'BRW-RSV', qty: 14 },
  },
  {
    id: 'r2',
    row_number: 3483,
    outcome: 'failed',
    code: 'row_error',
    label: 'Row could not be written',
    message: 'numeric field overflow',
    value: 'DO-9',
    identity: { doc_no: 'DO-9' },
  },
];

const RESULT: ImportJobResultEnvelope = {
  breakdown: {
    successful: [{ code: 'created', label: 'Order line created', count: 1 }],
    skipped: [{ code: 'order_not_found', label: 'Order not found', count: 751 }],
    failed: [{ code: 'row_error', label: 'Row could not be written', count: 5 }],
  },
};

/** DataGrid pulls saved column preferences through react-query, so it needs a client. */
function render(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockQuery(overrides: Record<string, unknown> = {}) {
  useImportJobRows.mockReturnValue({
    data: { data: ROWS, pagination: { total: ROWS.length, page: 1, limit: 25 }, empty: false },
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  });
}

describe('ImportJobRowsCard', () => {
  beforeEach(() => {
    useImportJobRows.mockReset();
  });

  it('renders each captured row with its reason and business identity', () => {
    mockQuery();
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} />);

    expect(screen.getByText('3482')).toBeInTheDocument();
    expect(screen.getByText('Order not found')).toBeInTheDocument();
    expect(screen.getByText('Order not found: 202607-3978')).toBeInTheDocument();
    expect(screen.getByText(/doc no: 202607-3978/)).toBeInTheDocument();
    expect(screen.getByText(/item code: SRTKT1861SS/)).toBeInTheDocument();
  });

  it('shows how many rows match the current filters', () => {
    mockQuery();
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} />);
    expect(screen.getByText('2 matching')).toBeInTheDocument();
  });

  it('renders an empty state when nothing was captured', () => {
    mockQuery({
      data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    });
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} />);
    expect(screen.getByText('No per-row detail was captured for this job.')).toBeInTheDocument();
    expect(screen.getByText(/retention window/i)).toBeInTheDocument();
  });

  it('distinguishes "no match" from "nothing captured"', () => {
    mockQuery({
      data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    });
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} codeFilter="order_not_found" />);
    expect(screen.getByText('No rows match these filters.')).toBeInTheDocument();
  });

  it('surfaces a load error', () => {
    mockQuery({
      data: undefined,
      isError: true,
      error: new Error('Failed to fetch import job rows'),
    });
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} />);
    expect(screen.getByText('Failed to fetch import job rows')).toBeInTheDocument();
  });

  it('says so when row capture was truncated', () => {
    mockQuery();
    render(
      <ImportJobRowsCard
        jobId="job-1"
        result={{ ...RESULT, rows_truncated: true, rows_total: 200 }}
      />,
    );
    expect(screen.getByText(/showing the first 200 rows captured/i)).toBeInTheDocument();
  });

  it('disables the CSV export when there is nothing to export', () => {
    mockQuery({
      data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    });
    render(<ImportJobRowsCard jobId="job-1" result={RESULT} />);
    expect(screen.getByRole('button', { name: /Download CSV/i })).toBeDisabled();
  });

  it('passes the active filters to the query', () => {
    mockQuery();
    render(
      <ImportJobRowsCard
        jobId="job-1"
        result={RESULT}
        outcomeFilter="skipped"
        codeFilter="order_not_found"
      />,
    );
    expect(useImportJobRows).toHaveBeenCalledWith(
      'job-1',
      expect.objectContaining({ outcome: 'skipped', code: 'order_not_found' }),
    );
  });
});
