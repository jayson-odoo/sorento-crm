/**
 * Reading a worklist row that came from either arm of the union.
 *
 * The ordering rule is the one worth pinning hardest: AC-FP04 asks for earliest outstanding
 * required date first, nulls last, TOTAL. An order that is merely mostly-sorted is what puts one
 * row on two pages of a paged list and another on none, and that failure is invisible on page one.
 */
import { describe, expect, it } from 'vitest';
import {
  formatOutstandingQty,
  isNotStarted,
  planningRowKey,
  planningRowProjectLabel,
  planningRowReference,
  planningRowSalesOrderHref,
  sortByEarliestRequired,
} from './fulfilmentPlanningRows';
import type { FulfilmentPlanningRow } from '../types/fulfilmentPlanning.types';

function row(overrides: Partial<FulfilmentPlanningRow> = {}): FulfilmentPlanningRow {
  return { line_count: 1, review_state: 'not_started', ...overrides };
}

describe('planningRowKey', () => {
  it('keys a not-started row on its core sales order, which is the only id it has', () => {
    expect(planningRowKey(row({ sales_order_id: 'so-345418', so_number: 'SO345418' }))).toBe(
      'so-345418',
    );
  });

  it('prefers the planning record once one exists, so the row keeps its place after adoption', () => {
    expect(
      planningRowKey(
        row({ id: 'pso-adopted-345418', sales_order_id: 'so-345418', so_number: 'SO345418' }),
      ),
    ).toBe('pso-adopted-345418');
  });

  it('falls back to the human key rather than answering with nothing', () => {
    expect(planningRowKey(row({ provisional_ref: 'PSO-000123' }))).toBe('PSO-000123');
  });
});

describe('planningRowReference', () => {
  it('names an adopted row by its sales-order number', () => {
    expect(planningRowReference(row({ so_number: 'SO345418' }))).toBe('SO345418');
  });

  it('falls back to the document number, then to our own reference', () => {
    expect(planningRowReference(row({ autocount_doc_no: 'SO376201' }))).toBe('SO376201');
    expect(planningRowReference(row({ provisional_ref: 'PSO-000123' }))).toBe('PSO-000123');
  });

  it('answers null rather than an id when the row has no human key at all', () => {
    expect(planningRowReference(row({ sales_order_id: 'so-345418' }))).toBeNull();
  });
});

/**
 * Reaching the sales order from a row (captain: "on click i should be able to view the SO").
 *
 * The identity column is the link, which is this repo's usual idiom for a listing - the SCM
 * sales-order list and the purchase-order list both make the document number the way in. The
 * row itself keeps its existing meaning (open the plan), so nothing a CS already does changes.
 */
describe('planningRowSalesOrderHref', () => {
  it('sends an AutoCount-arm row to the core sales order', () => {
    expect(
      planningRowSalesOrderHref(
        row({ row_kind: 'sales_order', sales_order_id: 'so-345418', so_number: 'SO345418' }),
      ),
    ).toBe('/scm/sales-orders/so-345418');
  });

  it('sends an authored row to its project sales order', () => {
    expect(
      planningRowSalesOrderHref(
        row({
          row_kind: 'planning_record',
          id: 'pso-1',
          project_id: 'proj-1',
          provisional_ref: 'PSO-000123',
        }),
      ),
    ).toBe('/project-sales/proj-1/sales-orders/pso-1');
  });

  it('prefers the core sales order when a row can reach both', () => {
    expect(
      planningRowSalesOrderHref(
        row({ sales_order_id: 'so-345418', id: 'pso-1', project_id: 'proj-1' }),
      ),
    ).toBe('/scm/sales-orders/so-345418');
  });

  it('answers null rather than a dead link when there is nothing to open', () => {
    // An adopted record has no project registration, so the project route cannot be built for
    // it; a row with no core order either is simply not linkable, and says so by rendering
    // plain text.
    expect(planningRowSalesOrderHref(row({ id: 'pso-1', project_id: null }))).toBeNull();
    expect(planningRowSalesOrderHref(row({ project_id: 'proj-1' }))).toBeNull();
    expect(planningRowSalesOrderHref(row({ provisional_ref: 'PSO-000123' }))).toBeNull();
  });
});

describe('planningRowProjectLabel', () => {
  it('prefers the registered project name', () => {
    expect(
      planningRowProjectLabel(
        row({ project_name: 'Tuju Residences', project_label: 'Tuju Residences' }),
      ),
    ).toBe('Tuju Residences');
  });

  it('falls back to the project string the sales-order book carried', () => {
    expect(
      planningRowProjectLabel(row({ project_label: 'GLOBAL INGRESS/ 252U RMMJ TAMAN IMPIAN EMAS' })),
    ).toBe('GLOBAL INGRESS/ 252U RMMJ TAMAN IMPIAN EMAS');
  });

  it('answers null when the order named no project, so the screen can say so', () => {
    expect(planningRowProjectLabel(row())).toBeNull();
  });
});

describe('isNotStarted', () => {
  it('is true only for the state that means no planning record exists', () => {
    expect(isNotStarted(row({ review_state: 'not_started' }))).toBe(true);
    expect(isNotStarted(row({ review_state: 'needs_cs_review' }))).toBe(false);
    expect(isNotStarted(row({ review_state: 'confirmed' }))).toBe(false);
    expect(isNotStarted(row({ review_state: 'awaiting_reconciliation' }))).toBe(false);
  });
});

describe('formatOutstandingQty', () => {
  it('reads a decimal string as a quantity, not as a machine', () => {
    expect(formatOutstandingQty('5488.0000')).toBe('5488');
    expect(formatOutstandingQty('10470.0000')).toBe('10470');
  });

  it('keeps a real fraction', () => {
    expect(formatOutstandingQty('12.5000')).toBe('12.5');
  });

  it('answers null for an absent quantity rather than a misleading zero', () => {
    expect(formatOutstandingQty(null)).toBeNull();
    expect(formatOutstandingQty(undefined)).toBeNull();
    expect(formatOutstandingQty('')).toBeNull();
  });

  it('shows a genuine zero as zero', () => {
    expect(formatOutstandingQty('0.0000')).toBe('0');
  });
});

describe('sortByEarliestRequired (AC-FP04)', () => {
  it('puts the work that is due soonest first', () => {
    const sorted = sortByEarliestRequired([
      row({ so_number: 'SO396071', earliest_required_date: '2025-09-01' }),
      row({ so_number: 'SO391698', earliest_required_date: '2022-07-03' }),
      row({ so_number: 'SO346436', earliest_required_date: '2025-04-23' }),
    ]);
    expect(sorted.map((entry) => entry.so_number)).toEqual([
      'SO391698',
      'SO346436',
      'SO396071',
    ]);
  });

  it('puts an undated order last, never first by accident', () => {
    const sorted = sortByEarliestRequired([
      row({ so_number: 'SO000001', earliest_required_date: null }),
      row({ so_number: 'SO391698', earliest_required_date: '2022-07-03' }),
    ]);
    expect(sorted.map((entry) => entry.so_number)).toEqual(['SO391698', 'SO000001']);
  });

  it('breaks a tie on the sales-order number, so the order is total and stable', () => {
    const sorted = sortByEarliestRequired([
      row({ so_number: 'SO349755', earliest_required_date: '2025-09-22' }),
      row({ so_number: 'SO345070', earliest_required_date: '2025-09-22' }),
      row({ so_number: 'SO349754', earliest_required_date: '2025-09-22' }),
    ]);
    expect(sorted.map((entry) => entry.so_number)).toEqual([
      'SO345070',
      'SO349754',
      'SO349755',
    ]);
  });

  it('orders two undated rows against each other rather than leaving them arbitrary', () => {
    const sorted = sortByEarliestRequired([
      row({ so_number: 'SO000002', earliest_required_date: null }),
      row({ so_number: 'SO000001', earliest_required_date: null }),
    ]);
    expect(sorted.map((entry) => entry.so_number)).toEqual(['SO000001', 'SO000002']);
  });

  it('does not mutate the list it was given', () => {
    const input = [
      row({ so_number: 'SO396071', earliest_required_date: '2025-09-01' }),
      row({ so_number: 'SO391698', earliest_required_date: '2022-07-03' }),
    ];
    sortByEarliestRequired(input);
    expect(input.map((entry) => entry.so_number)).toEqual(['SO396071', 'SO391698']);
  });
});
