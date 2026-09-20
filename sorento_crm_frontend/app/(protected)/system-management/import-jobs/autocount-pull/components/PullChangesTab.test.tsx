/**
 * PullChangesTab - Outcome / Reason filters (E1, small-fix track, fix round 2).
 *
 * `ImportJobRowsCard`'s outcome/code filters are CONTROLLED props - the generic job page owns
 * that state itself because its own Outcome breakdown card drives it too. `PullChangesTab`
 * rendered `ImportJobRowsCard` with none of the four (`outcomeFilter`/`codeFilter`/
 * `onChangeOutcome`/`onChangeCode`), so picking anything in either select changed nothing.
 *
 * Real `ImportJobRowsCard` -> real `useImportJobRows`, only the rows SERVICE
 * (`getImportJobRows`) mocked. `SearchableSelect` is stubbed as a deterministic native
 * `<select>` (same technique as `product-discontinued-scope-editor.test.tsx` /
 * `RunPlanningModal.test.tsx`) so a pick is a plain `fireEvent.change`, not a Radix popover
 * interaction.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const getImportJobRows = vi.fn();
const downloadImportJobRowsCsv = vi.fn();
vi.mock('../../services/importJobService', () => ({
  getImportJobRows: (...a: unknown[]) => getImportJobRows(...a),
  downloadImportJobRowsCsv: (...a: unknown[]) => downloadImportJobRowsCsv(...a),
}));

import { PullChangesTab } from './PullChangesTab';

const JOB_ID = 'job-1';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PullChangesTab jobId={JOB_ID} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getImportJobRows.mockReset();
  downloadImportJobRowsCsv.mockReset();
  getImportJobRows.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true });
});

describe('PullChangesTab - Outcome filter actually filters (E1)', () => {
  it('has no Reason select - a pull job never has a breakdown to offer reasons from', async () => {
    renderTab();
    await waitFor(() => expect(getImportJobRows).toHaveBeenCalledTimes(1));
    expect(screen.queryByLabelText('All reasons')).not.toBeInTheDocument();
  });

  it('picking Failed calls the rows service with outcome: failed, page index 0', async () => {
    renderTab();
    await waitFor(() => expect(getImportJobRows).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('All outcomes'), { target: { value: 'failed' } });

    await waitFor(() =>
      expect(getImportJobRows).toHaveBeenLastCalledWith(
        JOB_ID,
        expect.objectContaining({ outcome: 'failed', pageIndex: 0 }),
      ),
    );
  });

  it('Clear resets the outcome filter back to all', async () => {
    renderTab();
    await waitFor(() => expect(getImportJobRows).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('All outcomes'), { target: { value: 'failed' } });
    await waitFor(() =>
      expect(getImportJobRows).toHaveBeenLastCalledWith(
        JOB_ID,
        expect.objectContaining({ outcome: 'failed' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: /clear/i }));

    // The `outcome: undefined` key is already cached fresh from the very first render (same
    // params), so React Query serves it without a further `getImportJobRows` call - the
    // control's own value resetting is what proves `PullChangesTab` threaded Clear through.
    await waitFor(() => expect(screen.getByLabelText('All outcomes')).toHaveValue(''));
  });
});
