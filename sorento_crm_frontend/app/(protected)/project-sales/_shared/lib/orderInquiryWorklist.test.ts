import { describe, expect, it } from 'vitest';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';
import {
  deliveryMonthLabel,
  flowExclusionLabel,
  formatInquiryQty,
  inquiryFooterTotals,
  inquiryRowRemaining,
  inquiryRowTaken,
  lateDaysOf,
  linkedSummary,
  orderInquiryRowHref,
  orderInquirySoLineHref,
  orderInquirySoLineLabel,
} from './orderInquiryWorklist';

function row(overrides: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return { id: 'row-1', qty: '10', state: 'raised', verb: 'ORDER', ...overrides };
}

describe('deliveryMonthLabel', () => {
  it('spells a month the way their sheet tab does', () => {
    expect(deliveryMonthLabel('2026-01')).toBe('JAN 26');
    expect(deliveryMonthLabel('2026-06')).toBe('JUNE 26');
    expect(deliveryMonthLabel('2026-09')).toBe('SEPT 26');
  });

  it('answers null rather than guessing at anything that is not a month', () => {
    expect(deliveryMonthLabel('')).toBeNull();
    expect(deliveryMonthLabel(null)).toBeNull();
    expect(deliveryMonthLabel('2026')).toBeNull();
    expect(deliveryMonthLabel('2026-13')).toBeNull();
  });
});

describe('orderInquiryRowHref', () => {
  it('sends an adopted row to the core sales order', () => {
    expect(orderInquiryRowHref(row({ core_sales_order_id: 'so-1' }))).toBe(
      '/scm/sales-orders/so-1',
    );
  });

  it('sends an authored row to its project document', () => {
    expect(
      orderInquiryRowHref(row({ project_id: 'p-1', project_sales_order_id: 'pso-1' })),
    ).toBe('/project-sales/p-1/sales-orders/pso-1');
  });

  it('prefers the core order when a row can reach both', () => {
    expect(
      orderInquiryRowHref(
        row({
          core_sales_order_id: 'so-1',
          project_id: 'p-1',
          project_sales_order_id: 'pso-1',
        }),
      ),
    ).toBe('/scm/sales-orders/so-1');
  });

  it('answers null rather than a link that would 404', () => {
    expect(orderInquiryRowHref(row())).toBeNull();
    // A project sales order with no project registration cannot be addressed the
    // project way, and an adopted row is exactly that shape.
    expect(orderInquiryRowHref(row({ project_sales_order_id: 'pso-1' }))).toBeNull();
  });
});

describe('formatInquiryQty', () => {
  it('reads a quantity the way a person does', () => {
    expect(formatInquiryQty('600.0000')).toBe('600');
    expect(formatInquiryQty('12.5000')).toBe('12.5');
    expect(formatInquiryQty('91')).toBe('91');
  });

  it('leaves anything it does not recognise alone', () => {
    expect(formatInquiryQty(null)).toBe('');
    expect(formatInquiryQty('')).toBe('');
    expect(formatInquiryQty('n/a')).toBe('n/a');
  });
});

describe('flowExclusionLabel', () => {
  it('lets an ORDER row show its own Taken/Remaining figures', () => {
    expect(flowExclusionLabel('ORDER')).toBeNull();
  });

  it('names an ADVANCE/DELAY row for what it actually is - a date change, not a buy', () => {
    expect(flowExclusionLabel('ADVANCE')).toBe('Date change');
    expect(flowExclusionLabel('DELAY')).toBe('Date change');
  });

  it('gives every other non-ORDER verb its own honest word rather than a number', () => {
    expect(flowExclusionLabel('CANCEL_BALANCE')).toBe('Balance cancelled');
    expect(flowExclusionLabel('CHANGE_SO')).toBe('SO changed');
    expect(flowExclusionLabel('PRE_ORDERED_DO_NOT_ORDER')).toBe('Pre-ordered');
    expect(flowExclusionLabel('ALREADY_INBOUND')).toBe('Already inbound');
    expect(flowExclusionLabel('RELEASE')).toBe('Released');
  });

  it('falls back to a generic honest label for an unmapped non-ORDER verb', () => {
    expect(flowExclusionLabel('BORROW_SHORTFALL')).toBe('Not an ORDER row');
    expect(flowExclusionLabel('RESERVE_AND_ORDER')).toBe('Not an ORDER row');
  });
});

describe('linkedSummary: the headline only (slice A, 8 Sep 2026 - AC-A3 drops lateness entirely)', () => {
  it('reads the coverage headline off qty and linkedQty, regardless of a late link among them', () => {
    // AC-A3: nothing in this column says "late" any more. A late link still counts
    // toward the headline exactly like an on-time one - lateness is simply not read.
    const summary = linkedSummary('25', '25', [
      { id: 'l1', kind: 'po', document: '202604-S0083', qty: '10', late: false },
      { id: 'l2', kind: 'po', document: '202606-S0082', qty: '15', late: true },
    ]);
    expect(summary).not.toBeNull();
    expect(summary).toEqual({ headline: '25 of 25' });
  });

  it('answers null for a row with no links - the cell reads a dash, never "Not found (new order)"', () => {
    expect(linkedSummary('85', '0', [])).toBeNull();
    expect(linkedSummary('85', '0', null)).toBeNull();
  });

  it('carries no fourth argument any more - the call is (qty, linkedQty, links)', () => {
    // The PHASE2-era signature took a fourth parameter; the current one does not, and a
    // caller passing one is simply ignored rather than erroring - asserted here so a
    // regression that resurrects it is caught by a signature test rather than by chance.
    expect(linkedSummary.length).toBe(3);
  });
});

describe('lateDaysOf (AC-D17): reads late_days off the wire, never recomputes it', () => {
  it('answers the server-sent day count when the document is late', () => {
    expect(lateDaysOf({ late: true, late_days: 12 })).toBe(12);
  });

  it('answers null when late_days is absent, even if `late` is true', () => {
    // The PHASE2 fallback that derived a day count client-side is gone (plan section 6):
    // this is the only source of truth now, and a missing field means "not late".
    expect(lateDaysOf({ late: true })).toBeNull();
  });

  it('answers null for a zero or negative day count - never a negative "late"', () => {
    expect(lateDaysOf({ late_days: 0 })).toBeNull();
    expect(lateDaysOf({ late_days: -3 })).toBeNull();
  });

  it('answers null when the link is not late at all', () => {
    expect(lateDaysOf({ late: false, late_days: null })).toBeNull();
  });
});

/**
 * S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1..7): Taken = a buy row's own links,
 * Remaining = Qty - Taken - bundled, both `-` on a notice row, both excluded (Remaining 0)
 * once the row or its sales-order line is cancelled.
 */
describe('inquiryRowTaken / inquiryRowRemaining (AC-B3-2..4)', () => {
  it('AC-B3-2: qty 300, links 140 + 24 -> Taken 164, Remaining 136', () => {
    const buyRow = row({ verb: 'ORDER', qty: '300', linked_qty: '164', bundled_qty: '0' });
    expect(inquiryRowTaken(buyRow)).toBe('164');
    expect(inquiryRowRemaining(buyRow)).toBe('136');
  });

  it.each(['ADVANCE', 'DELAY', 'CHANGE_SO', 'CANCEL_BALANCE', 'PRE_ORDERED_DO_NOT_ORDER', 'ALREADY_INBOUND', 'RELEASE'])(
    'AC-B3-3: a %s notice row prints "-" for both Taken and Remaining',
    (verb) => {
      const noticeRow = row({ verb, qty: '50', linked_qty: '0' });
      expect(inquiryRowTaken(noticeRow)).toBe('-');
      expect(inquiryRowRemaining(noticeRow)).toBe('-');
    },
  );

  it('AC-B3-4: a row in state cancelled reads Remaining 0, not a negative or the raw subtraction', () => {
    const cancelledRow = row({ verb: 'ORDER', qty: '50', linked_qty: '0', state: 'cancelled' });
    expect(inquiryRowRemaining(cancelledRow)).toBe('0');
  });

  it('AC-B3-4: a buy row on a cancelled SALES-ORDER LINE also reads Remaining 0', () => {
    const onCancelledLine = row({
      verb: 'ORDER',
      qty: '50',
      linked_qty: '0',
      line_cancelled: true,
    });
    expect(inquiryRowRemaining(onCancelledLine)).toBe('0');
  });

  it('never reads Remaining negative - clamps at zero once links exceed qty', () => {
    const overLinked = row({ verb: 'ORDER', qty: '10', linked_qty: '15', bundled_qty: '0' });
    expect(inquiryRowRemaining(overLinked)).toBe('0');
  });
});

describe('inquiryFooterTotals (AC-B3-5): sums over buy rows only, never a notice or cancelled row', () => {
  it('AC-B3-5: totals ten buy rows and ignores two notice rows entirely', () => {
    const buyRows = Array.from({ length: 10 }, (_unused, index) =>
      row({ id: `buy-${index}`, verb: 'ORDER', qty: '10', linked_qty: '4', bundled_qty: '0' }),
    );
    const noticeRows = [
      row({ id: 'notice-1', verb: 'ADVANCE', qty: '999', linked_qty: '0' }),
      row({ id: 'notice-2', verb: 'DELAY', qty: '999', linked_qty: '0' }),
    ];

    const totals = inquiryFooterTotals([...buyRows, ...noticeRows]);

    expect(totals.qty).toBe(100);
    expect(totals.taken).toBe(40);
    // Remaining is the FOOTER's own subtraction (qty - taken - bundled), not a sum of the
    // rows' own already-clamped Remaining figures.
    expect(totals.remaining).toBe(60);
  });

  it('excludes a cancelled row (or one on a cancelled line) from every sum', () => {
    const live = row({ id: 'live', verb: 'ORDER', qty: '100', linked_qty: '30', bundled_qty: '0' });
    const cancelled = row({
      id: 'cancelled',
      verb: 'ORDER',
      qty: '500',
      linked_qty: '200',
      state: 'cancelled',
    });
    const cancelledLine = row({
      id: 'cancelled-line',
      verb: 'ORDER',
      qty: '500',
      linked_qty: '200',
      line_cancelled: true,
    });

    const totals = inquiryFooterTotals([live, cancelled, cancelledLine]);

    expect(totals.qty).toBe(100);
    expect(totals.taken).toBe(30);
    expect(totals.remaining).toBe(70);
  });
});

/**
 * S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-1): the "SO line" text and href, shared by
 * the OI Lines tab and the worklist.
 */
describe('orderInquirySoLineLabel / orderInquirySoLineHref (AC-B6-1)', () => {
  it('prints "SO402757 · L5" when the row carries a line number', () => {
    expect(orderInquirySoLineLabel({ so_number: 'SO402757', line_no: 5 })).toBe(
      'SO402757 · L5',
    );
  });

  it('falls back to the bare SO number when no line number is on the row', () => {
    expect(orderInquirySoLineLabel({ so_number: 'SO402757', line_no: null })).toBe(
      'SO402757',
    );
  });

  it('links to the exact line once both ids are on the row', () => {
    expect(
      orderInquirySoLineHref({
        core_sales_order_id: 'core-so-1',
        core_line_id: 'core-line-5',
      }),
    ).toBe('/scm/sales-orders/core-so-1?tab=lines&line=core-line-5');
  });

  it('answers null - never a link that lands nowhere - when either id is missing', () => {
    expect(
      orderInquirySoLineHref({ core_sales_order_id: null, core_line_id: 'core-line-5' }),
    ).toBeNull();
    expect(
      orderInquirySoLineHref({ core_sales_order_id: 'core-so-1', core_line_id: null }),
    ).toBeNull();
  });
});

