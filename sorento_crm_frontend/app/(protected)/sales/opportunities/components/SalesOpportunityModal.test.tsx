/**
 * The Log opportunity modal (UAC S2-12, S2-15, S2-16; plan 3.4, 3.5, section 16, N10, N11).
 *
 * ONE "Customer or prospect" search - no "Not a customer yet" switch (N10, S2-15) - and an
 * optional Products table (N11, S2-16), the complaint form's product-line pattern: a product
 * search and a quantity per row, Add product, remove, "No products yet" when empty.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string; disabled?: boolean } | null) => void;
    options?: { value: string; label: string; disabled?: boolean }[];
    fetchOptions?: (q: string, page: number) => Promise<
      { value: string; label: string; disabled?: boolean }[]
    >;
  }) => {
    const [query, setQuery] = React.useState('');
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) {
        props.fetchOptions(query, 0).then(setOptions);
      }
    }, [query]);
    const label = props['aria-label'] ?? props.id ?? 'select';
    return (
      <div>
        {props.fetchOptions && (
          <input aria-label={`${label} search`} value={query} onChange={(e) => setQuery(e.target.value)} />
        )}
        <select
          aria-label={label}
          value={props.value}
          onChange={(e) => {
            props.onChange(e.target.value);
            const opt = options.find((o) => o.value === e.target.value) ?? null;
            props.onOptionChange?.(opt);
          }}
        >
          <option value="" />
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    );
  },
}));

const service = vi.hoisted(() => ({
  getSalesOpportunityCustomerOptions: vi.fn(),
  getSalesOpportunityProductOptions: vi.fn(),
}));
vi.mock('../services/salesOpportunityService', () => service);

const save = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
vi.mock('../hooks/useSalesOpportunities', () => ({
  useSaveSalesOpportunity: () => save,
}));

import SalesOpportunityModal from './SalesOpportunityModal';

beforeEach(() => {
  save.mutateAsync.mockReset();
  save.mutateAsync.mockResolvedValue({ id: 'new' });
  service.getSalesOpportunityCustomerOptions.mockReset();
  service.getSalesOpportunityCustomerOptions.mockResolvedValue({
    items: [],
    prospect: null,
    blocked: null,
  });
  service.getSalesOpportunityProductOptions.mockReset();
  service.getSalesOpportunityProductOptions.mockResolvedValue([
    { value: 'p1', label: 'ZZT-001 - ZZT Basin' },
  ]);
});

describe('SalesOpportunityModal', () => {
  it('has one Customer or prospect field and no toggle/switch element', () => {
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);
    expect(screen.getByLabelText('Customer or prospect')).toBeTruthy();
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByText(/not a customer yet/i)).toBeNull();
  });

  it('offers "Add ... as a new prospect" when no customer matches, and sends prospect_name', async () => {
    service.getSalesOpportunityCustomerOptions.mockResolvedValue({
      items: [],
      prospect: { name: 'Seri Indah Renovation' },
      blocked: null,
    });
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Customer or prospect search'), {
      target: { value: 'Seri Indah Renovation' },
    });
    await waitFor(() =>
      expect(screen.getByText('Add "Seri Indah Renovation" as a new prospect')).toBeTruthy(),
    );

    fireEvent.change(screen.getByLabelText('Customer or prospect'), {
      target: { value: 'prospect:Seri Indah Renovation' },
    });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Opp' } });
    fireEvent.change(screen.getByLabelText('Expected amount'), { target: { value: '1000' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), {
      target: { value: '2026-11-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    const payload = save.mutateAsync.mock.calls[0][0];
    expect(payload.prospect_name).toBe('Seri Indah Renovation');
    expect(payload.customer_id).toBeFalsy();
  });

  it('renders a blocked match as a disabled option', async () => {
    service.getSalesOpportunityCustomerOptions.mockResolvedValue({
      items: [],
      prospect: null,
      blocked: { name: 'Seri Indah', message: "Seri Indah is another agent's customer" },
    });
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('Customer or prospect search'), {
      target: { value: 'Seri Indah' },
    });
    await waitFor(() => {
      const option = screen.getByText("Seri Indah is another agent's customer");
      expect((option as HTMLOptionElement).disabled).toBe(true);
    });
  });

  it('shows "No products yet" until a row is added, and Add product adds one', () => {
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);
    expect(screen.getByText(/no products yet/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    expect(screen.queryByText(/no products yet/i)).toBeNull();
  });

  it('removes a product row', () => {
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    const removeButtons = screen.getAllByRole('button', { name: /remove/i });
    expect(removeButtons.length).toBe(2);
    fireEvent.click(removeButtons[0]);
    expect(screen.getAllByRole('button', { name: /remove/i }).length).toBe(1);
  });

  it('sends the product lines in the order they were entered', async () => {
    render(<SalesOpportunityModal open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('Customer or prospect'), { target: { value: 'cust-1' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Opp' } });
    fireEvent.change(screen.getByLabelText('Expected amount'), { target: { value: '1000' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), {
      target: { value: '2026-11-01' },
    });

    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    const rows = screen.getAllByTestId('opportunity-line-row');
    const firstProductSelect = within(rows[0]).getByLabelText(/product/i);
    fireEvent.change(firstProductSelect, { target: { value: 'p1' } });
    const firstQty = within(rows[0]).getByLabelText(/qty/i);
    fireEvent.change(firstQty, { target: { value: '3' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync.mock.calls[0][0].lines).toEqual([{ product_id: 'p1', qty: 3 }]);
  });
});
