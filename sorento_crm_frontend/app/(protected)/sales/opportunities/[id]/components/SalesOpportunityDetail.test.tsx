/**
 * `/sales/opportunities/{id}` detail page (UAC S2-11, S2-12, S2-13; plan section 16).
 *
 * Stage buttons come from `available_transitions` only; Lost reveals a required reason select
 * and blocks save without it; Won reveals an optional sales order select; every section
 * (Opportunity, Products, Stage) renders with an empty state; a RecordNavigation is present.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/components/common/RecordNavigation', () => ({
  RecordNavigation: () => <nav aria-label="record navigation" />,
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props['aria-label'] ?? props.id ?? 'select'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="" />
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const hooks = vi.hoisted(() => ({
  useSalesOpportunity: vi.fn(),
  useSaveSalesOpportunity: vi.fn(),
}));
vi.mock('../../hooks/useSalesOpportunities', () => hooks);

import SalesOpportunityDetail from './SalesOpportunityDetail';

const save = { mutateAsync: vi.fn(), isPending: false };

function detail(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'opp-1',
    opportunity_no: 'OPP-000001',
    title: 'ZZT Deal',
    customer_id: 'cust-1',
    customer_name: 'ZZT Dealer',
    prospect_name: null,
    sales_agent_id: null,
    sales_agent_label: null,
    status_id: 'st-new',
    stage_key: 'new',
    stage_label: 'New',
    win_probability: 10,
    outcome: 'open',
    expected_amount: '1000.00',
    expected_close_date: '2026-11-01',
    lost_reason: null,
    lost_reason_label: null,
    sales_order_id: null,
    sales_order_no: null,
    source: 'crm',
    created_by_label: 'Jane Doe',
    created_at: '2026-09-26T00:00:00',
    updated_at: '2026-09-26T00:00:00',
    stage_changed_at: '2026-09-26T00:00:00',
    lines: [],
    available_transitions: [
      { to_status_id: 'st-qualified', key: 'qualified', label: 'Qualified' },
      { to_status_id: 'st-won', key: 'won', label: 'Won' },
      { to_status_id: 'st-lost', key: 'lost', label: 'Lost' },
    ],
    ...over,
  };
}

beforeEach(() => {
  save.mutateAsync.mockReset();
  save.mutateAsync.mockResolvedValue({});
  hooks.useSaveSalesOpportunity.mockReturnValue(save);
  hooks.useSalesOpportunity.mockReturnValue({
    data: detail(),
    isLoading: false,
    isError: false,
  });
});

describe('SalesOpportunityDetail', () => {
  it('renders a RecordNavigation', () => {
    render(<SalesOpportunityDetail id="opp-1" />);
    expect(screen.getByLabelText('record navigation')).toBeTruthy();
  });

  it('offers only the stages named in available_transitions', () => {
    render(<SalesOpportunityDetail id="opp-1" />);
    expect(screen.getByRole('button', { name: 'Qualified' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Won' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Lost' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Proposal' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Negotiation' })).toBeNull();
  });

  it('choosing Lost reveals a required reason select and blocks save without it', async () => {
    render(<SalesOpportunityDetail id="opp-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Lost' }));
    const reasonSelect = await screen.findByLabelText(/lost reason/i);
    expect(reasonSelect).toBeTruthy();

    const confirm = screen.getByRole('button', { name: /confirm|save/i });
    fireEvent.click(confirm);
    expect(save.mutateAsync).not.toHaveBeenCalled();

    fireEvent.change(reasonSelect, { target: { value: 'price' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalled());
  });

  it('choosing Won reveals an optional sales order select', async () => {
    render(<SalesOpportunityDetail id="opp-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Won' }));
    expect(await screen.findByLabelText(/sales order/i)).toBeTruthy();
  });

  it('renders every section with an empty state when there is nothing to show', () => {
    hooks.useSalesOpportunity.mockReturnValue({
      data: detail({ lines: [] }),
      isLoading: false,
      isError: false,
    });
    render(<SalesOpportunityDetail id="opp-1" />);
    expect(screen.getByText('Opportunity')).toBeTruthy();
    expect(screen.getByText('Products')).toBeTruthy();
    expect(screen.getByText('Stage')).toBeTruthy();
    expect(screen.getByText(/no products yet/i)).toBeTruthy();
  });

  it('shows a loading state', () => {
    hooks.useSalesOpportunity.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<SalesOpportunityDetail id="opp-1" />);
    expect(screen.queryByText('Opportunity')).toBeNull();
  });
});
