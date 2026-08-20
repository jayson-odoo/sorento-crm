import { describe, expect, it } from 'vitest';
import type { OrderInquiryWorklistRow } from '../types/orderInquiry.types';
import {
  deliveryMonthLabel,
  flowExclusionLabel,
  formatInquiryQty,
  orderInquiryRowHref,
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
