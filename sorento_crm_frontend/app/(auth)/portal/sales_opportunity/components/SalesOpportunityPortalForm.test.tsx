/**
 * The portal Sales Opportunity form (UAC S2-10, S2-15, S2-16; plan 3.5, N10, N11; F4/F7).
 *
 * Same "Customer or prospect" search and Products table contract as the CRM modal, against the
 * portal service, now over the system `SearchableSelect` (F4) rather than the portal's own
 * `AsyncCombobox` - the mock below mirrors the one the CRM's own
 * `SalesOpportunityModal.test.tsx` uses, so both surfaces are exercised the same way.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: { value: string; label: string; disabled?: boolean } | null) => void;
    options?: { value: string; label: string; disabled?: boolean }[];
    fetchOptions?: (
      q: string,
      page: number,
    ) => Promise<{ value: string; label: string; disabled?: boolean }[]>;
    selectedOption?: { value: string; label: string; disabled?: boolean };
    placeholder?: string;
    emptyMessage?: string;
  }) => {
    const [query, setQuery] = React.useState('');
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) props.fetchOptions(query, 0).then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query]);
    const label = props['aria-label'] ?? props.placeholder ?? props.id ?? 'select';
    // Mirrors the real component's own fallback (S4): a `selectedOption` whose value
    // isn't in the fetched page still shows as the current selection.
    const merged =
      props.selectedOption && !options.some((o) => o.value === props.selectedOption!.value)
        ? [props.selectedOption, ...options]
        : options;
    return (
      <div>
        {props.fetchOptions ? (
          <input aria-label={`${label} search`} value={query} onChange={(e) => setQuery(e.target.value)} />
        ) : null}
        {merged.length === 0 ? <p data-testid={`${label}-empty`}>{props.emptyMessage}</p> : null}
        <select
          aria-label={label}
          value={props.value}
          onChange={(e) => {
            props.onChange(e.target.value);
            const opt = merged.find((o) => o.value === e.target.value) ?? null;
            props.onOptionChange?.(opt);
          }}
        >
          <option value="" />
          {merged.map((o) => (
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
  getPortalCustomerOptions: vi.fn(),
  getPortalProductOptions: vi.fn(),
  createPortalSalesOpportunity: vi.fn(),
}));
vi.mock('../../lib/sales-opportunity-service', () => service);

import SalesOpportunityPortalForm from './SalesOpportunityPortalForm';

beforeEach(() => {
  Object.values(service).forEach((fn) => fn.mockReset());
  service.getPortalCustomerOptions.mockResolvedValue({ items: [], prospect: null, blocked: null });
  service.getPortalProductOptions.mockResolvedValue([
    { id: 'p1', code: 'ZZT-001', name: 'ZZT Basin', listPrice: '100.00' },
  ]);
  service.createPortalSalesOpportunity.mockResolvedValue({ id: 'opp-1' });
});

describe('SalesOpportunityPortalForm', () => {
  it('has no agent field anywhere', () => {
    render(<SalesOpportunityPortalForm />);
    expect(screen.queryByLabelText(/agent/i)).toBeNull();
    expect(screen.queryByText(/sales agent/i)).toBeNull();
  });

  it('F3: says the agent has no customers when the query is empty', async () => {
    render(<SalesOpportunityPortalForm />);
    expect(
      await screen.findByText('You have no customers linked yet; type a name to add a prospect'),
    ).toBeTruthy();
  });

  it('offers "Add ... as a new prospect" when nothing matches and creates with prospect_name', async () => {
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [],
      prospect: { name: 'Seri Indah Renovation' },
      blocked: null,
    });
    render(<SalesOpportunityPortalForm />);

    fireEvent.change(screen.getByLabelText('Customer or prospect search'), {
      target: { value: 'Seri Indah Renovation' },
    });
    const select = await screen.findByLabelText('Customer or prospect');
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Add "Seri Indah Renovation" as a new prospect' })).toBeTruthy(),
    );
    fireEvent.change(select, {
      target: { value: 'prospect:Seri Indah Renovation' },
    });

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Opp' } });
    fireEvent.change(screen.getByLabelText('Expected amount'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), {
      target: { value: '2026-11-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save|submit/i }));

    await waitFor(() => expect(service.createPortalSalesOpportunity).toHaveBeenCalledTimes(1));
    const payload = service.createPortalSalesOpportunity.mock.calls[0][0];
    expect(payload.prospect_name).toBe('Seri Indah Renovation');
    expect(payload.customer_id).toBeUndefined();
  });

  it('S4: keeps the picked prospect option visible after the search list changes (e.g. reopening)', async () => {
    service.getPortalCustomerOptions.mockImplementation(async (q: string) => {
      if (q === 'Seri Indah Renovation') {
        return { items: [], prospect: { name: 'Seri Indah Renovation' }, blocked: null };
      }
      return { items: [], prospect: null, blocked: null };
    });
    render(<SalesOpportunityPortalForm />);

    fireEvent.change(screen.getByLabelText('Customer or prospect search'), {
      target: { value: 'Seri Indah Renovation' },
    });
    const select = await screen.findByLabelText('Customer or prospect');
    const prospectOption = await screen.findByRole('option', {
      name: 'Add "Seri Indah Renovation" as a new prospect',
    });
    fireEvent.change(select, { target: { value: 'prospect:Seri Indah Renovation' } });

    // Simulate reopening the field: a fresh search whose own result set no longer
    // includes the option already picked.
    fireEvent.change(screen.getByLabelText('Customer or prospect search'), { target: { value: '' } });
    await waitFor(() => expect(service.getPortalCustomerOptions).toHaveBeenCalledWith(''));

    expect(
      screen.getByRole('option', { name: 'Add "Seri Indah Renovation" as a new prospect' }),
    ).toBeTruthy();
    expect(prospectOption).toBeTruthy();
  });

  it('shows a disabled option for a blocked exact match', async () => {
    service.getPortalCustomerOptions.mockResolvedValue({
      items: [],
      prospect: null,
      blocked: { name: 'Seri Indah', message: "Seri Indah is another agent's customer" },
    });
    render(<SalesOpportunityPortalForm />);
    fireEvent.change(screen.getByLabelText('Customer or prospect search'), {
      target: { value: 'Seri Indah' },
    });
    const blockedOption = await screen.findByRole('option', {
      name: "Seri Indah is another agent's customer",
    });
    expect((blockedOption as HTMLOptionElement).disabled).toBe(true);
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

  it('F7: picking a product prefills unit price, shows the line amount, and tracks the expected amount total', async () => {
    render(<SalesOpportunityPortalForm />);
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));

    const productSelect = await screen.findByLabelText('Search products...');
    await waitFor(() => expect(screen.getByRole('option', { name: 'ZZT-001 - ZZT Basin' })).toBeTruthy());
    fireEvent.change(productSelect, { target: { value: 'p1' } });

    expect((screen.getByLabelText('Unit price') as HTMLInputElement).value).toBe('100.00');
    expect(screen.getByText('RM 100.00')).toBeTruthy();
    await waitFor(() =>
      expect((screen.getByLabelText('Expected amount') as HTMLInputElement).value).toBe('100.00'),
    );

    // Typing an amount by hand stops the auto total from overriding it.
    fireEvent.change(screen.getByLabelText('Expected amount'), { target: { value: '999' } });
    fireEvent.change(screen.getByLabelText('Qty'), { target: { value: '2' } });
    expect((screen.getByLabelText('Expected amount') as HTMLInputElement).value).toBe('999');
  });

  it('F7: sends unit_price on every line', async () => {
    render(<SalesOpportunityPortalForm />);
    fireEvent.click(screen.getByRole('button', { name: /add product/i }));
    const productSelect = await screen.findByLabelText('Search products...');
    await waitFor(() => expect(screen.getByRole('option', { name: 'ZZT-001 - ZZT Basin' })).toBeTruthy());
    fireEvent.change(productSelect, { target: { value: 'p1' } });

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'ZZT Opp' } });
    fireEvent.change(screen.getByLabelText('Expected close date'), {
      target: { value: '2026-11-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save|submit/i }));

    await waitFor(() => expect(service.createPortalSalesOpportunity).toHaveBeenCalledTimes(1));
    const payload = service.createPortalSalesOpportunity.mock.calls[0][0];
    expect(payload.lines[0]).toEqual({ product_id: 'p1', qty: 1, unit_price: 100 });
  });
});
