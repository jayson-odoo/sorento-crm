/**
 * Portal detail (UAC S2-11; plan section 16, "detail has the same form plus stage buttons from
 * `available_transitions`, Lost revealing a required reason select"). No agent, no sales order
 * field anywhere in the portal - only the CRM sends `sales_order_id` (plan section 16, "Won").
 *
 * Same mocking style as `SalesOpportunityPortalForm.test.tsx`: the service module and
 * `AsyncCombobox` are mocked, `@/components/common/SearchableSelect` is mocked the same way the
 * CRM `SalesOpportunityDetail.test.tsx` does, since the ADR requires every dropdown (the lost
 * reason picker) to be one.
 *
 * `./SalesOpportunityPortalDetail` does not exist yet on this branch, so this whole file is
 * expected to fail to resolve the import.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('../../components/AsyncCombobox', () => ({
  AsyncCombobox: (props: {
    id?: string;
    value: string;
    onChange: (v: string, item?: unknown) => void;
    fetchOptions: (q: string) => Promise<unknown[]>;
    optionValue: (o: any) => string;
    optionLabel: (o: any) => string;
    placeholder?: string;
  }) => (
    <input
      aria-label={props.placeholder ?? props.id ?? 'search'}
      value={props.value}
      readOnly
    />
  ),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={props['aria-label'] ?? props.placeholder ?? props.id ?? 'select'}
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

const service = vi.hoisted(() => ({
  getPortalSalesOpportunity: vi.fn(),
  updatePortalSalesOpportunity: vi.fn(),
  getPortalOpportunityMeta: vi.fn(),
}));
vi.mock('../../lib/sales-opportunity-service', () => service);

import SalesOpportunityPortalDetail from './SalesOpportunityPortalDetail';

function detail(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'opp-1',
    opportunity_no: 'OPP-000001',
    title: 'ZZT Deal',
    customer_id: null,
    customer_name: null,
    prospect_name: 'ZZT Prospect',
    status_id: 'st-new',
    stage_key: 'new',
    stage_label: 'New',
    outcome: 'open',
    expected_amount: '1000.00',
    expected_close_date: '2026-11-01',
    lost_reason: null,
    lost_reason_label: null,
    sales_order_id: null,
    sales_order_no: null,
    source: 'portal',
    lines: [{ id: 'l1', product_id: 'p1', product_code: 'ZZT-001', product_name: 'ZZT Basin', qty: 2 }],
    available_transitions: [
      { to_status_id: 'st-qualified', key: 'qualified', label: 'Qualified' },
      { to_status_id: 'st-won', key: 'won', label: 'Won' },
      { to_status_id: 'st-lost', key: 'lost', label: 'Lost' },
    ],
    ...over,
  };
}

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.getPortalSalesOpportunity.mockResolvedValue(detail());
  service.updatePortalSalesOpportunity.mockResolvedValue(detail());
  service.getPortalOpportunityMeta.mockResolvedValue({
    stages: [],
    lost_reasons: [
      { value: 'price', label: 'Price' },
      { value: 'competitor', label: 'Competitor' },
    ],
  });
});

describe('SalesOpportunityPortalDetail', () => {
  it('offers only the stages named in available_transitions', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    expect(await screen.findByRole('button', { name: 'Qualified' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Won' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Lost' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Proposal' })).toBeNull();
  });

  it('clicking Lost reveals a required reason picker sourced from meta lost_reasons', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Lost' }));
    const reasonSelect = await screen.findByLabelText(/lost reason/i);
    expect(screen.getByRole('option', { name: 'Price' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Competitor' })).toBeTruthy();
    expect(reasonSelect).toBeTruthy();
  });

  it('confirming Lost without a reason does not call updatePortalSalesOpportunity', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Lost' }));
    await screen.findByLabelText(/lost reason/i);
    fireEvent.click(screen.getByRole('button', { name: /confirm|save/i }));
    expect(service.updatePortalSalesOpportunity).not.toHaveBeenCalled();
  });

  it('confirming Lost with a reason PATCHes status_id and lost_reason', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Lost' }));
    const reasonSelect = await screen.findByLabelText(/lost reason/i);
    fireEvent.change(reasonSelect, { target: { value: 'price' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm|save/i }));
    await waitFor(() =>
      expect(service.updatePortalSalesOpportunity).toHaveBeenCalledWith('opp-1', {
        status_id: 'st-lost',
        lost_reason: 'price',
      }),
    );
  });

  it('clicking Qualified PATCHes status_id only', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Qualified' }));
    await waitFor(() =>
      expect(service.updatePortalSalesOpportunity).toHaveBeenCalledWith('opp-1', {
        status_id: 'st-qualified',
      }),
    );
  });

  it('has no sales order field anywhere in the portal', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    expect(screen.queryByLabelText(/sales order/i)).toBeNull();
  });

  it('shows no stage buttons when the opportunity is terminal (won)', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({ outcome: 'won', stage_key: 'won', stage_label: 'Won', available_transitions: [] }),
    );
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    expect(screen.queryByRole('button', { name: 'Qualified' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Won' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Lost' })).toBeNull();
  });

  it('shows no stage buttons when the opportunity is terminal (lost)', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({ outcome: 'lost', stage_key: 'lost', stage_label: 'Lost', available_transitions: [] }),
    );
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    expect(screen.queryByRole('button', { name: 'Qualified' })).toBeNull();
  });

  it('lists the lines as product code, name and quantity', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('ZZT-001');
    expect(screen.getByText('ZZT Basin')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });
});
