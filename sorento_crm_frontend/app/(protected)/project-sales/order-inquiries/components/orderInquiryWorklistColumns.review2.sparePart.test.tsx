/**
 * SPARE-PART-ORDER-REQUEST review round 2 (browser pass 5), red-first (Phase 2).
 *
 * R10 UAC G1 (a line's description reaches purchasing): the Order Inquiries cross-order Lines
 *     view (the Lines toggle on the OI list, `useOrderInquiryWorklistColumns`) shows a spare part
 *     row's own `line_description` under the item code, not the product's name, the way the OI
 *     page's Lines tab already does (orderInquiryHeaderLinesColumns). A sales-order row, which
 *     has no line description, still shows its product name (guard).
 *
 * The Item code column's cell is rendered from the real column defs.
 */
import React from 'react';
import { cleanup, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => new URLSearchParams(''),
}));

import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

function worklistRow(over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    verb: 'REPLENISH',
    links: [],
    linked_qty: '0',
    item_code: 'SP-SEAL-40',
    product_name: 'Pump seal 40mm',
    ...over,
  } as unknown as OrderInquiryWorklistRow;
}

function renderItemCell(row: OrderInquiryWorklistRow) {
  const { result } = renderHook(() => useOrderInquiryWorklistColumns());
  const column = result.current.find(
    (c) => (c as { accessorKey?: string }).accessorKey === 'item_code',
  ) as { cell: (ctx: unknown) => React.ReactNode } | undefined;
  expect(column, 'the worklist has an Item code column').toBeTruthy();
  render(<>{column!.cell({ row: { original: row } })}</>);
}

beforeEach(() => cleanup());

describe('R10 (G1): the cross-order Lines view shows a spare part line its own description', () => {
  it("a spare part row shows its line_description, not the product's name", () => {
    renderItemCell(
      worklistRow({ inquiry_type: 'spare_part_request', line_description: 'Left seal, blue rubber' }),
    );
    expect(screen.getByText('SP-SEAL-40')).toBeInTheDocument();
    expect(screen.queryByText('Left seal, blue rubber'), 'the line description is shown').not.toBeNull();
    expect(screen.queryByText('Pump seal 40mm')).toBeNull();
  });

  it('a spare part row with no description falls back to the product name (guard)', () => {
    renderItemCell(worklistRow({ inquiry_type: 'spare_part_request', line_description: null }));
    expect(screen.getByText('Pump seal 40mm')).toBeInTheDocument();
  });

  it('a sales-order row still shows its product name (guard)', () => {
    renderItemCell(worklistRow({ inquiry_type: 'sales_order', line_description: null }));
    expect(screen.getByText('Pump seal 40mm')).toBeInTheDocument();
  });
});
