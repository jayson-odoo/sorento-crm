/**
 * QUOTE-LINE-NOTE-REMARK (AC-4): the server joins the Non-cancellable flag and the line note with
 * a newline in `remark`. The page must show them on separate lines (the REMARK cell, or an
 * element inside it, carries `whitespace-pre-line`) and must never cut a long note. Masked values.
 */
import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { QuotationSignLine } from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';
import { SIGN_COLUMNS } from './signColumns.fixture';

const LONG_NOTE = 'ZZT-A1 supply only, colour to be confirmed on site. '.repeat(12).trim();

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

const COLUMNS = [...SIGN_COLUMNS.slice(0, -1), { key: 'remark', label: 'REMARK' }, SIGN_COLUMNS.at(-1)!];
const AT = COLUMNS.findIndex((column) => column.key === 'remark');

function remarkCells(remarks: (string | null)[]): HTMLTableCellElement[] {
  render(
    <QuotationSignScopes
      scopes={[
        {
          scope_label: 'ZZT Bath',
          scope_total: '200.00',
          columns: COLUMNS,
          lines: remarks.map((remark, i) => line(`l${i}`, String(i + 1), remark)),
        },
      ]}
      grandTotal="200.00"
    />,
  );
  return Array.from(document.querySelectorAll('tbody tr')).map(
    (row) => row.querySelectorAll('td')[AT] as HTMLTableCellElement,
  );
}

/** The cell itself plus every element inside it. */
function selfAndDescendants(cell: Element): Element[] {
  return [cell, ...Array.from(cell.querySelectorAll('*'))];
}

describe('QuotationSignScopes remark with a line note', () => {
  it('shows the flag and the note on separate lines (whitespace-pre-line keeps the newline)', () => {
    const [cell] = remarkCells(['Non-cancellable\nLead time 6 weeks']);
    expect(cell.textContent).toBe('Non-cancellable\nLead time 6 weeks');
    const preLine = selfAndDescendants(cell).some((el) => el.classList.contains('whitespace-pre-line'));
    expect(preLine).toBe(true);
  });

  it('shows a long note whole, never truncated', () => {
    const [cell] = remarkCells([LONG_NOTE]);
    expect(cell.textContent).toBe(LONG_NOTE);
    const cut = selfAndDescendants(cell).some(
      (el) => el.classList.contains('truncate') || Array.from(el.classList).some((c) => c.startsWith('line-clamp')),
    );
    expect(cut).toBe(false);
    // Long text wraps rather than forcing the column wide: the cell keeps newlines and wraps.
    const wraps = selfAndDescendants(cell).some((el) => el.classList.contains('whitespace-pre-line'));
    expect(wraps).toBe(true);
  });
});
