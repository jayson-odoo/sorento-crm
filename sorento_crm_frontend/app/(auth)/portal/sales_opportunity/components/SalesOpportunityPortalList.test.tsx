/**
 * The portal Sales Opportunities list (UAC S2-10; plan 3.5, section 16).
 *
 * Mobile-first card list: number, title, customer or prospect, stage `Badge`, amount, expected
 * close date; a New link to the create form; each card links to its own detail. Same mocking
 * style as `SalesOpportunityPortalForm.test.tsx` (service mocked, no network).
 *
 * `./SalesOpportunityPortalList` does not exist yet on this branch, so this whole file is
 * expected to fail to resolve the import.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const service = vi.hoisted(() => ({
  listPortalSalesOpportunities: vi.fn(),
}));
vi.mock('../../lib/sales-opportunity-service', () => service);

import SalesOpportunityPortalList from './SalesOpportunityPortalList';

const ROWS = [
  {
    id: 'opp-1',
    opportunity_no: 'OPP-000001',
    title: 'New basin order',
    customer_name: 'Kedai Mine',
    prospect_name: null,
    stage_label: 'Qualified',
    expected_amount: '5000.00',
    expected_close_date: '2026-11-15',
  },
  {
    id: 'opp-2',
    opportunity_no: 'OPP-000002',
    title: 'Renovation project',
    customer_name: null,
    prospect_name: 'Seri Indah Renovation',
    stage_label: 'New',
    expected_amount: '1200.00',
    expected_close_date: '2026-12-01',
  },
];

beforeEach(() => {
  service.listPortalSalesOpportunities.mockReset();
});

describe('SalesOpportunityPortalList', () => {
  it('renders a New link to the create form', async () => {
    service.listPortalSalesOpportunities.mockResolvedValue(ROWS);
    render(<SalesOpportunityPortalList />);
    await waitFor(() => expect(service.listPortalSalesOpportunities).toHaveBeenCalled());
    const newLink = screen.getByRole('link', { name: /new/i });
    expect(newLink.getAttribute('href')).toContain('/portal/sales_opportunity/new');
  });

  it('shows number, title, customer name, stage, amount and close date, linking to the detail', async () => {
    service.listPortalSalesOpportunities.mockResolvedValue(ROWS);
    render(<SalesOpportunityPortalList />);

    const card = await screen.findByText('OPP-000001');
    expect(screen.getByText('New basin order')).toBeTruthy();
    expect(screen.getByText('Kedai Mine')).toBeTruthy();
    expect(screen.getByText('Qualified')).toBeTruthy();
    expect(screen.getByText(/5000/)).toBeTruthy();
    expect(screen.getByText(/2026-11-15/)).toBeTruthy();

    const link = card.closest('a');
    expect(link?.getAttribute('href')).toContain('/portal/sales_opportunity/opp-1');
  });

  it('shows the prospect name when there is no customer', async () => {
    service.listPortalSalesOpportunities.mockResolvedValue(ROWS);
    render(<SalesOpportunityPortalList />);
    await screen.findByText('OPP-000002');
    expect(screen.getByText('Seri Indah Renovation')).toBeTruthy();
  });

  it('shows an empty state when there are no opportunities', async () => {
    service.listPortalSalesOpportunities.mockResolvedValue([]);
    render(<SalesOpportunityPortalList />);
    await screen.findByText(/no opportunities yet/i);
  });

  it('shows an error state when the load fails', async () => {
    service.listPortalSalesOpportunities.mockRejectedValue(new Error('network down'));
    render(<SalesOpportunityPortalList />);
    await screen.findByText(/failed to load/i);
  });
});
