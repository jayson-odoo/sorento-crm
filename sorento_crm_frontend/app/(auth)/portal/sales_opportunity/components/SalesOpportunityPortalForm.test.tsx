/**
 * The portal Sales Opportunity form (UAC S2-10, S2-15, S2-16; plan 3.5, N10, N11).
 *
 * Same "Customer or prospect" search and Products table contract as the CRM modal, against the
 * portal service. No agent field anywhere - the agent comes from the token, never the form.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

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
    const [query, setQuery] = React.useState('');
    const [options, setOptions] = React.useState<any[]>([]);
    React.useEffect(() => {
      props.fetchOptions(query).then(setOptions);
    }, [query]);
    return (
      <div>
        <input
          aria-label={props.placeholder ?? props.id ?? 'search'}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
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

const service = vi.hoisted(() => ({
  getPortalCustomerOptions: vi.fn(),
  getPortalProductOptions: vi.fn(),
  createPortalSalesOpportunity: vi.fn(),
}));
vi.mock('../../lib/sales-opportunity-service', () => service);

import SalesOpportunityPortalForm from './SalesOpportunityPortalForm';

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.getPortalCustomerOptions.mockResolvedValue({ items: [], prospect: null, blocked: null });
  service.getPortalProductOptions.mockResolvedValue([{ id: 'p1', code: 'ZZT-001', name: 'ZZT Basin' }]);
  service.createPortalSalesOpportunity.mockResolvedValue({ id: 'opp-1' });
});

describe('SalesOpportunityPortalForm', () => {
  it('has no agent field anywhere', () => {
    render(<SalesOpportunityPortalForm />);
    expect(screen.queryByLabelText(/agent/i)).toBeNull();
    expect(screen.queryByText(/sales agent/i)).toBeNull();
  });

  it('offers "Add ... as a new prospect" when nothing matches and creates with prospect_name', async () => {
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [],
      prospect: { name: 'Seri Indah Renovation' },
      blocked: null,
    });
    render(<SalesOpportunityPortalForm />);

    fireEvent.change(screen.getByLabelText(/customer or prospect/i), {
      target: { value: 'Seri Indah Renovation' },
    });
    const prospectOption = await screen.findByText('Add "Seri Indah Renovation" as a new prospect');
    fireEvent.click(prospectOption);

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Opp' } });
    fireEvent.change(screen.getByLabelText('Expected amount'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), {
      target: { value: '2026-11-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save|submit/i }));

    await waitFor(() => expect(service.createPortalSalesOpportunity).toHaveBeenCalledTimes(1));
    const payload = service.createPortalSalesOpportunity.mock.calls[0][0];
    expect(payload.prospect_name).toBe('Seri Indah Renovation');
    expect(payload.customer_id).toBeFalsy();
  });

  it('shows a disabled option for a blocked exact match', async () => {
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [],
      prospect: null,
      blocked: { name: 'Seri Indah', message: "Seri Indah is another agent's customer" },
    });
    render(<SalesOpportunityPortalForm />);
    fireEvent.change(screen.getByLabelText(/customer or prospect/i), {
      target: { value: 'Seri Indah' },
    });
    const blockedButton = await screen.findByText("Seri Indah is another agent's customer");
    expect((blockedButton as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows "No products yet" until a row is added, and Add product adds one', () => {
    render(<SalesOpportunityPortalForm />);
    expect(screen.getByText(/no products yet/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    expect(screen.queryByText(/no products yet/i)).toBeNull();
  });

  it('removes a product row', () => {
    render(<SalesOpportunityPortalForm />);
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    expect(screen.getAllByRole('button', { name: /remove/i }).length).toBe(2);
    fireEvent.click(screen.getAllByRole('button', { name: /remove/i })[0]);
    expect(screen.getAllByRole('button', { name: /remove/i }).length).toBe(1);
  });
});
