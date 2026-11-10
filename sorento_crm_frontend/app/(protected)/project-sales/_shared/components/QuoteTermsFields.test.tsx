import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/** QUOTE-TERMS-SELECT: Payment Terms is a select over the synced AutoCount terms; Validity is a
 *  number and a unit sent as a pair; a legacy free text stays visible until someone picks. */

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">none</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const terms = [
  { id: 'pt-cbd', code: 'C.B.D.', description: 'CASH BEFORE DELIVERY', label: 'CASH BEFORE DELIVERY' },
  { id: 'pt-30', code: '30 DAYS', description: null, label: '30 DAYS' },
];
let lastProjectId: string | undefined;
vi.mock('../hooks/usePaymentTerms', () => ({
  usePaymentTermOptions: (projectId?: string) => {
    lastProjectId = projectId;
    return { data: terms, isLoading: false, error: null, refetch: vi.fn() };
  },
}));

import { QuoteTermsFields } from './QuoteTermsFields';

const onChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  lastProjectId = undefined;
});

function renderFields(values: React.ComponentProps<typeof QuoteTermsFields>['values'], projectId?: string) {
  return render(
    <QuoteTermsFields idPrefix="t" values={values} onChange={onChange} projectId={projectId} />,
  );
}

describe('QuoteTermsFields', () => {
  it('lists the synced terms and sends the pick with its printed label', () => {
    renderFields({});
    const select = screen.getByLabelText('Payment Terms') as HTMLSelectElement;
    expect(select.dataset.clearable).toBe('true');
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      'none',
      'CASH BEFORE DELIVERY',
      '30 DAYS',
    ]);
    fireEvent.change(select, { target: { value: 'pt-cbd' } });
    expect(onChange).toHaveBeenLastCalledWith({
      payment_term_id: 'pt-cbd',
      payment_terms: 'CASH BEFORE DELIVERY',
    });
  });

  it('clearing the select clears the pick and the text', () => {
    renderFields({ payment_term_id: 'pt-cbd', payment_terms: 'CASH BEFORE DELIVERY' });
    fireEvent.change(screen.getByLabelText('Payment Terms'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith({ payment_term_id: null, payment_terms: null });
  });

  it('shows a legacy free text as Current until a term is picked', () => {
    renderFields({ payment_terms: '50% deposit, balance before delivery', validity: '30 days from quotation date' });
    expect(screen.getByText('Current: 50% deposit, balance before delivery')).toBeTruthy();
    expect(screen.getByText('Current: 30 days from quotation date')).toBeTruthy();
    expect((screen.getByLabelText('Payment Terms') as HTMLSelectElement).value).toBe('');
  });

  it('a picked term no longer synced still shows as picked', () => {
    renderFields({ payment_term_id: 'pt-gone', payment_terms: 'RETIRED TERM' });
    const select = screen.getByLabelText('Payment Terms') as HTMLSelectElement;
    expect(select.value).toBe('pt-gone');
    expect(screen.queryByText(/Current:/)).toBeNull();
  });

  it('validity is sent only once both the number and the unit are set, printed like the cover', () => {
    renderFields({});
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '2' } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Validity unit'), { target: { value: 'week' } });
    expect(onChange).toHaveBeenLastCalledWith({
      validity_value: 2,
      validity_unit: 'week',
      validity: '2 WEEKS',
    });
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '1' } });
    expect(onChange).toHaveBeenLastCalledWith({
      validity_value: 1,
      validity_unit: 'week',
      validity: '1 WEEK',
    });
  });

  it('a number out of 1..999 is not sent', () => {
    renderFields({ validity_value: 2, validity_unit: 'week', validity: '2 WEEKS' });
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '1000' } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('emptying the number clears the validity and its unit', () => {
    renderFields({ validity_value: 2, validity_unit: 'week', validity: '2 WEEKS' });
    fireEvent.change(screen.getByLabelText('Validity'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith({
      validity_value: null,
      validity_unit: null,
      validity: null,
    });
    expect((screen.getByLabelText('Validity unit') as HTMLSelectElement).value).toBe('');
  });

  it('shows what prints when a synced link reads differently from the pick', () => {
    renderFields({ payment_term_id: 'pt-30', payment_terms: '30 days' });
    expect(screen.getByText('Current: 30 days')).toBeTruthy();
  });

  it('a retired pick with no text never shows an id', () => {
    renderFields({ payment_term_id: 'pt-gone', payment_terms: null });
    const select = screen.getByLabelText('Payment Terms') as HTMLSelectElement;
    expect(select.options[select.selectedIndex].textContent).toBe('Retired term');
  });

  it('asks the project for its terms on the quotation form', () => {
    renderFields({}, 'proj-1');
    expect(lastProjectId).toBe('proj-1');
  });
});
