/**
 * QUOTE-DESC-RICHTEXT: the customer sign page draws a styled line description the way the PDF
 * prints it, through the parser (never innerHTML); a plain one shows as typed. Values invented.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { QuotationSignLine } from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';
import { SIGN_COLUMNS } from './signColumns.fixture';

const STYLED =
  '<p><strong>ZZT ONE PIECE WC</strong> <span style="color: #dc2626">C/W SEAT COVER</span></p>';

function line(id: string, description: string): QuotationSignLine {
  return {
    id,
    item_label: id,
    description,
    technical_spec: null,
    image_url: null,
    drawing_url: null,
    brand: 'BRAND-X',
    product_code: `ZZT-${id}`,
    quantity: '2',
    unit_price: '100.00',
    complete_set: null,
    band_label: null,
    is_rate_only: false,
    amount: '200.00',
  };
}

function renderScopes(lines: QuotationSignLine[]) {
  render(
    <QuotationSignScopes
      scopes={[{ scope_label: 'Sanitary ware', scope_total: '400.00', columns: SIGN_COLUMNS, lines }]}
      grandTotal="400.00"
    />,
  );
}

describe('sign page line description', () => {
  it('draws bold and colour from a styled description', () => {
    renderScopes([line('1', STYLED)]);
    const bold = screen.getAllByText('ZZT ONE PIECE WC')[0];
    expect(bold.closest('strong')).not.toBeNull();
    const red = screen.getAllByText('C/W SEAT COVER')[0].closest('span') as HTMLElement;
    expect(red.style.color).toBe('rgb(220, 38, 38)');
    expect(document.body.textContent).not.toContain('<strong>');
  });

  it('never runs markup: a script or handler in the value draws as nothing', () => {
    renderScopes([line('1', '<p>WC<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script></p>')]);
    expect(document.querySelector('tbody img[src="x"]')).toBeNull();
    expect(document.querySelector('tbody script')).toBeNull();
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it('shows a plain description exactly as typed', () => {
    renderScopes([line('1', 'BASIN <b>MIXER</b>')]);
    expect(screen.getAllByText('BASIN <b>MIXER</b>').length).toBeGreaterThan(0);
  });

  it('names a styled item in plain words on its feedback button', () => {
    render(
      <QuotationSignScopes
        scopes={[{ scope_label: 'Sanitary ware', scope_total: '400.00', columns: SIGN_COLUMNS, lines: [line('1', STYLED)] }]}
        grandTotal="400.00"
        onFeedback={() => {}}
      />,
    );
    expect(
      screen.getAllByRole('button', { name: 'Leave feedback on ZZT ONE PIECE WC C/W SEAT COVER' }).length,
    ).toBeGreaterThan(0);
  });
});
