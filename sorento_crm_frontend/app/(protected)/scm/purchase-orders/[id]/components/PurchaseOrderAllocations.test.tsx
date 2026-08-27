/**
 * Allocated to - the PO occupancy panel (section 3.G, AC-G1/AC-G2).
 *
 * Four things this screen exists to say, and each is a test: the three figures per line, WHO
 * is waiting (by name, never by id), the "location differs" mark that IS the split
 * instruction the buyer re-keys in AutoCount, and the empty state - because a section that
 * hides itself on missing data is a code-review hard fail, and a buyer who sees nothing
 * cannot tell "nobody is waiting on this" from "the panel is broken".
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import { PurchaseOrderAllocations } from './PurchaseOrderAllocations';
import type { PurchaseOrderLineAllocation } from '../../../types/scm.types';

afterEach(cleanup);

/** PO-2026/07-0029 as the captain walked it: one DC1 line of 500, fully occupied. */
const DC1_LINE: PurchaseOrderLineAllocation = {
  line_id: 'line-1',
  sku: 'WESERP10B',
  warehouse_code: 'DC1',
  outstanding: 500,
  allocated: 500,
  free: 0,
  placements: [
    {
      inquiry_no: 'OI-000001',
      so_number: 'SO416191',
      customer: 'YOTU BUILDER SDN BHD',
      agent: 'JUSTIN',
      qty: 6,
      needed_at: 'BRW',
      location_differs: true,
    },
    {
      inquiry_no: 'OI-000006',
      so_number: 'SO324132',
      customer: 'BUIMACO / TUJU RESIDENCE',
      agent: 'CYNDI',
      qty: 487,
      needed_at: 'BRW-BB',
      location_differs: true,
    },
  ],
};

describe('PurchaseOrderAllocations', () => {
  it('states outstanding, allocated and free for the line', () => {
    render(<PurchaseOrderAllocations allocations={[DC1_LINE]} />);

    expect(screen.getByText('WESERP10B')).toBeTruthy();
    expect(screen.getByText('DC1')).toBeTruthy();
    // Three figures, because there are three questions and one number answers none of them.
    // Matched as "label then value" on ONE element: asserting the value alone would pass on
    // any 500 in the block, and "Allocated" alone also matches the card's own title.
    const figures = Array.from(document.querySelectorAll('span')).map((el) =>
      (el.textContent || '').replace(/\s+/g, ' ').trim(),
    );
    for (const expected of ['Outstanding 500', 'Allocated 500', 'Free 0']) {
      expect(figures).toContain(expected);
    }
  });

  it('names every placement by inquiry, order, customer and agent - never by id', () => {
    render(<PurchaseOrderAllocations allocations={[DC1_LINE]} />);

    expect(screen.getByText('OI-000001')).toBeTruthy();
    expect(screen.getByText('SO416191')).toBeTruthy();
    expect(screen.getByText('YOTU BUILDER SDN BHD')).toBeTruthy();
    expect(screen.getByText('JUSTIN')).toBeTruthy();
    expect(screen.getByText('487')).toBeTruthy();
    expect(screen.queryByText(/line-1/)).toBeNull();
  });

  it('marks a placement whose location is not the PO line own', () => {
    render(<PurchaseOrderAllocations allocations={[DC1_LINE]} />);
    // The mark is the split instruction, so it is on the row rather than hiding it.
    expect(screen.getAllByText('Location differs')).toHaveLength(2);
    expect(screen.getByText('BRW-BB')).toBeTruthy();
  });

  it('leaves a placement at the line own location unmarked', () => {
    render(
      <PurchaseOrderAllocations
        allocations={[
          {
            ...DC1_LINE,
            warehouse_code: 'BRW-BB',
            placements: [{ ...DC1_LINE.placements[1], location_differs: false }],
          },
        ]}
      />,
    );
    expect(screen.queryByText('Location differs')).toBeNull();
  });

  it('renders one block per line', () => {
    render(
      <PurchaseOrderAllocations
        allocations={[DC1_LINE, { ...DC1_LINE, line_id: 'line-2', sku: 'SRTWT2207' }]}
      />,
    );
    expect(screen.getByText('WESERP10B')).toBeTruthy();
    expect(screen.getByText('SRTWT2207')).toBeTruthy();
  });

  it('says so when nobody is waiting, rather than hiding the section', () => {
    render(<PurchaseOrderAllocations allocations={[]} />);

    expect(screen.getByText('Allocated to')).toBeTruthy();
    expect(
      screen.getByText(/No order inquiry is linked to this purchase order yet/i),
    ).toBeTruthy();
  });
});

describe('F7 - an SPO that pulled from this line', () => {
  /** The same DC1 line, its quantity taken by a CRM SPO rather than by an inquiry. */
  const withSpo: PurchaseOrderLineAllocation = {
    ...DC1_LINE,
    placements: [
      {
        kind: 'spo',
        spo_number: 'CRM-SPO-2026/08-0007',
        packing_list: 'FSCU8103365',
        qty: 500,
        warehouses: [
          { warehouse_code: 'BRW', qty: 300 },
          { warehouse_code: 'MWH', qty: 200 },
        ],
        arrival_date: '2026-09-14',
        inquiry_no: null,
        so_number: null,
        customer: null,
        agent: null,
        needed_at: null,
        location_differs: false,
      },
    ],
  };

  it('names the SPO and the container it is on (AC-G7)', () => {
    render(<PurchaseOrderAllocations allocations={[withSpo]} />);

    expect(screen.getByText('SPO')).toBeInTheDocument();
    expect(screen.getByText('CRM-SPO-2026/08-0007')).toBeInTheDocument();
    expect(screen.getByText('FSCU8103365')).toBeInTheDocument();
  });

  it('says where it is landing, and how much at each', () => {
    render(<PurchaseOrderAllocations allocations={[withSpo]} />);

    // The landings, then when the container is due beside them (AC-G7).
    expect(screen.getByText(/BRW 300, MWH 200 - due 2026-09-14/)).toBeInTheDocument();
  });

  it('leaves an order-inquiry placement reading exactly as it did', () => {
    render(<PurchaseOrderAllocations allocations={[DC1_LINE]} />);

    expect(screen.getByText('OI-000001')).toBeInTheDocument();
    expect(screen.getByText('SO416191')).toBeInTheDocument();
    expect(screen.queryByText('SPO')).not.toBeInTheDocument();
  });
});

describe('F7 - when the SPO take actually lands', () => {
  const withSpo: PurchaseOrderLineAllocation = {
    ...DC1_LINE,
    placements: [
      {
        kind: 'spo',
        spo_number: 'CRM-SPO-2026/08-0007',
        packing_list: 'FSCU8103365',
        qty: 500,
        warehouses: [{ warehouse_code: 'BRW', qty: 500 }],
        arrival_date: '2026-09-14',
        inquiry_no: null,
        so_number: null,
        customer: null,
        agent: null,
        needed_at: null,
        location_differs: false,
      },
    ],
  };

  it('states the arrival date beside where it lands (AC-G7)', () => {
    render(<PurchaseOrderAllocations allocations={[withSpo]} />);

    // The date used to be a FALLBACK for having no warehouse, so on a real take - which
    // always has one - it never appeared at all.
    expect(screen.getByText(/BRW 500/)).toBeInTheDocument();
    expect(screen.getByText(/2026-09-14|14\/09\/2026/)).toBeInTheDocument();
  });

  it('still says something when the container has no date yet', () => {
    render(
      <PurchaseOrderAllocations
        allocations={[{ ...withSpo, placements: [{ ...withSpo.placements[0], arrival_date: null }] }]}
      />,
    );

    expect(screen.getByText(/BRW 500/)).toBeInTheDocument();
  });
});
