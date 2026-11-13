/**
 * NON-CANCELLABLE-ITEMS: the server adds a REMARK column when a scope has a non-cancellable line
 * and each line carries `remark`. The page draws it like any other column. Values invented.
 */
import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { QuotationSignLine } from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';
import { SIGN_COLUMNS } from './signColumns.fixture';

function line(id: string, item: string, remark: string | null): QuotationSignLine {
  return {
    id,
    item_label: item,
    description: `Item ${item}`,
    technical_spec: null,
    brand: 'BRAND-X',
    product_code: `ZZT-${item}`,
    quantity: '1',
    unit_price: '100.00',
    complete_set: null,
    remark,
    band_label: null,
    is_rate_only: false,
    amount: '100.00',
  };
}

describe('QuotationSignScopes remark column', () => {
  it('draws the REMARK header and the remark cell, blank where a line has none', () => {
    const columns = [...SIGN_COLUMNS.slice(0, -1), { key: 'remark', label: 'REMARK' }, SIGN_COLUMNS.at(-1)!];
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Bath',
            scope_total: '200.00',
            columns,
            lines: [line('l1', '1', 'Non-cancellable'), line('l2', '2', null)],
          },
        ]}
        grandTotal="200.00"
      />,
    );
    const headers = Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent?.trim());
    expect(headers).toContain('REMARK');
    const at = columns.findIndex((column) => column.key === 'remark');
    const rows = document.querySelectorAll('tbody tr');
    expect(rows[0].querySelectorAll('td')[at].textContent).toBe('Non-cancellable');
    expect(rows[1].querySelectorAll('td')[at].textContent).toBe('');
  });
});
