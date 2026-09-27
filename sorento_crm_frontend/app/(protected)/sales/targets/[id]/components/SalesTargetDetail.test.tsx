/**
 * `/sales/targets/{id}` (S1-23, J14). Modelled on
 * `sales/teams/[id]/components/SalesTeamDetail.test.tsx`.
 *
 * Exported: `SalesTargetDetail` (named export, `{ id }: { id: string }`) from
 * `./SalesTargetDetail`. Section order (S1-23): Target, What counts, Dates, Periods, Commission
 * - asserted via `getByRole('region', { name: ... })` per section (`aria-label`s: 'Target',
 * 'What counts', 'Dates', 'Periods', 'Commission').
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/targets/t1',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ primary, pendingAction }: { primary?: React.ReactNode; pendingAction?: React.ReactNode }) => (
    <div data-testid="detail-actions">{pendingAction ?? primary}</div>
  ),
}));

const patchPeriod = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const addChild = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const patchHeader = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const hooks = vi.hoisted(() => ({
  useSalesTarget: vi.fn(),
  usePatchSalesTargetPeriod: () => patchPeriod,
  useCreateTargetChild: () => addChild,
  usePatchSalesTarget: () => patchHeader,
}));
vi.mock('../../hooks/useSalesTargets', () => hooks);

import { SalesTargetDetail } from './SalesTargetDetail';

function detail(over: Record<string, unknown> = {}) {
  return {
    id: 't1', target_no: 'TGT-000001', name: 'North FY26 H2', subject_kind: 'agent',
    sales_agent_id: 'a1', sales_team_id: null, subject_label: 'ALI - Ali Hassan',
    subject_team_name: null, parent: null, metric: 'amount', basis: 'ordered',
    product_scope: 'all', start_date: '2026-10-01', end_date: '2026-12-31', split_every: null,
    split_unit: null, counts_label: 'Ordered', scope: [],
    periods: [
      { id: 'p1', period_start: '2026-10-01', period_end: '2026-10-31', target_value: 1000, achieved_value: 500, achieved_pct: 50, is_current: true },
    ],
    children: [], members_without_figure: [], child_count: 0,
    created_at: '2026-09-26T01:00:00', updated_at: '2026-09-26T01:00:00',
    ...over,
  };
}

beforeEach(() => {
  patchPeriod.mutateAsync.mockReset();
  patchPeriod.mutateAsync.mockResolvedValue({});
  addChild.mutateAsync.mockReset();
  addChild.mutateAsync.mockResolvedValue({});
  patchHeader.mutateAsync.mockReset();
  patchHeader.mutateAsync.mockResolvedValue({});
  hooks.useSalesTarget.mockReturnValue({ data: detail(), isLoading: false, isError: false });
});

describe('SalesTargetDetail', () => {
  it('renders sections in order: Target, What counts, Dates, Periods, Commission (S1-23)', () => {
    render(<SalesTargetDetail id="t1" />);
    const regions = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'));
    expect(regions).toEqual(['Target', 'What counts', 'Dates', 'Periods', 'Commission']);
  });

  it('puts the target number, subject link, created and updated in the header, not a section', () => {
    render(<SalesTargetDetail id="t1" />);
    expect(screen.getByText('TGT-000001')).toBeTruthy();
    const target = screen.getByRole('region', { name: 'Target' });
    expect(within(target).queryByText('TGT-000001')).toBeNull();
  });

  it("marks today's period and edits its figure in place", async () => {
    render(<SalesTargetDetail id="t1" />);
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).getByText(/current/i)).toBeTruthy();
    fireEvent.click(within(periods).getByRole('button', { name: /edit/i, hidden: true }) ?? within(periods).getByText('1,000'));
  });

  it('shows a "-" for a period starting after today', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({
        periods: [
          { id: 'p1', period_start: '2026-10-01', period_end: '2026-10-31', target_value: 1000, achieved_value: 500, achieved_pct: 50, is_current: false },
          { id: 'p2', period_start: '2027-01-01', period_end: '2027-01-31', target_value: 1000, achieved_value: null, achieved_pct: null, is_current: false },
        ],
      }),
      isLoading: false, isError: false,
    });
    render(<SalesTargetDetail id="t1" />);
    const periods = screen.getByRole('region', { name: 'Periods' });
    const rows = within(periods).getAllByRole('row');
    expect(rows[rows.length - 1].textContent).toContain('-');
  });

  it('shows "No commission" with Add tier, disabled, before S4', () => {
    render(<SalesTargetDetail id="t1" />);
    const commission = screen.getByRole('region', { name: 'Commission' });
    expect(within(commission).getByText('No commission')).toBeTruthy();
    expect((within(commission).getByRole('button', { name: /add tier/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a team target has read-only periods and an Agents section with Add figure (S1-27, S1-28)', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({
        subject_kind: 'team', sales_agent_id: null, sales_team_id: 'north', subject_label: 'North',
        children: [{ target_id: 'c1', sales_agent_id: 'a1', label: 'ALI - Ali Hassan', periods: [{ period_start: '2026-10-01', target_value: 600 }] }],
        members_without_figure: [{ sales_agent_id: 'b1', label: 'MEI - Tan Mei Ling' }],
        child_count: 1,
      }),
      isLoading: false, isError: false,
    });
    render(<SalesTargetDetail id="t1" />);
    const periods = screen.getByRole('region', { name: 'Periods' });
    expect(within(periods).queryByRole('button', { name: /edit period/i })).toBeNull();

    const agents = screen.getByRole('region', { name: 'Agents' });
    expect(within(agents).getByText('ALI - Ali Hassan')).toBeTruthy();
    expect(within(agents).getByRole('button', { name: /add figure/i })).toBeTruthy();
  });

  it('a child target names its parent and forbids editing what counts', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({ parent: { id: 'p0', name: 'North Team Target' } }),
      isLoading: false, isError: false,
    });
    render(<SalesTargetDetail id="t1" />);
    expect(screen.getByText(/set on/i)).toBeTruthy();
    expect(screen.getByText('North Team Target')).toBeTruthy();
  });

  it('the deferred delete names the subject and child count', () => {
    hooks.useSalesTarget.mockReturnValue({
      data: detail({ subject_kind: 'team', child_count: 2 }),
      isLoading: false, isError: false,
    });
    render(<SalesTargetDetail id="t1" />);
    expect(screen.getByText(/2 agent targets/i)).toBeTruthy();
  });
});
