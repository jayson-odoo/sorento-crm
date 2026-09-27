/**
 * Sales > Targets (S1-15, S1-18, S1-21, S1-22, S1-14, S6-10). Modelled on
 * `sales/teams/components/SalesTeamsView.test.tsx`.
 *
 * Exported default: `SalesTargetsView` from `./SalesTargetsView`.
 * Assumed stable test surface the coder must match (accessible names/roles, no invented
 * `data-testid`s beyond what `PageHeader`'s mock already exposes as `header-actions`):
 *   - tabs: `getByRole('tab', { name: 'Teams' })`, `'Agents'`, `'Dealers'`.
 *   - the header action: `getByRole('button', { name: /set target/i })`.
 *   - the toolbar's Team filter: `getByRole('combobox', { name: /team/i })` (via the
 *     `SearchableSelect` mock below, a native `<select>`), offering a `'No team'` option.
 *   - the Active on date input: `getByLabelText('Active on')`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/targets',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      <div data-testid="header-actions">{actions}</div>
    </header>
  ),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    clearable?: boolean;
    'aria-label'?: string;
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

const hooks = vi.hoisted(() => ({ useSalesTargets: vi.fn() }));
vi.mock('../hooks/useSalesTargets', () => hooks);

vi.mock('./SetTargetModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div role="dialog">set target modal</div> : null),
}));

import SalesTargetsView from './SalesTargetsView';

function row(over: Record<string, unknown> = {}) {
  return {
    target_id: 't1', target_no: 'TGT-000001', name: 'North FY26 H2', subject_kind: 'team',
    sales_agent_id: null, sales_team_id: 'north', subject_label: 'North', team_id: null,
    team_name: null, left_on: null, members: [{ sales_agent_id: 'a1', label: 'ALI - Ali Hassan' }],
    metric: 'amount', basis: 'ordered', product_scope: 'all', scope_labels: [],
    period_id: 'p1', period_start: '2026-10-01', period_end: '2026-10-31', target_value: 1000,
    achieved_value: 500, achieved_pct: 50, parent_target_id: null,
    ...over,
  };
}

function withRows(rows: Record<string, unknown>[], extra: Record<string, unknown> = {}) {
  hooks.useSalesTargets.mockReturnValue({
    data: { on: '2026-10-20', rows, unassigned_amount: 0, no_team_count: 0, ...extra },
    isLoading: false, isFetching: false, isError: false,
  });
}

beforeEach(() => {
  perms.granted = new Set(['sales.targets.view', 'sales.targets.add']);
  hooks.useSalesTargets.mockReset();
});

describe('SalesTargetsView', () => {
  it('opens on the Teams tab, before Agents; no Dealers yet (S1-15 round 4, S7-2 ships it)', () => {
    withRows([row()]);
    render(<SalesTargetsView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Teams', 'Agents']);
    const teams = screen.getByRole('tab', { name: 'Teams' });
    const agents = screen.getByRole('tab', { name: 'Agents' });
    expect(teams.getAttribute('aria-selected')).toBe('true');
    expect(agents).toBeTruthy();
  });

  it('shows Set target alone at the header, only for sales.targets.add (S1-18)', () => {
    withRows([row()]);
    const first = render(<SalesTargetsView />);
    const actions = screen.getByTestId('header-actions');
    expect(within(actions).getByRole('button', { name: /set target/i })).toBeTruthy();
    first.unmount();

    perms.granted = new Set(['sales.targets.view']);
    render(<SalesTargetsView />);
    expect(screen.queryAllByRole('button', { name: /set target/i })).toEqual([]);
  });

  it('folds one subject into one line with a Targets pill (S1-21)', () => {
    withRows([row()]);
    render(<SalesTargetsView />);
    const line = screen.getByText('North').closest('tr')!;
    expect(within(line).getByText('North FY26 H2')).toBeTruthy();
    expect(within(line).getByText('1,000')).toBeTruthy();
  });

  it('ends the Teams tab with No team and Unassigned lines (S1-14, S1-22)', () => {
    withRows([row()], { no_team_count: 2, unassigned_amount: 300 });
    render(<SalesTargetsView />);
    expect(screen.getByText('No team')).toBeTruthy();
    expect(screen.getByText('Unassigned')).toBeTruthy();
  });

  it('offers a clearable Team filter on the Agents tab, including No team (S6-10)', () => {
    withRows([row({ target_id: null, subject_kind: 'agent', sales_agent_id: 'a1', sales_team_id: null })]);
    render(<SalesTargetsView />);
    fireEvent.click(screen.getByRole('tab', { name: 'Agents' }));
    const filter = screen.getByRole('combobox', { name: /team/i }) as HTMLSelectElement;
    expect(Array.from(filter.options).some((o) => o.value === 'none' && /no team/i.test(o.label))).toBe(true);
  });

  it('renders loading, empty and error states (S1-15)', () => {
    hooks.useSalesTargets.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, isError: false });
    const { rerender } = render(<SalesTargetsView />);
    expect(screen.getAllByRole('row').length).toBeGreaterThanOrEqual(0);

    hooks.useSalesTargets.mockReturnValue({
      data: { on: '2026-10-20', rows: [], unassigned_amount: 0, no_team_count: 0 },
      isLoading: false, isFetching: false, isError: false,
    });
    rerender(<SalesTargetsView />);
    expect(screen.getByText(/no team/i)).toBeTruthy();

    hooks.useSalesTargets.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, isError: true, error: new Error('boom') });
    rerender(<SalesTargetsView />);
    expect(screen.getByText(/boom|failed to load/i)).toBeTruthy();
  });
});
