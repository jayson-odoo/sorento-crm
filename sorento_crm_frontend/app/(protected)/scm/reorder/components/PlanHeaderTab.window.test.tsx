/**
 * AC-S4.5 (PLAN-reorder-feedback-9sep.md, S4) - the header tab reads the window with
 * `describeWindow`, both in read mode and via two inputs in Edit.
 *
 * Read-only render harness copied from `PlanHeaderTab.test.tsx` (mocks + `makeRun`/
 * `renderTab` shape) rather than editing that file - this is a NEW file so the coder's own
 * S1/S2 slice (`PlanHeaderTab.tsx` / `.test.tsx`) is never touched here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import type { ReorderRun } from '../types/reorder.types';

type StubOption = { value: string; label: string };

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

function makeRun(over: Record<string, unknown> = {}): ReorderRun {
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
  } as unknown as ReorderRun;
}

function renderTab(run: ReorderRun, unsavedCount = 0) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlanHeaderTab runId={run.run_id} run={run} unsavedCount={unsavedCount} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('PlanHeaderTab - window wording (AC-S4.5)', () => {
  it('both dates set reads "Sales orders needed: X to Y"', () => {
    renderTab(makeRun({
      plan_horizon_start: '2025-01-01', plan_horizon_date: '2026-10-31',
    }));
    expect(screen.getByText(/Sales orders needed/)).toBeInTheDocument();
    expect(screen.getByText('01/01/2025 to 31/10/2026')).toBeInTheDocument();
  });

  it('end only reads "up to Y"', () => {
    renderTab(makeRun({ plan_horizon_start: null, plan_horizon_date: '2026-10-31' }));
    expect(screen.getByText('up to 31/10/2026')).toBeInTheDocument();
  });

  it('start only reads "from X"', () => {
    renderTab(makeRun({ plan_horizon_start: '2025-01-01', plan_horizon_date: null }));
    expect(screen.getByText('from 01/01/2025')).toBeInTheDocument();
  });

  it('neither set reads "every open order"', () => {
    renderTab(makeRun({ plan_horizon_start: null, plan_horizon_date: null }));
    expect(screen.getByText('every open order')).toBeInTheDocument();
  });

  it('Edit exposes BOTH a From and a To date input', () => {
    renderTab(makeRun({ plan_horizon_start: '2025-01-01', plan_horizon_date: '2026-10-31' }));
    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));

    expect(screen.getByLabelText('From')).toBeInTheDocument();
    expect(screen.getByLabelText('To')).toBeInTheDocument();
  });
});
