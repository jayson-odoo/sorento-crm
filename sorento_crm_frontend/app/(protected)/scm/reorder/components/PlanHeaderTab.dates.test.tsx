/**
 * DATE-PICKER-UNIFY slice B: PlanHeaderTab "Sales orders needed" is ONE typeable range field
 * in Edit, sending the same plan_horizon_start / plan_horizon_date to Re-plan.
 * Harness copied from PlanHeaderTab.test.tsx.
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
  useActiveWarehouseOptions: () => ({
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


const RANGE_PH = 'DD/MM/YYYY - DD/MM/YYYY';

function typeRange(el: HTMLElement, text: string) {
  fireEvent.change(el, { target: { value: text } });
  fireEvent.keyDown(el, { key: 'Enter' });
}

describe('PlanHeaderTab - dates (DATE-PICKER-UNIFY slice B)', () => {
  it('AC1/AC3: Edit shows the stored window as dd/mm/yyyy in ONE range field, no native input', () => {
    renderTab(makeRun({ plan_horizon_start: '2098-12-01', plan_horizon_date: '2099-12-31' }));
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getAllByPlaceholderText(RANGE_PH)).toHaveLength(1);
    expect(screen.getByPlaceholderText(RANGE_PH)).toHaveValue('01/12/2098 - 31/12/2099');
  });

  it('AC2/AC9: typing a range and pressing Enter re-plans with the same two params', async () => {
    renderTab(makeRun());
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    typeRange(screen.getByPlaceholderText(RANGE_PH), '01/11/2099 - 30/11/2099');
    fireEvent.click(screen.getByRole('button', { name: /^Re-plan$/i }));
    await screen.findByRole('alertdialog');
    fireEvent.click(dialogButton(/^Re-plan$/i));
    await waitFor(() => expect(replanReorderRunMock).toHaveBeenCalledTimes(1));
    expect(replanReorderRunMock).toHaveBeenCalledWith('run-1', {
      warehouse_codes: [],
      product_codes: [],
      plan_horizon_start: '2099-11-01',
      plan_horizon_date: '2099-11-30',
    });
  });
});
