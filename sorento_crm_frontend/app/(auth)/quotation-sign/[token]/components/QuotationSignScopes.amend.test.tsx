/**
 * QUOTE-CUSTOMER-AMEND fix round 2, on the sign page's table itself. Values invented.
 *
 * - D1: the table's scroller is positioned, so the sr-only label in the suggest-mode icon column
 *   (position: absolute) is clipped by it instead of widening the page at 375px.
 * - Answered Amount: a line whose suggestions were accepted shows the amount it now comes to (the
 *   issued value for a side not accepted); an accepted removal shows no amount.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  QuotationSignAmendment,
  QuotationSignLine,
} from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';

function line(id: string, item: string, over: Partial<QuotationSignLine> = {}): QuotationSignLine {
  return {
    id,
    item_label: item,
    description: `Item ${item}`,
    technical_spec: null,
    brand: null,
    product_code: `ZZT-${item}`,
    quantity: '120',
    unit_price: '400.00',
    complete_set: null,
    band_label: null,
    is_rate_only: false,
    amount: '48000.00',
    ...over,
  };
}

const LINES = [
  line('l1', '1'),
  line('l2', '2', { unit_price: '160.00', amount: '19200.00' }),
  line('l3', '3', { quantity: '10', unit_price: '25.00', amount: '250.00' }),
  line('l4', '4', { unit_price: '50.00', amount: '6000.00' }),
];

function row(lineId: string, field: string, to: string | null, decision: string) {
  return {
    id: `r-${lineId}-${field}`,
    line_id: lineId,
    field,
    value_from: null,
    value_to: to,
    decision,
    decision_reason: null,
  };
}

function tr(item: string): HTMLElement {
  const found = Array.from(document.querySelectorAll('tbody tr')).find(
    (el) => el.querySelector('td')?.textContent?.trim() === item,
  );
  if (!found) throw new Error(`no row ${item}`);
  return found as HTMLElement;
}

/** The Amount cell: the ninth. */
function amountOf(item: string): string {
  return tr(item).querySelectorAll('td')[8]?.textContent ?? '';
}

describe('QuotationSignScopes, fix round 2', () => {
  it('D1: scrolls the table inside a positioned scroller in suggest mode', () => {
    render(
      <QuotationSignScopes
        scopes={[{ scope_label: 'Sanitary ware', scope_total: '73450.00', lines: LINES }]}
        grandTotal="73450.00"
        suggest={{ edits: {}, onEdit: vi.fn(), onToggleRemove: vi.fn() }}
      />,
    );
    const scroller = screen.getByRole('table').parentElement as HTMLElement;
    expect(scroller.className).toContain('overflow-x-auto');
    expect(scroller.className).toContain('relative');
  });

  it('shows the answered amount on an accepted line, and none on an accepted removal', () => {
    const amendment = {
      id: 'req-1',
      status: 'applied',
      submitted_at: '2026-10-30T06:05:00',
      requester_name: 'Buyer A',
      note: null,
      rows: [
        row('l1', 'quantity', '110.00', 'accepted'),
        row('l1', 'unit_price', '380.00', 'accepted'),
        // Price accepted, quantity as issued: 120 x 150.00.
        row('l2', 'unit_price', '150.00', 'accepted'),
        row('l3', 'remove', null, 'accepted'),
        // Rejected: the issued amount stands.
        row('l4', 'unit_price', '40.00', 'rejected'),
      ],
    } as unknown as QuotationSignAmendment;
    render(
      <QuotationSignScopes
        scopes={[{ scope_label: 'Sanitary ware', scope_total: '73450.00', lines: LINES }]}
        grandTotal="73450.00"
        amendment={amendment}
      />,
    );
    expect(amountOf('1')).toMatch(/RM\s*41,800\.00/);
    expect(amountOf('2')).toMatch(/RM\s*18,000\.00/);
    expect(amountOf('3')).not.toMatch(/RM/);
    expect(amountOf('3')).toMatch(/Removal accepted/);
    expect(amountOf('4')).toMatch(/RM\s*6,000\.00/);
  });
});
