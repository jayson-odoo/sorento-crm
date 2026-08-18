/**
 * The Phase 1 fixtures themselves.
 *
 * They are throwaway, so this file is too, but while they are what the captain clicks they have
 * to answer honestly: the worklist has to be ordered the way the contract promises, Start planning
 * has to be idempotent, and the one decision on show - the fulfilment location is the sales-order
 * LINE's own, and a line without one is named rather than defaulted - has to be visible in the
 * data and not just in the components that render it.
 */
import { describe, expect, it } from 'vitest';
import {
  mockAdopt,
  mockReconciliation,
  mockSupply,
  mockWorklist,
} from './fulfilmentPlanning.fixtures';

describe('mockWorklist', () => {
  it('carries both arms: unplanned core sales orders and an authored Project SO', () => {
    const { data } = mockWorklist({ limit: 100 });
    expect(data.some((row) => row.row_kind === 'sales_order')).toBe(true);
    expect(data.some((row) => row.row_kind === 'planning_record')).toBe(true);
  });

  it('is ordered by earliest required date, so the top of the list is the work that is due', () => {
    const dates = mockWorklist({ limit: 100 })
      .data.map((row) => row.earliest_required_date)
      .filter(Boolean) as string[];
    expect([...dates].sort()).toEqual(dates);
  });

  it('shows an unplanned order as Not started with no planning record invented for it', () => {
    const row = mockWorklist({ limit: 100 }).data.find((entry) => entry.so_number === 'SO391698');
    expect(row?.review_state).toBe('not_started');
    expect(row?.id).toBeNull();
    expect(row?.provisional_ref).toBeNull();
    expect(row?.status).toBeNull();
  });

  it('states the order that named no project as such, rather than defaulting one', () => {
    const row = mockWorklist({ limit: 100 }).data.find((entry) => entry.so_number === 'SO345418');
    expect(row?.project_label).toBeNull();
    expect(row?.customer_name).toBe('PEMBINAAN YUEN SENG SDN BHD (PROJECT)');
  });

  it('filters on the review state, including the new value', () => {
    const notStarted = mockWorklist({ limit: 100, review_state: 'not_started' }).data;
    expect(notStarted.length).toBeGreaterThan(0);
    expect(notStarted.every((row) => row.review_state === 'not_started')).toBe(true);

    const confirmed = mockWorklist({ limit: 100, review_state: 'confirmed' }).data;
    expect(confirmed.every((row) => row.review_state === 'confirmed')).toBe(true);
  });

  it('searches the sales-order number, the customer and the project string', () => {
    expect(mockWorklist({ query: 'SO346436' }).data).toHaveLength(1);
    expect(mockWorklist({ query: 'global ingress' }).data.length).toBeGreaterThan(0);
    expect(mockWorklist({ query: 'VISTA LAVENDAR' }).data.length).toBeGreaterThan(0);
    expect(mockWorklist({ query: 'nothing matches this' }).data).toHaveLength(0);
  });

  it('pages, and reports the total of the filtered set rather than of the page', () => {
    const page = mockWorklist({ page: 1, limit: 2 });
    expect(page.data).toHaveLength(2);
    expect(page.total).toBeGreaterThan(2);
  });
});

describe('mockAdopt', () => {
  it('answers with the record it created and moves the row off Not started', () => {
    const result = mockAdopt('so-346436');
    expect(result.so_number).toBe('SO346436');
    expect(result.already_adopted).toBe(false);
    expect(result.review_state).toBe('needs_cs_review');

    const row = mockWorklist({ limit: 100 }).data.find((entry) => entry.so_number === 'SO346436');
    expect(row?.review_state).toBe('needs_cs_review');
    expect(row?.id).toBe(result.project_sales_order_id);
    expect(row?.origin).toBe('adopted');
  });

  it('is idempotent: a second press answers with the same record, not a new one', () => {
    const first = mockAdopt('so-396071');
    const second = mockAdopt('so-396071');
    expect(second.project_sales_order_id).toBe(first.project_sales_order_id);
    expect(second.already_adopted).toBe(true);
  });

  it('refuses a sales order that is not in the list rather than inventing one', () => {
    expect(() => mockAdopt('so-does-not-exist')).toThrow();
  });
});

describe('mockReconciliation on an adopted order', () => {
  it('says there is nothing to compare against, and names the core sales order', () => {
    const summary = mockReconciliation('pso-adopted-368874');
    expect(summary.header.outcome).toBe('adopted');
    expect(summary.header.core_so_number).toBe('SO368874');
    expect(summary.header.reason).toContain('AutoCount sales-order book');
    expect(summary.exceptions).toHaveLength(0);
    expect(summary.lines_linked).toBe(summary.lines_total);
  });

  it('has no project registration, and does not invent one', () => {
    expect(mockReconciliation('pso-adopted-368874').project_id).toBeNull();
  });
});

describe('mockSupply', () => {
  it('plans every line against the line’s OWN fulfilment location', () => {
    const proposal = mockSupply('pso-adopted-368874');
    expect(proposal.lines.every((line) => line.fulfilment_location === 'BRW-IB')).toBe(true);
    expect(proposal.sales_order_number).toBe('SO368874');
    expect(proposal.sales_order_id).toBe('so-368874');
  });

  it('proposes a split that balances against the open quantity, on every line', () => {
    for (const line of mockSupply('pso-adopted-368874').lines) {
      const total = line.components.reduce(
        (sum, component) => sum + Number.parseFloat(component.qty),
        0,
      );
      expect(total).toBeCloseTo(Number.parseFloat(line.open_qty), 4);
    }
  });

  it('names the line’s location in the reason beside every quantity', () => {
    for (const line of mockSupply('pso-adopted-368874').lines) {
      expect(line.components.every((component) => component.reason.length > 0)).toBe(true);
    }
  });

  it('proposes NOTHING for a line whose sales order states no location', () => {
    const adopted = mockAdopt('so-366992');
    const proposal = mockSupply(adopted.project_sales_order_id);
    expect(proposal.lines.length).toBeGreaterThan(0);
    for (const line of proposal.lines) {
      expect(line.fulfilment_location_missing).toBe(true);
      expect(line.fulfilment_location).toBeNull();
      // No Reserve of zero dressed up as a plan, and above all no defaulted warehouse.
      expect(line.components).toHaveLength(0);
      expect(line.timely_spo).toHaveLength(0);
    }
  });

  it('reads a confirmed order back frozen, so the decision is shown rather than edited', () => {
    const proposal = mockSupply('pso-adopted-364368');
    expect(proposal.review_state).toBe('confirmed');
    expect(proposal.decision?.state).toBe('active');
    expect(proposal.lines.every((line) => line.frozen != null)).toBe(true);
  });
});
