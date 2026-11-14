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

/**
 * The area-grid (matrix) table: the server sends `remark` in a matrix scope's columns too, and the
 * PDF's matrix layout prints REMARK after the unit rate and before the money (the plain columns
 * after QTY keep their order: UNIT RATE, COMPLETE SET, REMARK, GRAND TOTAL). The page mirrors it.
 */
const MATRIX = [
  { key: 'ta', label: 'ZZT TYPE A', cols: [{ key: 'ta-bh', label: '1 BH' }, { key: 'ta-kit', label: 'Kitchen' }] },
];

function renderMatrix(columns: typeof COLUMNS, remark: string | null) {
  render(
    <QuotationSignScopes
      scopes={[
        {
          scope_label: 'ZZT Units',
          scope_total: '200.00',
          columns,
          matrix_columns: MATRIX,
          lines: [{ ...line('m1', '1', remark), quantity: '2', qty_cells: { 'ta-bh': '2.00' } }],
        },
      ]}
      grandTotal="200.00"
    />,
  );
}

function topHeaders(): string[] {
  const first = document.querySelector('thead tr');
  return Array.from(first?.querySelectorAll('th') ?? []).map((th) => th.textContent?.trim() ?? '');
}

/** The body cell whose whole text is ``text``. */
function cellWithText(text: string): HTMLTableCellElement | undefined {
  return Array.from(document.querySelectorAll('tbody td')).find((td) => td.textContent === text) as
    | HTMLTableCellElement
    | undefined;
}

describe('QuotationSignScopes matrix scope remark', () => {
  it('draws a REMARK header between Unit rate and Amount, as the PDF matrix does', () => {
    renderMatrix(COLUMNS, 'Non-cancellable\nLead time 6 weeks');
    const heads = topHeaders();
    expect(heads).toContain('REMARK');
    const at = heads.indexOf('REMARK');
    expect(at).toBeGreaterThan(heads.findIndex((h) => /unit rate/i.test(h)));
    expect(at).toBeLessThan(heads.findIndex((h) => /^amount$/i.test(h)));
  });

  it('shows the flag and the note on separate lines in the matrix REMARK cell', () => {
    renderMatrix(COLUMNS, 'Non-cancellable\nLead time 6 weeks');
    const cell = cellWithText('Non-cancellable\nLead time 6 weeks');
    expect(cell).toBeDefined();
    const preLine = selfAndDescendants(cell!).some((el) => el.classList.contains('whitespace-pre-line'));
    expect(preLine).toBe(true);
  });

  it('shows a long note whole in the matrix REMARK cell, never truncated', () => {
    renderMatrix(COLUMNS, LONG_NOTE);
    const cell = cellWithText(LONG_NOTE);
    expect(cell).toBeDefined();
    const cut = selfAndDescendants(cell!).some(
      (el) => el.classList.contains('truncate') || Array.from(el.classList).some((c) => c.startsWith('line-clamp')),
    );
    expect(cut).toBe(false);
  });

  it('draws no REMARK header on a matrix scope whose columns lack remark', () => {
    renderMatrix(SIGN_COLUMNS, null);
    expect(topHeaders()).not.toContain('REMARK');
    expect(topHeaders().length).toBeGreaterThan(0);
  });
});

/**
 * Crew pass at 1280 (13 Nov): the plain table summed to 1274px of minimum widths inside the sign
 * card's 1182px inner width (crew copy; the cloud re-check measured the table box at 1152px,
 * the scrollbar and padding being the difference), clipping GRAND TOTAL. jsdom has no layout, so the guard reads each
 * header's `min-w-[Npx]` (and the feedback column's `w-10` = 40px) and sums them. Tailwind's
 * preflight is border-box, so a min width already includes the cell padding.
 */
const SIGN_CARD_INNER_AT_1280 = 1152;

function headerMinWidth(th: Element): number {
  const classes = Array.from(th.classList);
  const min = classes.map((c) => /^min-w-\[(\d+)px\]$/.exec(c)).find(Boolean);
  if (min) return Number(min[1]);
  if (classes.includes('w-10')) return 40;
  return 0;
}

describe('QuotationSignScopes plain table width with REMARK', () => {
  it('fits the sign card at 1280: header min widths sum to at most 1152px, REMARK at least 130px', () => {
    const columns = [
      { key: 'item', label: 'ITEM' },
      { key: 'spec', label: 'TECHNICAL SPEC' },
      { key: 'description', label: 'DESCRIPTION' },
      { key: 'brand', label: 'BRAND' },
      { key: 'product_code', label: 'PRODUCT CODE' },
      { key: 'qty', label: 'QTY' },
      { key: 'unit_rate', label: 'UNIT RATE (RM)' },
      { key: 'complete_set', label: 'COMPLETE SET' },
      { key: 'remark', label: 'REMARK' },
      { key: 'amount', label: 'GRAND TOTAL' },
    ];
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'ZZT Bath',
            scope_total: '100.00',
            columns,
            lines: [line('w1', '1', 'Non-cancellable\nLead time 6 weeks')],
          },
        ]}
        grandTotal="100.00"
        onFeedback={() => {}}
      />,
    );
    const heads = Array.from(document.querySelectorAll('thead th'));
    // Every server column plus the feedback column: a missing header would shrink the sum falsely.
    expect(heads).toHaveLength(columns.length + 1);
    const remark = heads.find((th) => th.textContent?.trim() === 'REMARK');
    expect(remark).toBeDefined();
    expect(headerMinWidth(remark!)).toBeGreaterThanOrEqual(130);
    const total = heads.reduce((sum, th) => sum + headerMinWidth(th), 0);
    expect(total).toBeLessThanOrEqual(SIGN_CARD_INNER_AT_1280);
  });
});
