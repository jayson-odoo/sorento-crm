/**
 * `buildContainerRequestMatrix` - the Stage 1 schedule view's own build step (6b.2): the same
 * `lines` the container-request build already returned, regrouped client-side by Product or
 * SO axis and bucketed by day/week/month. No second fetch, no second idea of what is in a
 * cell - see the module docstring.
 */
import { describe, it, expect } from 'vitest';
import { buildContainerRequestMatrix } from './containerRequestMatrix';
import type { ContainerRequestSoLine } from '../../services/fulfilmentService';

function soLine(over: Partial<ContainerRequestSoLine> = {}): ContainerRequestSoLine {
  return {
    product_id: 'p1',
    item_code: 'ITEM-1',
    so_number: 'SO-1',
    customer_label: 'Acme Sdn Bhd',
    demand_class: 'project',
    order_date: '2026-08-01',
    required_date: '2026-08-19',
    qty: 10,
    ...over,
  };
}

describe('buildContainerRequestMatrix - bucketing', () => {
  it('day granularity buckets on the exact required_date', () => {
    const matrix = buildContainerRequestMatrix([soLine({ required_date: '2026-08-19' })], 'product', 'day');
    expect(matrix.buckets).toHaveLength(1);
    expect(matrix.buckets[0]).toMatchObject({ key: '2026-08-19', kind: 'dated', label: '19 Aug 2026' });
  });

  it('week granularity buckets to the Monday of that week', () => {
    // 2026-08-19 is a Wednesday; the week starts Monday 2026-08-17.
    const matrix = buildContainerRequestMatrix([soLine({ required_date: '2026-08-19' })], 'product', 'week');
    expect(matrix.buckets).toHaveLength(1);
    expect(matrix.buckets[0].key).toBe('2026-08-17');
  });

  it('month granularity buckets to the first of the month', () => {
    const matrix = buildContainerRequestMatrix([soLine({ required_date: '2026-08-19' })], 'product', 'month');
    expect(matrix.buckets).toHaveLength(1);
    expect(matrix.buckets[0]).toMatchObject({ key: '2026-08', kind: 'dated', label: 'Aug 2026' });
  });

  it('two lines the same week collapse into ONE bucket', () => {
    const matrix = buildContainerRequestMatrix(
      [soLine({ required_date: '2026-08-17' }), soLine({ required_date: '2026-08-21' })],
      'product',
      'week',
    );
    expect(matrix.buckets).toHaveLength(1);
  });

  it('a line with no required_date lands in the No date bucket', () => {
    const matrix = buildContainerRequestMatrix([soLine({ required_date: null })], 'product', 'week');
    expect(matrix.buckets).toHaveLength(1);
    expect(matrix.buckets[0]).toMatchObject({ key: 'no_date', kind: 'no_date', label: 'No date' });
  });

  it('the No date bucket sorts FIRST, not last (this screen\'s own rule)', () => {
    const matrix = buildContainerRequestMatrix(
      [
        soLine({ required_date: '2026-01-05' }),
        soLine({ required_date: null }),
        soLine({ required_date: '2026-12-25' }),
      ],
      'product',
      'day',
    );
    expect(matrix.buckets.map((b) => b.kind)).toEqual(['no_date', 'dated', 'dated']);
    expect(matrix.buckets[0].key).toBe('no_date');
  });

  it('dated buckets sort chronologically after the No date bucket', () => {
    const matrix = buildContainerRequestMatrix(
      [soLine({ required_date: '2026-12-25' }), soLine({ required_date: '2026-01-05' })],
      'product',
      'day',
    );
    expect(matrix.buckets.map((b) => b.key)).toEqual(['2026-01-05', '2026-12-25']);
  });
});

describe('buildContainerRequestMatrix - the axis', () => {
  it('the product axis groups by item_code, one row per product', () => {
    const matrix = buildContainerRequestMatrix(
      [
        soLine({ item_code: 'ITEM-1', so_number: 'SO-1' }),
        soLine({ item_code: 'ITEM-1', so_number: 'SO-2' }),
        soLine({ item_code: 'ITEM-2', so_number: 'SO-3' }),
      ],
      'product',
      'day',
    );
    expect(matrix.rows.map((r) => r.label).sort()).toEqual(['ITEM-1', 'ITEM-2']);
  });

  it('the order axis groups by so_number, one row per order, with the customer as description', () => {
    const matrix = buildContainerRequestMatrix(
      [soLine({ so_number: 'SO-1', customer_label: 'Acme Sdn Bhd' })],
      'order',
      'day',
    );
    expect(matrix.rows).toHaveLength(1);
    expect(matrix.rows[0]).toMatchObject({ label: 'SO-1', description: 'Acme Sdn Bhd' });
  });

  it('a line with no SO number still gets an order-axis row, labelled honestly', () => {
    const matrix = buildContainerRequestMatrix([soLine({ so_number: null })], 'order', 'day');
    expect(matrix.rows[0].label).toBe('Not numbered');
  });

  it('a line with no item code still gets a product-axis row, labelled honestly', () => {
    const matrix = buildContainerRequestMatrix([soLine({ item_code: null })], 'product', 'day');
    expect(matrix.rows[0].label).toBe('Unresolved');
  });

  it('rows sort alphabetically by label', () => {
    const matrix = buildContainerRequestMatrix(
      [soLine({ item_code: 'ITEM-B' }), soLine({ item_code: 'ITEM-A' })],
      'product',
      'day',
    );
    expect(matrix.rows.map((r) => r.label)).toEqual(['ITEM-A', 'ITEM-B']);
  });
});

describe('buildContainerRequestMatrix - cells', () => {
  it('a cell sums the qty of every line landing on that row and bucket', () => {
    const matrix = buildContainerRequestMatrix(
      [
        soLine({ item_code: 'ITEM-1', required_date: '2026-08-17', qty: 10 }),
        soLine({ item_code: 'ITEM-1', required_date: '2026-08-19', qty: 5 }),
      ],
      'product',
      'week',
    );
    expect(matrix.cells).toHaveLength(1);
    expect(matrix.cells[0].qty).toBe(15);
    expect(matrix.cells[0].lines).toHaveLength(2);
  });

  it('a cell carries the exact lines behind it, for the drill popover', () => {
    const a = soLine({ so_number: 'SO-A', qty: 3 });
    const b = soLine({ so_number: 'SO-B', qty: 4 });
    const matrix = buildContainerRequestMatrix([a, b], 'product', 'week');
    expect(matrix.cells[0].lines).toEqual([a, b]);
  });

  it('rows and buckets with no line between them have no cell at all - a blank is not a zero', () => {
    const matrix = buildContainerRequestMatrix(
      [
        soLine({ item_code: 'ITEM-1', required_date: '2026-08-17' }),
        soLine({ item_code: 'ITEM-2', required_date: '2026-09-21' }),
      ],
      'product',
      'week',
    );
    expect(matrix.rows).toHaveLength(2);
    expect(matrix.buckets).toHaveLength(2);
    // 2 rows x 2 buckets = 4 possible cells; only the 2 that actually occurred exist.
    expect(matrix.cells).toHaveLength(2);
  });
});
