/**
 * PORTAL-P4-REQUESTS S6: every Sales Opportunity column header sorts (P4-23), for limited and staff alike.
 * Today Customer, Agent, Stage and Source are `enableSorting: false`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/opportunities',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (k: string) => ({ listing_key: k, config: null })),
  upsertUserListColumnConfig: vi.fn(async (k: string, c: unknown) => ({ listing_key: k, config: c })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
const hooks = vi.hoisted(() => ({ useSalesOpportunities: vi.fn(), useSalesOpportunityMeta: vi.fn(), useSalesOpportunityAgentOptions: vi.fn() }));
vi.mock('../hooks/useSalesOpportunities', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSalesOpportunities')>();
  return { ...actual, ...hooks };
});

import SalesOpportunitiesView from './SalesOpportunitiesView';

const COLUMNS = ['Number', 'Title', 'Customer', 'Agent', 'Stage', 'Amount', 'Close date', 'Source'];

beforeEach(() => {
  cleanup();
  hooks.useSalesOpportunities.mockReturnValue({
    data: {
      data: [{ id: 'o-1', opportunity_no: 'OPP-000001', title: 'ZZT Deal', customer_name: 'ZZT Dealer', sales_agent_label: 'ZZA', stage_label: 'New', stage_key: 'new', outcome: 'open', expected_amount: '10', expected_close_date: '2026-11-01', source: 'portal' }],
      pagination: { total: 1, page: 1, limit: 25 }, empty: false,
    },
    isLoading: false, isFetching: false, isPlaceholderData: false, refetch: vi.fn(), error: null,
  });
  hooks.useSalesOpportunityMeta.mockReturnValue({ data: { stages: [], lost_reasons: [] } });
  hooks.useSalesOpportunityAgentOptions.mockReturnValue({ data: [] });
});

describe('every Sales Opportunity column header sorts', () => {
  it.each([
    ['limited', ['sales.opportunities.view_own', 'sales.opportunities.add']],
    ['staff', ['sales.opportunities.view', 'sales.opportunities.add']],
  ])('%s: each header is a sort button', async (_n, slugs) => {
    held = new Set(slugs);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SalesOpportunitiesView />
      </QueryClientProvider>,
    );
    await screen.findByText('OPP-000001');
    const missing: string[] = [];
    for (const title of COLUMNS) {
      const th = screen.queryAllByText(title).map((el) => el.closest('th')).find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(title);
    }
    expect(missing).toEqual([]);
  });
});
