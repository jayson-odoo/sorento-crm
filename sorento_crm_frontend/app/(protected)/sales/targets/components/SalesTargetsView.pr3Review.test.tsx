/**
 * FILTER-MULTISELECT PR3 review: a team id the options do not hold (an old link) is never shown as its
 * own label. Uses the real SearchableMultiSelect.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const url = vi.hoisted(() => ({ search: '?tab=agent' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/targets',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
const hooks = vi.hoisted(() => ({
  useSalesTargets: vi.fn(),
  usePointRatios: () => ({ data: { rows: [] }, isLoading: false }),
  useSavePointRatio: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useImportDealerTargets: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDownloadDealerTemplate: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../hooks/useSalesTargets', () => hooks);
import SalesTargetsView from './SalesTargetsView';

const row = (id: string, team: string) => ({
  target_id: id, target_no: `TGT-${id}`, name: `ZZT ${id}`, subject_kind: 'agent', sales_agent_id: `ag-${id}`,
  sales_team_id: null, subject_label: `Agent ${id}`, team_id: team, team_name: `ZZT Team ${team}`, left_on: null,
  members: null, metric: 'amount', basis: 'ordered', product_scope: 'all', scope_labels: [], period_id: null,
  period_start: null, period_end: null, start_date: '2026-01-01', end_date: '2026-12-31', target_value: 100,
  achieved_value: 10, achieved_pct: 10, parent_target_id: null,
});
beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
  url.search = '?tab=agent';
  hooks.useSalesTargets.mockImplementation(() => ({
    data: { on: '2026-10-20', rows: [row('a', 'a'), row('b', 'b'), row('c', 'c')], unassigned_amount: 0, no_team_count: 0 },
    isLoading: false, isFetching: false, isError: false, isPlaceholderData: false,
  }));
});
afterEach(() => cleanup());

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;
const ORPHAN = '9f1b6c52-4d1e-4a39-8a77-0c2d5e8b1f34';

describe('Sales targets - a team id the options do not hold', () => {
  it('shows no UUID in the Team trigger or a chip', async () => {
    url.search = `?tab=agent&team=${ORPHAN}`;
    const user = userEvent.setup();
    render(<SalesTargetsView />);
    await screen.findByText('TGT-a');
    await user.click(screen.getByRole('button', { name: /^filters/i }));
    await screen.findByText('Team', { selector: 'label' });
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });
});
