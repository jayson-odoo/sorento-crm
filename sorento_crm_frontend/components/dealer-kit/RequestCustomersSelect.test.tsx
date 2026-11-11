/** PRICETAG-REQUEST-LAYOUT: the real chip select (the form suites use its __mocks__ stand-in). */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RequestCustomersSelect } from './RequestCustomersSelect';
import { customersLabel, requestCustomers } from '@/lib/dealer-kit/request-customers';

const OPTIONS = [
  { code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' },
  { code: 'ZZTD02', name: 'ZZT Second Dealer' },
];

describe('RequestCustomersSelect', () => {
  it('shows one removable chip per customer, in pick order', () => {
    render(
      <RequestCustomersSelect
        value={[OPTIONS[1], OPTIONS[0]]}
        options={OPTIONS}
        onChange={vi.fn()}
      />,
    );
    const chips = screen.getAllByRole('button', { name: /^Remove / });
    expect(chips.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Remove ZZT Second Dealer',
      'Remove ZZT Dealer Sdn Bhd',
    ]);
  });

  it('removing a chip hands back the rest as {code, name}', () => {
    const onChange = vi.fn();
    render(<RequestCustomersSelect value={OPTIONS} options={OPTIONS} onChange={onChange} />);
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Remove ZZT Dealer Sdn Bhd' }));
    expect(onChange).toHaveBeenCalledWith([{ code: 'ZZTD02', name: 'ZZT Second Dealer' }]);
  });

  it('keeps the name of a customer the lookup no longer lists', () => {
    render(
      <RequestCustomersSelect
        value={[{ code: 'ZZT-OLD', name: 'ZZT Old Dealer' }]}
        options={OPTIONS}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Remove ZZT Old Dealer' })).toBeInTheDocument();
  });
});

describe('request-customers helpers', () => {
  it('labels one customer by name and several as "First +N"', () => {
    expect(customersLabel([])).toBeNull();
    expect(customersLabel([OPTIONS[0]])).toBe('ZZT Dealer Sdn Bhd');
    expect(customersLabel([OPTIONS[0], OPTIONS[1], { code: null, name: 'C' }])).toBe('ZZT Dealer Sdn Bhd +2');
  });

  it('reads an older request as its one debtor', () => {
    expect(requestCustomers({ debtor_code: 'ZZTD01', debtor_name: 'ZZT Dealer Sdn Bhd' })).toEqual([
      { code: 'ZZTD01', name: 'ZZT Dealer Sdn Bhd' },
    ]);
    expect(requestCustomers({ debtor_code: null, debtor_name: null })).toEqual([]);
    expect(requestCustomers({ customers: [OPTIONS[1]], debtor_name: 'x' })).toEqual([OPTIONS[1]]);
  });
});
