import React from 'react';
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { TownCards } from './TownCards';

const base = {
  schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
  today: { invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 1 },
  shops: [], warehouses: [], reorder: { below_count: 1, set_count: 2 }, deliveries: { to_deliver: 1 },
};

describe('TownCards approvals line', () => {
  const text = (quotations: number) =>
    render(<TownCards snapshot={{ ...base, approvals: { total: 1, purchase_requests: 1, quotation_documents: quotations } } as never} />)
      .container.textContent ?? '';

  it('says 1 quotation, not 1 quotations', () => {
    expect(text(1)).toContain('1 quotation');
    expect(text(1)).not.toContain('1 quotations');
  });

  it('keeps the plural for zero and many', () => {
    expect(text(0)).toContain('0 quotations');
    expect(text(2)).toContain('2 quotations');
  });
});
