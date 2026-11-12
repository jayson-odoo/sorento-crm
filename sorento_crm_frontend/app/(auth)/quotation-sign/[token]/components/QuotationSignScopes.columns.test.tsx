/**
 * QUOTE-SIGN-COLUMNS: the sign page draws the quotation's own columns, as the server sends them
 * per scope, product photo included. Values invented.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { QuotationSignLine } from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';
import { SIGN_COLUMNS, SIGN_COLUMNS_WITH_IMAGE } from './signColumns.fixture';

const PHOTO = 'data:image/jpeg;base64,ZZTPHOTO';
const DRAWING = 'data:image/jpeg;base64,ZZTDRAWING';

function line(
  id: string,
  item: string,
  over: Partial<QuotationSignLine> = {},
): QuotationSignLine {
  return {
    id,
    item_label: item,
    description: `Item ${item}`,
    technical_spec: null,
    image_url: null,
    drawing_url: null,
    brand: 'BRAND-X',
    product_code: `ZZT-${item}`,
    quantity: '2',
    unit_price: '100.00',
    complete_set: null,
    band_label: null,
    is_rate_only: false,
    amount: '200.00',
    ...over,
  };
}

const LINES = [
  line('l1', '1', { image_url: PHOTO, drawing_url: DRAWING }),
  line('l2', '2', { technical_spec: 'Typed spec text', uom: 'pcs' }),
];

function headers(): string[] {
  return Array.from(document.querySelectorAll('thead th')).map(
    (th) => th.textContent?.trim() ?? '',
  );
}

describe('QuotationSignScopes columns', () => {
  it('draws exactly the server columns, in order, photo column included', () => {
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Sanitary ware',
            scope_total: '400.00',
            columns: SIGN_COLUMNS_WITH_IMAGE,
            lines: LINES,
          },
        ]}
        grandTotal="400.00"
      />,
    );
    expect(headers()).toEqual(SIGN_COLUMNS_WITH_IMAGE.map((c) => c.label));
    // Every row has one cell per column: none dropped.
    for (const tr of Array.from(document.querySelectorAll('tbody tr'))) {
      expect(tr.querySelectorAll('td')).toHaveLength(
        SIGN_COLUMNS_WITH_IMAGE.length,
      );
    }
    const photo = screen.getByAltText('Product photo, line 1');
    expect(photo).toHaveAttribute('src', PHOTO);
    const firstRow = document.querySelectorAll('tbody tr')[0];
    // The photo sits under PRODUCT IMAGE, the drawing under TECHNICAL SPEC, as on the PDF.
    expect(firstRow.querySelectorAll('td')[1]).toContainElement(photo);
    expect(
      within(firstRow.querySelectorAll('td')[2] as HTMLElement).getByAltText(
        'Technical drawing, line 1',
      ),
    ).toHaveAttribute('src', DRAWING);
    // Typed spec text from before drawings sits under the description, as on the PDF.
    const secondRow = document.querySelectorAll('tbody tr')[1];
    // QTY carries the unit, as the PDF's QTY cell does.
    expect(secondRow.querySelectorAll('td')[6].textContent).toBe('2 pcs');
    expect(secondRow.querySelectorAll('td')[3].textContent).toContain(
      'Typed spec text',
    );
  });

  it('prints cells as the PDF does: money without RM, blanks for empties', () => {
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Sanitary ware',
            scope_total: '1000.00',
            columns: SIGN_COLUMNS,
            lines: [
              line('l1', '1', {
                brand: null,
                complete_set: '  ',
                quantity: '2',
                unit_price: '500.00',
                amount: '1000.00',
              }),
            ],
          },
        ]}
        grandTotal="1000.00"
      />,
    );
    const cells = Array.from(
      document.querySelectorAll('tbody tr')[0].querySelectorAll('td'),
    ).map((td) => td.textContent);
    const at = (label: string) =>
      cells[SIGN_COLUMNS.findIndex((c) => c.label === label)];
    // The PDF's `_money`: the heading names the currency, the cell does not.
    expect(at('UNIT RATE (RM)')).toBe('500.00');
    expect(at('GRAND TOTAL')).toBe('1,000.00');
    // The PDF's `_cell`: an empty value is an empty cell, never a dash.
    expect(at('BRAND')).toBe('');
    expect(at('COMPLETE SET')).toBe('');
  });

  it('omits the photo column for a scope the server sends without it', () => {
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Fittings',
            scope_total: '400.00',
            columns: SIGN_COLUMNS,
            lines: [line('l1', '1'), line('l2', '2')],
          },
        ]}
        grandTotal="400.00"
      />,
    );
    expect(headers()).toEqual(SIGN_COLUMNS.map((c) => c.label));
    expect(screen.queryByText('PRODUCT IMAGE')).toBeNull();
  });

  // PS-QUOTE-MATRIX retired suggest mode: the icon column is the feedback button now.
  it('keeps the photo column with feedback on, plus one icon column', () => {
    const onFeedback = vi.fn();
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Sanitary ware',
            scope_total: '400.00',
            columns: SIGN_COLUMNS_WITH_IMAGE,
            lines: LINES,
          },
        ]}
        grandTotal="400.00"
        onFeedback={onFeedback}
      />,
    );
    expect(headers().slice(0, -1)).toEqual(
      SIGN_COLUMNS_WITH_IMAGE.map((c) => c.label),
    );
    expect(headers()).toHaveLength(SIGN_COLUMNS_WITH_IMAGE.length + 1);
    expect(screen.getByAltText('Product photo, line 1')).toBeInTheDocument();
    // Named by its description, never by the printed number the ITEM column shows.
    screen.getByRole('button', { name: 'Leave feedback on Item 1' }).click();
    expect(onFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ itemLabel: 'Item 1', scopeLabel: 'Sanitary ware' }),
    );
  });
});

/**
 * PROPOSAL-FORM-COLLAPSE (owner, 10 Nov 2026): a heading is its own row. The sign page draws it
 * as the band, as the PDF does; it is not an item, takes no number and gets no feedback button.
 */
describe('QuotationSignScopes heading rows', () => {
  const heading: QuotationSignLine = {
    ...line('h1', ''),
    item_label: null,
    description: null,
    product_code: null,
    brand: null,
    quantity: '0',
    unit_price: '0',
    amount: null,
    band_label: 'PAGE 1',
    is_section: true,
  };

  it('draws a heading row as one band and counts only the items', () => {
    render(
      <QuotationSignScopes
        scopes={[
          {
            scope_label: 'Sanitary ware',
            scope_total: '400.00',
            columns: SIGN_COLUMNS,
            lines: [LINES[0], heading, LINES[1]],
          },
        ]}
        grandTotal="400.00"
        onFeedback={vi.fn()}
      />,
    );
    const rows = Array.from(document.querySelectorAll('tbody tr'));
    expect(rows).toHaveLength(3);
    expect(rows[1].querySelectorAll('td')).toHaveLength(1);
    expect(rows[1]).toHaveTextContent('PAGE 1');
    expect(screen.getAllByRole('button', { name: /^Leave feedback on / })).toHaveLength(2);
    expect(screen.getByText('2 items')).toBeInTheDocument();
  });
});
