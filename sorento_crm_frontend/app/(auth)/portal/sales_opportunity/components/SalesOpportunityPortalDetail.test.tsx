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

// Same fuller mock `SalesOpportunityPortalForm.test.tsx` uses (Phase 3 fix2 should-fix 5): a
// typed keystroke fires `onChange` with no item, a click on a listed option fires it WITH one -
// the in-place "Customer or prospect" edit needs both to exercise a real switch.
vi.mock('../../components/AsyncCombobox', () => ({
  AsyncCombobox: (props: {
    id?: string;
    value: string;
    onChange: (v: string, item?: unknown) => void;
    fetchOptions: (q: string) => Promise<unknown[]>;
    optionValue: (o: any) => string;
    optionLabel: (o: any) => string;
    placeholder?: string;
  }) => {
    const [query, setQuery] = React.useState(props.value);
    const [options, setOptions] = React.useState<any[]>([]);
    React.useEffect(() => {
      props.fetchOptions(query).then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);
    return (
      <div>
        <input
          aria-label={props.placeholder ?? props.id ?? 'search'}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            props.onChange(e.target.value);
          }}
        />
        <ul>
          {options.map((o, i) => (
            <li key={i}>
              <button
                type="button"
                disabled={o.disabled}
                onClick={() => props.onChange(props.optionValue(o), o)}
              >
                {props.optionLabel(o)}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  },
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
  getPortalCustomerOptions: vi.fn(),
  getPortalProductOptions: vi.fn(),
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
  service.getPortalCustomerOptions.mockResolvedValue({ items: [], prospect: null, blocked: null });
  service.getPortalProductOptions.mockResolvedValue([{ id: 'p1', code: 'ZZT-001', name: 'ZZT Basin' }]);
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

  it('fix reviewer-8: clicking Won reveals a confirm step, same as Lost', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Won' }));
    expect(service.updatePortalSalesOpportunity).not.toHaveBeenCalled();
    const confirm = screen.getByRole('button', { name: /confirm|save/i });
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(service.updatePortalSalesOpportunity).toHaveBeenCalledWith('opp-1', {
        status_id: 'st-won',
      }),
    );
  });

  it('fix reviewer-8: Cancel on a pending Won leaves the opportunity untouched', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Won' }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(service.updatePortalSalesOpportunity).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /confirm|save/i })).toBeNull();
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

  it('fix browser-defect-1: shows the lost reason once the opportunity is Lost', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({
        outcome: 'lost',
        stage_key: 'lost',
        stage_label: 'Lost',
        lost_reason: 'price',
        lost_reason_label: 'Price',
        available_transitions: [],
      }),
    );
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    expect(screen.getByText('Price')).toBeTruthy();
  });

  it('fix nit: shows an error state with Retry when the load fails', async () => {
    service.getPortalSalesOpportunity.mockRejectedValueOnce(new Error('network down'));
    service.getPortalSalesOpportunity.mockResolvedValueOnce(detail());
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText(/failed to load/i);
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await screen.findByText('OPP-000001');
  });

  it('fix B3: Edit reveals the same form pre-filled with the opportunity', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('ZZT Deal');
    expect((screen.getByLabelText('Expected amount') as HTMLInputElement).value).toBe('1000.00');
  });

  it('fix B3: saving an edit PATCHes the opportunity and returns to the view', async () => {
    service.updatePortalSalesOpportunity.mockResolvedValue(detail({ title: 'ZZT Deal Renamed' }));
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Deal Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(service.updatePortalSalesOpportunity).toHaveBeenCalledTimes(1));
    expect(service.updatePortalSalesOpportunity.mock.calls[0][0]).toBe('opp-1');
    expect(service.updatePortalSalesOpportunity.mock.calls[0][1].title).toBe('ZZT Deal Renamed');
    await waitFor(() => expect(screen.queryByLabelText('Title')).toBeNull());
  });

  it('fix B3: Cancel returns to the view without saving', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByLabelText('Title')).toBeNull();
    expect(service.updatePortalSalesOpportunity).not.toHaveBeenCalled();
    expect(screen.getByText('ZZT Deal')).toBeTruthy();
  });

  it('fix B3: no Edit once the opportunity is closed (N7)', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({ outcome: 'won', stage_key: 'won', available_transitions: [] }),
    );
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    expect(screen.queryByRole('button', { name: /^edit$/i })).toBeNull();
  });

  it('fix2 should-fix 5: Edit keeps the SAME view - the Products card stays, its rows become editable in place', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    // Read view: Products section lists the line as plain text.
    expect(screen.getByText('Products')).toBeTruthy();
    expect(screen.getByText('ZZT-001')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

    // Still one page, not a second component swapped in: Products is still there,
    // now with an Add product control - the CRM detail's own in-place edit shape.
    expect(screen.getByText('Products')).toBeTruthy();
    expect(screen.getByRole('button', { name: /add product/i })).toBeTruthy();
  });

  it('fix2 should-fix 5: the opportunity number and stage badge stay visible while editing (read-only meta)', async () => {
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    expect(screen.getByText('OPP-000001')).toBeTruthy();
    expect(screen.getByText('New')).toBeTruthy();
  });

  it('fix2 should-fix 3: the stage pill colours from stage_key', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({ outcome: 'lost', stage_key: 'lost', stage_label: 'Lost', available_transitions: [] }),
    );
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    const badge = await screen.findByText('Lost');
    expect(badge.className).toMatch(/--color-destructive-soft/);
  });

  it('fix2 B-new: switching a prospect-backed opportunity to a customer sends customer_id and an explicit prospect_name: null', async () => {
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [{ customer_id: 'cust-2', customer_code: 'C2', customer_name: 'ZZT New Customer' }],
      prospect: null,
      blocked: null,
    });
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText(/customer or prospect/i), {
      target: { value: 'ZZT New' },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'C2 - ZZT New Customer' }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(service.updatePortalSalesOpportunity).toHaveBeenCalledTimes(1));
    const payload = service.updatePortalSalesOpportunity.mock.calls[0][1];
    expect(payload.customer_id).toBe('cust-2');
    expect(payload.prospect_name).toBeNull();
  });

  it('fix2 B-new: switching a customer-backed opportunity to a prospect sends prospect_name and an explicit customer_id: null', async () => {
    service.getPortalSalesOpportunity.mockResolvedValue(
      detail({ customer_id: 'cust-1', customer_name: 'ZZT Dealer', prospect_name: null }),
    );
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [],
      prospect: { name: 'ZZT New Prospect' },
      blocked: null,
    });
    render(<SalesOpportunityPortalDetail id="opp-1" />);
    await screen.findByText('OPP-000001');
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    fireEvent.change(screen.getByLabelText(/customer or prospect/i), {
      target: { value: 'ZZT New Prospect' },
    });
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add "ZZT New Prospect" as a new prospect' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(service.updatePortalSalesOpportunity).toHaveBeenCalledTimes(1));
    const payload = service.updatePortalSalesOpportunity.mock.calls[0][1];
    expect(payload.prospect_name).toBe('ZZT New Prospect');
    expect(payload.customer_id).toBeNull();
  });
});
