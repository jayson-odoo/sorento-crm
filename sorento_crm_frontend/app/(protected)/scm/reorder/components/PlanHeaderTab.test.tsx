/**
 * PlanHeaderTab (S5, plan 5.1, AC-5.1/AC-5.2). Review S7: scope round-trip through
 * Edit -> Re-plan, `canReplan` gating (superseded / not-yet-completed runs offer no Edit),
 * past-cut-off validation, the unsaved-changes guard (review S5) and the cut-off prefill
 * clamp (review nit).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRun } from '../types/reorder.types';

/** The confirm button INSIDE the open AlertDialog - scoped rather than a bare
 *  `getByRole('button', { name: 'Re-plan' })`, which is ambiguous while the toolbar's own
 *  "Re-plan" button is still present (behind the dialog) in the DOM. */
function dialogButton(name: RegExp) {
  return within(screen.getByRole('alertdialog')).getByRole('button', { name });
}

type StubOption = { value: string; label: string };

// Same deterministic stub `RunPlanningModal.test.tsx` uses - a group of checkboxes plus a
// search box for the async (products) instance, and rendered chips for `selectedOptions` so
// a pre-filled edit is directly assertable.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    fetchOptions,
    selectedOptions,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: StubOption[];
    fetchOptions?: (query: string) => Promise<StubOption[]>;
    selectedOptions?: StubOption[];
    placeholder?: string;
  }) => {
    const [fetched, setFetched] = React.useState<StubOption[]>([]);
    React.useEffect(() => {
      if (!fetchOptions) return;
      let live = true;
      void fetchOptions('').then((rows) => {
        if (live) setFetched(rows);
      });
      return () => {
        live = false;
      };
    }, [fetchOptions]);
    const rows = fetchOptions ? fetched : (options ?? []);
    return (
      <div aria-label={placeholder ?? 'multi-select'}>
        {rows.map((o) => (
          <label key={o.value}>
            <input
              type="checkbox"
              aria-label={o.label}
              checked={value.includes(o.value)}
              onChange={(e) =>
                onChange(
                  e.target.checked ? [...value, o.value] : value.filter((x) => x !== o.value),
                )
              }
            />
            {o.label}
          </label>
        ))}
        {(selectedOptions ?? []).map((o) => (
          <span key={o.value} data-testid={`chip-${placeholder}`}>
            {o.label}
          </span>
        ))}
      </div>
    );
  },
}));

vi.mock('../../hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({
    data: [
      { value: 'BRW', label: 'Butterworth' },
      { value: 'MWH', label: 'Main WH' },
    ],
    isLoading: false,
    isError: false,
  }),
}));

const searchProductOptions = vi.fn(async (): Promise<StubOption[]> => [
  { value: 'SRTWT7408', label: 'SRTWT7408 - Wall-hung WC 7408' },
]);
vi.mock('../../services/scmOptionsService', () => ({
  searchProductOptions: () => searchProductOptions(),
}));

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

const { replanReorderRunMock } = vi.hoisted(() => ({ replanReorderRunMock: vi.fn() }));
vi.mock('../services/reorderRunService', () => ({
  replanReorderRun: (...args: unknown[]) => replanReorderRunMock(...args),
}));

import { PlanHeaderTab } from './PlanHeaderTab';

function makeRun(over: Partial<ReorderRun> = {}): ReorderRun {
  return {
    run_id: 'run-1',
    status: 'completed',
    stage: 'writing_recommendations',
    buy_scope: 'warehouse',
    summary: {
      buy_count: 10,
      disposition_count: 0,
      exception_count: 0,
      total_cash_impact: 5000,
      recommendation_count: 12,
    },
    error: null,
    plan_horizon_date: null,
    started_at: '2026-09-01T00:30:00',
    warehouse_codes: [],
    is_all_warehouses: true,
    product_codes: null,
    supersedes_run_id: null,
    superseded_by_run_id: null,
    ...over,
  } as ReorderRun;
}

function renderTab(run: ReorderRun, unsavedCount = 0) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlanHeaderTab runId={run.run_id} run={run} unsavedCount={unsavedCount} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  replanReorderRunMock.mockResolvedValue({
    run_id: 'run-2',
    status: 'running',
    stage: 'resolving_policies',
    buy_scope: 'warehouse',
    summary: null,
    error: null,
    supersedes_run_id: 'run-1',
  });
});

describe('PlanHeaderTab - canReplan gating (review S7)', () => {
  it('offers Edit on a completed, not-yet-superseded run', () => {
    renderTab(makeRun());
    expect(screen.getByRole('button', { name: /Edit/i })).toBeInTheDocument();
  });

  it('offers no Edit once the run has been superseded', () => {
    renderTab(makeRun({ superseded_by_run_id: 'run-9' }));
    expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument();
    expect(screen.getByText(/superseded by a newer plan/i)).toBeInTheDocument();
  });

  it('the backend-completed guard is mirrored: no Edit on a legacy non-completed shape', () => {
    renderTab(makeRun({ status: 'failed' as ReorderRun['status'] }));
    expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument();
  });
});

describe('PlanHeaderTab - scope round-trip through Edit -> Re-plan (review S7)', () => {
  it('pre-fills the edit form from the run and sends it back unchanged', async () => {
    const run = makeRun({
      warehouse_codes: ['BRW'],
      is_all_warehouses: false,
      product_codes: ['SRTWT7408'],
      plan_horizon_date: '2099-12-31', // safely in the future, never clamped
    });
    renderTab(run);

    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    // Warehouses is the STATIC-options select (mirrors `RunPlanningModal`): the pre-filled
    // pick shows as a CHECKED option, not a `selectedOptions` chip - only the fetch-mode
    // Products field passes that prop, since its labels come from a search rather than a
    // list already on screen.
    expect(await screen.findByLabelText('Butterworth')).toBeChecked();
    expect(await screen.findByTestId('chip-All products')).toHaveTextContent(
      'SRTWT7408 - Wall-hung WC 7408',
    );
    expect(screen.getByLabelText('Sales order cut-off')).toHaveValue('2099-12-31');

    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    await screen.findByRole('alertdialog');
    fireEvent.click(dialogButton(/^Re-plan$/i));

    await waitFor(() => expect(replanReorderRunMock).toHaveBeenCalledTimes(1));
    expect(replanReorderRunMock).toHaveBeenCalledWith('run-1', {
      warehouse_codes: ['BRW'],
      product_codes: ['SRTWT7408'],
      plan_horizon_date: '2099-12-31',
    });
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/scm/reorder/run-2'));
  });

  it('an unnarrowed run round-trips as empty scope (still means "all")', async () => {
    const run = makeRun(); // is_all_warehouses true, product_codes null
    renderTab(run);
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    await screen.findByRole('alertdialog');
    fireEvent.click(dialogButton(/^Re-plan$/i));
    await waitFor(() => expect(replanReorderRunMock).toHaveBeenCalledTimes(1));
    expect(replanReorderRunMock).toHaveBeenCalledWith('run-1', {
      warehouse_codes: [],
      product_codes: [],
      plan_horizon_date: null,
    });
  });
});

describe('PlanHeaderTab - past cut-off validation (review S7)', () => {
  it('blocks Re-plan and explains why, without opening the confirm dialog', async () => {
    renderTab(makeRun());
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.change(screen.getByLabelText('Sales order cut-off'), {
      target: { value: '2000-01-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    expect(
      await screen.findByText(/cut-off cannot be in the past/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/starts a new plan with the values above/i)).not.toBeInTheDocument();
    expect(replanReorderRunMock).not.toHaveBeenCalled();
  });
});

describe('PlanHeaderTab - the cut-off prefill is clamped to today (review nit)', () => {
  it('a stored cut-off already in the past opens the edit form at today, not the stale date', () => {
    renderTab(makeRun({ plan_horizon_date: '2000-01-01' }));
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    const input = screen.getByLabelText('Sales order cut-off') as HTMLInputElement;
    expect(input.value).not.toBe('2000-01-01');
    expect(input.value >= input.min).toBe(true);
  });
});

describe('PlanHeaderTab - unsaved-changes guard before Re-plan (review S5)', () => {
  it('warns before firing when the Lines tab carries unsaved decisions', async () => {
    renderTab(makeRun(), 3);
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    expect(
      await screen.findByText(/3 products carry changes nobody has saved/i),
    ).toBeInTheDocument();
    expect(replanReorderRunMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Continue anyway/i }));
    expect(
      await screen.findByText(/starts a new plan with the values above/i),
    ).toBeInTheDocument();
  });

  it('fires straight to the Re-plan confirm when nothing is unsaved', async () => {
    renderTab(makeRun(), 0);
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    expect(screen.queryByText(/carry changes nobody has saved/i)).not.toBeInTheDocument();
    expect(
      await screen.findByText(/starts a new plan with the values above/i),
    ).toBeInTheDocument();
  });
});

describe('PlanHeaderTab - counts (review nit: no Disposition tile, S2 always zeroes it)', () => {
  it('shows Buy/Exceptions/Recommendations/Cash impact, never Disposition', () => {
    renderTab(makeRun());
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('Exceptions')).toBeInTheDocument();
    expect(screen.getByText('Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Cash impact')).toBeInTheDocument();
    expect(screen.queryByText('Disposition')).not.toBeInTheDocument();
  });
});
