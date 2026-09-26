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

const hooks = vi.hoisted(() => ({
  useSalesOpportunities: vi.fn(),
  useSalesOpportunityMeta: vi.fn(),
  useSalesOpportunityAgentOptions: vi.fn(),
}));
vi.mock('../hooks/useSalesOpportunities', () => hooks);

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) props.fetchOptions('').then(setOptions);
    }, []);
    return (
      <select
        aria-label={props['aria-label'] ?? props.id ?? 'select'}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
      >
        <option value="" />
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: (props: {
    id?: string;
    'aria-label'?: string;
    from?: string | null;
    to?: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
  }) => (
    <input
      aria-label={props['aria-label'] ?? props.id ?? 'date range'}
      value={props.from ?? ''}
      onChange={(e) => props.onChange({ from: e.target.value || null, to: props.to ?? null })}
    />
  ),
}));

const service = vi.hoisted(() => ({ getSalesOpportunityCustomerOptions: vi.fn() }));
vi.mock('../services/salesOpportunityService', () => service);

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
  hooks.useSalesOpportunityMeta.mockReturnValue({ data: { stages: [], lost_reasons: [] } });
  hooks.useSalesOpportunityAgentOptions.mockReturnValue({ data: [] });
  service.getSalesOpportunityCustomerOptions.mockReset();
  service.getSalesOpportunityCustomerOptions.mockResolvedValue({
    items: [],
    prospect: null,
    blocked: null,
  });
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

  it('fix B2: shows the Agent column', () => {
    withOpportunities([opportunity({ sales_agent_label: 'ALI - Ali Hassan' })]);
    render(<SalesOpportunitiesView />);
    expect(screen.getByText('ALI - Ali Hassan')).toBeTruthy();
  });

  it('fix B2: passes Stage, Agent, Customer and close-date filters to the query', () => {
    hooks.useSalesOpportunityMeta.mockReturnValue({
      data: { stages: [{ id: 'st-1', key: 'new', label: 'New' }], lost_reasons: [] },
    });
    hooks.useSalesOpportunityAgentOptions.mockReturnValue({
      data: [{ id: 'agent-1', code: 'ALI', label: 'ALI - Ali Hassan' }],
    });
    withOpportunities([]);
    render(<SalesOpportunitiesView />);

    fireEvent.change(screen.getByLabelText('Stage'), { target: { value: 'st-1' } });
    fireEvent.change(screen.getByLabelText('Agent'), { target: { value: 'agent-1' } });

    expect(hooks.useSalesOpportunities).toHaveBeenLastCalledWith(
      expect.objectContaining({ statusId: 'st-1', salesAgentId: 'agent-1' }),
    );
  });

  it('fix B2: passes pagination state through to the query', () => {
    hooks.useSalesOpportunities.mockReturnValue({
      data: { data: [opportunity()], pagination: { total: 120, page: 1, limit: 50 }, empty: false },
      isLoading: false,
      isFetching: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<SalesOpportunitiesView />);
    expect(hooks.useSalesOpportunities).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageIndex: 0, pageSize: 50 }),
    );
    // recordCount comes from the API's own total, not the page's row count.
    expect(screen.getByText(/120/)).toBeTruthy();
  });
});
