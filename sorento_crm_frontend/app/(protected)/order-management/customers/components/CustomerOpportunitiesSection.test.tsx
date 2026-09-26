/**
 * The customer page's Opportunities section (UAC S2-12; plan section 16, J8).
 *
 * "No opportunities yet" with a "Log opportunity" button when there are none, preset to this
 * customer; the section renders in both view and edit (same layout, CLAUDE.md CRUD standard).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const hooks = vi.hoisted(() => ({ useCustomerOpportunities: vi.fn() }));
vi.mock('@/app/(protected)/sales/opportunities/hooks/useSalesOpportunities', () => hooks);

vi.mock('@/app/(protected)/sales/opportunities/components/SalesOpportunityModal', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">opportunity modal</div> : null,
}));

import CustomerOpportunitiesSection from './CustomerOpportunitiesSection';

beforeEach(() => {
  hooks.useCustomerOpportunities.mockReset();
});

describe('CustomerOpportunitiesSection', () => {
  it('shows "No opportunities yet" with Log opportunity when there are none', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /log opportunity/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('lists the customer opportunities when present', () => {
    hooks.useCustomerOpportunities.mockReturnValue({
      data: [
        {
          id: 'opp-1',
          opportunity_no: 'OPP-000001',
          title: 'ZZT Deal',
          stage_label: 'New',
          expected_amount: '1000.00',
          expected_close_date: '2026-11-01',
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(<CustomerOpportunitiesSection customerId="cust-1" />);
    expect(screen.getByText('ZZT Deal')).toBeTruthy();
    expect(screen.queryByText('No opportunities yet')).toBeNull();
  });

  it('renders the same in view and edit mode', () => {
    hooks.useCustomerOpportunities.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { rerender } = render(<CustomerOpportunitiesSection customerId="cust-1" isEditing={false} />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
    rerender(<CustomerOpportunitiesSection customerId="cust-1" isEditing={true} />);
    expect(screen.getByText('No opportunities yet')).toBeTruthy();
  });
});
