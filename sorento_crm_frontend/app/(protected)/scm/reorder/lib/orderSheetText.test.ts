/**
 * AC-S9.2 (PLAN-reorder-feedback-9sep.md, S9) - the text the Order summary sheet's
 * Delivery / Project-customer / Remarks cells render, so the composition is tested once
 * rather than three ways inside the grid. Separator is a PLAIN hyphen with spaces on
 * either side, never an em or en dash (repo-wide rule, CLAUDE.md).
 */
import { describe, expect, it } from 'vitest';
import { customersText, monthText, remarksText } from './orderSheetText';

describe('monthText (Delivery column)', () => {
  it('renders month groups oldest first, newest last, with an undated bucket appended', () => {
    const text = monthText([
      { month: '2026-09', qty: 30 },
      { month: '2026-10', qty: 30 },
      { month: null, qty: 5 },
    ]);
    expect(text).toBe('Sep 30 - Oct 30 - undated 5');
  });

  it('a single dated month, no undated bucket', () => {
    expect(monthText([{ month: '2026-09', qty: 30 }])).toBe('Sep 30');
  });

  it('empty input renders an empty string', () => {
    expect(monthText([])).toBe('');
  });
});

describe('customersText (Project / customer column)', () => {
  it('renders label + qty in brackets, comma-separated', () => {
    const text = customersText([
      { label: 'OIB Construction', qty: 364 },
      { label: 'Sepang', qty: 480 },
    ]);
    expect(text).toBe('OIB Construction (364), Sepang (480)');
  });

  it('empty input renders an empty string', () => {
    expect(customersText([])).toBe('');
  });
});

describe('remarksText (Remarks column)', () => {
  it('composes PO + incoming, last receipt and MOQ, hyphen-separated', () => {
    const text = remarksText({
      po_open_qty: 400, incoming_spo_qty: 89,
      last_receipt: { date: '2026-07-21', qty: 300 },
      moq: 1000,
    });
    expect(text).toBe('PO 400 + incoming 89 = 489 - Last in 21/07/2026, 300 - MOQ 1000');
    expect(text).not.toMatch(/[\u2013\u2014]/); // never an en (\u2013) or em (\u2014) dash
  });

  it('omits a section that carries nothing to say', () => {
    const text = remarksText({
      po_open_qty: 0, incoming_spo_qty: 0, last_receipt: null, moq: null,
    });
    expect(text).toBe('');
  });

  it('omits only the missing sections, keeping the rest', () => {
    const text = remarksText({
      po_open_qty: 0, incoming_spo_qty: 0, last_receipt: null, moq: 1000,
    });
    expect(text).toBe('MOQ 1000');
  });
});
