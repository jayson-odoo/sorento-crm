/**
 * Sales > Opportunities (UAC S2-12, S2-13; plan 3.4, 3.5, section 16).
 *
 * DataGrid with fixed layout and resizable columns, one row per opportunity: number, title,
 * customer or prospect, stage Badge, amount, close date, Source (Portal/CRM). `rowHref` to
 * the detail page; `Log opportunity` is the header's one primary action, gated on
 * `sales.opportunities.add`.
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
  usePathname: () => '/sales/opportunities',
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

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

const hooks = vi.hoisted(() => ({ useSalesOpportunities: vi.fn() }));
vi.mock('../hooks/useSalesOpportunities', () => hooks);

vi.mock('./SalesOpportunityModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div role="dialog">opportunity modal</div> : null),
}));

import SalesOpportunitiesView from './SalesOpportunitiesView';
import type { SalesOpportunityListItem } from '../types/salesOpportunity.types';

function opportunity(over: Partial<SalesOpportunityListItem> = {}): SalesOpportunityListItem {
  return {
    id: 'opp-1',
    opportunity_no: 'OPP-000001',
    title: 'ZZT Basins Deal',
    customer_id: 'cust-1',
    customer_name: 'ZZT Dealer',
    prospect_name: null,
    stage_key: 'new',
    stage_label: 'New',
    expected_amount: '10000.00',
    expected_close_date: '2026-11-01',
    source: 'crm',
    sales_agent_label: 'ALI - Ali Hassan',
    ...over,
  };
}

function withOpportunities(data: SalesOpportunityListItem[]) {
  hooks.useSalesOpportunities.mockReturnValue({
    data: { data, pagination: { total: data.length, page: 1, limit: 50 }, empty: data.length === 0 },
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  perms.granted = new Set(['sales.opportunities.view', 'sales.opportunities.add']);
  hooks.useSalesOpportunities.mockReset();
});

describe('SalesOpportunitiesView', () => {
  it('titles the page with Log opportunity as the header action', () => {
    withOpportunities([opportunity()]);
    render(<SalesOpportunitiesView />);
    const actions = screen.getByTestId('header-actions');
    fireEvent.click(within(actions).getByRole('button', { name: /log opportunity/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('draws a prospect name when there is no customer', () => {
    withOpportunities([
      opportunity({ id: 'opp-2', customer_id: null, customer_name: null, prospect_name: 'ZZT Prospect Co' }),
    ]);
    render(<SalesOpportunitiesView />);
    expect(screen.getByText('ZZT Prospect Co')).toBeTruthy();
  });

  it('shows the Source as Portal or CRM', () => {
    withOpportunities([
      opportunity({ id: 'opp-portal', source: 'portal' }),
      opportunity({ id: 'opp-crm', source: 'crm' }),
    ]);
    render(<SalesOpportunitiesView />);
    expect(screen.getByText('Portal')).toBeTruthy();
    expect(screen.getByText('CRM')).toBeTruthy();
  });

  it('links each row to its detail page', () => {
    withOpportunities([opportunity()]);
    render(<SalesOpportunitiesView />);
    const link = screen.getByRole('link', { name: /ZZT Basins Deal/i });
    expect(link.getAttribute('href')).toBe('/sales/opportunities/opp-1');
  });

  it('offers no Log opportunity to a role without sales.opportunities.add', () => {
    perms.granted = new Set(['sales.opportunities.view']);
    withOpportunities([]);
    render(<SalesOpportunitiesView />);
    expect(screen.queryByRole('button', { name: /log opportunity/i })).toBeNull();
  });

  it('shows the empty state with no opportunities', () => {
    withOpportunities([]);
    render(<SalesOpportunitiesView />);
    expect(screen.getByText(/no opportunities/i)).toBeTruthy();
  });

  it('shows a loading state', () => {
    hooks.useSalesOpportunities.mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
      isError: false,
      refetch: vi.fn(),
    });
    render(<SalesOpportunitiesView />);
    expect(screen.queryByText(/no opportunities/i)).toBeNull();
  });

  it('shows an error state', () => {
    hooks.useSalesOpportunities.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: true,
      refetch: vi.fn(),
    });
    render(<SalesOpportunitiesView />);
    expect(screen.getByText(/failed to load/i)).toBeTruthy();
  });
});
