/**
 * FILTER-MULTISELECT PR2: the import job rows card's Outcome and Reason (code) filters take several
 * values (OR within a filter, AND across). The card is controlled, so the values travel to its parent
 * comma-joined through onChangeOutcome / onChangeCode and back in as outcomeFilter / codeFilter, and on
 * to the rows query. The "All" placeholders are never values. Harness mirrors ImportJobRowsCard.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render as rtlRender, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactElement } from 'react';
import { ImportJobRowsCard } from './ImportJobRowsCard';
import type { ImportJobResultEnvelope } from '../types/importJob.types';

const useImportJobRows = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useImportJobs', () => ({ useImportJobRows }));
vi.mock('../services/importJobService', () => ({ downloadImportJobRowsCsv: vi.fn() }));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const RESULT: ImportJobResultEnvelope = {
  breakdown: {
    successful: [{ code: 'created', label: 'Order line created', count: 1 }],
    skipped: [{ code: 'order_not_found', label: 'Order not found', count: 751 }],
    failed: [{ code: 'row_error', label: 'Row could not be written', count: 5 }],
  },
};

function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Holds the filters the way the job detail page does, as strings. */
function Harness({ onOutcome, onCode }: { onOutcome: (v: string) => void; onCode: (v: string) => void }) {
  const [outcome, setOutcome] = useState('');
  const [code, setCode] = useState('');
  return (
    <ImportJobRowsCard
      jobId="job-1"
      result={RESULT}
      outcomeFilter={outcome}
      codeFilter={code}
      onChangeOutcome={(v) => { onOutcome(v); setOutcome(v); }}
      onChangeCode={(v) => { onCode(v); setCode(v); }}
    />
  );
}

const lastQuery = () => {
  const calls = useImportJobRows.mock.calls;
  return calls[calls.length - 1][1] as Record<string, unknown>;
};

beforeEach(() => {
  useImportJobRows.mockReset();
  useImportJobRows.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true },
    isLoading: false, isError: false, error: null,
  });
});
afterEach(() => cleanup());

describe('Import job rows - multi Outcome and Reason filters', () => {
  it('are two multi controls, Outcome then Reason', async () => {
    render(<Harness onOutcome={vi.fn()} onCode={vi.fn()} />);
    await screen.findByText('Rows');
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two outcomes go to the parent and the query comma-joined, never with the All placeholder', async () => {
    const user = userEvent.setup();
    const onOutcome = vi.fn();
    render(<Harness onOutcome={onOutcome} onCode={vi.fn()} />);
    const [outcome] = await screen.findAllByRole('listbox');
    await user.selectOptions(outcome, ['skipped', 'failed']);
    await waitFor(() => expect(onOutcome).toHaveBeenLastCalledWith('skipped,failed'));
    await waitFor(() => expect(lastQuery().outcome).toBe('skipped,failed'));
  });

  it('two reasons go to the parent and the query comma-joined', async () => {
    const user = userEvent.setup();
    const onCode = vi.fn();
    render(<Harness onOutcome={vi.fn()} onCode={onCode} />);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['order_not_found', 'row_error']);
    await waitFor(() => expect(onCode).toHaveBeenLastCalledWith('order_not_found,row_error'));
    await waitFor(() => expect(lastQuery().code).toBe('order_not_found,row_error'));
  });

  it('the filters AND across each other and Clear drops both', async () => {
    const user = userEvent.setup();
    render(<Harness onOutcome={vi.fn()} onCode={vi.fn()} />);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[0], ['skipped', 'failed']);
    await user.selectOptions(boxes[1], ['row_error']);
    await waitFor(() => expect(lastQuery()).toMatchObject({ outcome: 'skipped,failed', code: 'row_error' }));
    await user.click(screen.getByRole('button', { name: /clear/i }));
    await waitFor(() => expect(lastQuery().outcome).toBeUndefined());
    expect(lastQuery().code).toBeUndefined();
  });
});
