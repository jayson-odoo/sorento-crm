/**
 * #1340: the scm_reorder_run scope block on the scheduled task config page.
 *
 * `ScmReorderRunScopeFields` (`components/ScmReorderRunScopeFields.tsx`) does not exist
 * yet, and `ScheduledTaskForm` does not render it for any task key yet - every assertion
 * below about the block's labels/controls is red until the coder wires it in (AC-8: the
 * block shows only on the `scm_reorder_run` task page, every select is the system
 * dropdown, and it pre-fills from `task.metadata`).
 *
 * `SearchableSelect`/`SearchableMultiSelect` are stubbed as plain native controls so
 * selection is deterministic in jsdom - the same technique
 * `app/(protected)/scm/reorder/components/RunPlanningModal.test.tsx` uses for the same
 * two components.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ScheduledTaskForm } from './ScheduledTaskForm';
import type { ScheduledTask } from '../types/scheduledTask.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

type StubOption = { value: string; label: string };

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    placeholder,
    clearable,
  }: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options: StubOption[];
    placeholder?: string;
    clearable?: boolean;
  }) => {
    const rows = clearable ? [{ value: '', label: placeholder ?? 'All' }, ...options] : options;
    return (
      <select
        id={id}
        data-testid={id}
        aria-label={placeholder ?? id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {rows.map((o) => (
          <option key={o.value || '__all__'} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    fetchOptions,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: StubOption[];
    fetchOptions?: (query: string) => Promise<StubOption[]>;
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
      </div>
    );
  },
}));

vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => ({
  getCompaniesSelect: () => Promise.resolve([]),
}));

vi.mock('@/app/(protected)/scm/hooks/useScmOptions', () => ({
  useWarehouseOptions: () => ({
    data: [
      { value: 'WH1', label: 'Warehouse One' },
      { value: 'WH2', label: 'Warehouse Two' },
    ],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/app/(protected)/scm/services/scmOptionsService', () => ({
  searchProductOptions: () =>
    Promise.resolve([{ value: 'P1', label: 'P1 - Product One' }]),
}));

const BASE_TASK: ScheduledTask = {
  id: 'task-1',
  key: 'scm_reorder_run',
  name: 'Scheduled reorder run',
  description: null,
  enabled: true,
  interval_unit: 'days',
  interval_value: 1,
  timezone: 'Asia/Kuala_Lumpur',
  start_at: null,
  next_run_at: null,
  last_run_at: null,
  last_status: null,
  last_error: null,
  metadata: {},
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-01T00:00:00',
  due_at: null,
  grace_percent: null,
  grace_seconds: null,
  is_overdue: false,
  late_by_seconds: null,
};

function renderForm(task: ScheduledTask) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ScheduledTaskForm task={task} onSubmit={() => {}} />
    </QueryClientProvider>,
  );
}

describe('ScheduledTaskForm - scm_reorder_run scope block', () => {
  it('renders the scope block for the scm_reorder_run task', () => {
    renderForm(BASE_TASK);

    expect(screen.getByText('Warehouses')).toBeInTheDocument();
    expect(screen.getByText('Demand')).toBeInTheDocument();
    expect(screen.getByText('Sales orders needed')).toBeInTheDocument();
    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.getByText('Budget')).toBeInTheDocument();
    expect(screen.getByText('Market insight')).toBeInTheDocument();

    const demand = screen.getByTestId('scm-demand');
    expect(demand).toBeInTheDocument();
    expect(demand).toHaveAttribute('aria-label', 'All');
  });

  it('does not render the scope block for a different task key', () => {
    renderForm({ ...BASE_TASK, key: 'system_health_watchdog' });

    expect(screen.queryByText('Warehouses')).not.toBeInTheDocument();
    expect(screen.queryByText('Market insight')).not.toBeInTheDocument();
    expect(screen.queryByTestId('scm-demand')).not.toBeInTheDocument();
  });

  it('pre-fills the scope block from task.metadata', async () => {
    renderForm({
      ...BASE_TASK,
      metadata: {
        warehouse_codes: ['WH1'],
        demand_class: 'retail',
        horizon_end_days: 30,
        budget: 5000,
        include_market: true,
      },
    });

    expect(await screen.findByTestId('scm-demand')).toHaveValue('retail');
    expect(screen.getByRole('checkbox', { name: 'Warehouse One' })).toBeChecked();
    const horizonEnd = document.getElementById('scm-horizon-end') as HTMLInputElement | null;
    expect(horizonEnd?.value).toBe('30');
    const budget = document.getElementById('scm-budget') as HTMLInputElement | null;
    expect(budget?.value).toBe('5000');
    expect(screen.getByRole('switch', { name: 'Market insight' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });
});
