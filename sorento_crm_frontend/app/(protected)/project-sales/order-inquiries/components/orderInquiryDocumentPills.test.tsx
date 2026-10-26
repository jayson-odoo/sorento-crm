/**
 * LINKAGE-UNIFY U3 (AC-D1, AC-D3, AC-D4; PLAN section 9): the PO and SPO document cells of
 * the worklist AND the Lines tab draw the same pills off the same link entries.
 *
 *  - a PO chip never carries a "received" pill (owner note on mock v1);
 *  - an SPO chip carries "Received <qty> at <bin>" from `receipts` (L880: "Received 486 at
 *    BRW-BB");
 *  - class d (no SPO): the PO chip itself carries "Received <qty> at <bin>";
 *  - `dead_reason` prints "PO cancelled" / "SPO withdrawn".
 *
 * `receipts` and `dead_reason` are not on the app's link type yet; the fixtures cast.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/ui/tooltip', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui/tooltip')>(
    '@/components/ui/tooltip',
  );
  return {
    ...actual,
    TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import { useOrderInquiryHeaderLinesColumns } from '../[id]/components/orderInquiryHeaderLinesColumns';
import { foldInquiryLines, toLineRows } from '../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

type Link = Record<string, unknown>;

function rowWith(links: Link[]): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    core_line_id: 'cl-1',
    line_no: 1,
    verb: 'ORDER',
    state: 'placed',
    qty: '486',
    linked_qty: '486',
    reserved_qty: '0',
    bundled_qty: '0',
    item_code: 'SRTWT7202',
    links,
  } as unknown as OrderInquiryWorklistRow;
}

const PO_LINK: Link = {
  id: 'l-po', kind: 'po', document: '202607-S0083', po_id: 'po-1', po_line_id: 'pl-1',
  qty: '486', received: false, receipts: [], dead_reason: null,
};
const SPO_RECEIVED: Link = {
  id: 'derived-1', kind: 'spo', document: 'SPO-2026/09-0107', derived: true,
  source_po_number: '202607-S0083', qty: '486', received: true, received_qty: '486',
  receipts: [{ qty: '486', bin: 'BRW-BB' }], dead_reason: null,
};

type Where = 'worklist' | 'lines';

function cellOf(where: Where, columnId: 'po_number' | 'spo_number', row: OrderInquiryWorklistRow) {
  if (where === 'worklist') {
    const { result } = renderHook(() => useOrderInquiryWorklistColumns());
    const column = result.current.find(
      (c) => (c as { id?: string }).id === columnId,
    ) as { cell: (ctx: unknown) => React.ReactNode } | undefined;
    expect(column).toBeDefined();
    return column!.cell({ row: { original: row } });
  }
  const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
  const column = result.current.find(
    (c) => (c as { id?: string }).id === columnId,
  ) as { cell: (ctx: unknown) => React.ReactNode } | undefined;
  expect(column).toBeDefined();
  const [lineRow] = toLineRows(foldInquiryLines([row]));
  return column!.cell({ row: { original: lineRow } });
}

function show(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe.each<Where>(['worklist', 'lines'])('document pills on the %s', (where) => {
  it('seed: the PO chip names the document', () => {
    show(cellOf(where, 'po_number', rowWith([PO_LINK, SPO_RECEIVED])));
    expect(screen.getByText('202607-S0083')).toBeTruthy();
  });

  it('AC-D1: the PO chip carries no "received" pill, even with its SPO landed', () => {
    show(cellOf(where, 'po_number', rowWith([{ ...PO_LINK, received: true }, SPO_RECEIVED])));
    expect(screen.queryByText(/received/i)).toBeNull();
  });

  it('AC-D1: the SPO chip reads "Received 486 at BRW-BB" off the receipts', () => {
    show(cellOf(where, 'spo_number', rowWith([PO_LINK, SPO_RECEIVED])));
    expect(screen.getByText('SPO-2026/09-0107')).toBeTruthy();
    expect(screen.getByText('Received 486 at BRW-BB')).toBeTruthy();
  });

  it('AC-D1: an SPO still in transit has no received pill', () => {
    show(
      cellOf(
        where,
        'spo_number',
        rowWith([PO_LINK, { ...SPO_RECEIVED, received: false, receipts: [] }]),
      ),
    );
    expect(screen.queryByText(/received/i)).toBeNull();
  });

  it('AC-D1: class d, the PO chip itself reads "Received 50 at BRW-BB"', () => {
    show(
      cellOf(
        where,
        'po_number',
        rowWith([{ ...PO_LINK, qty: '50', received: true, receipts: [{ qty: '50', bin: 'BRW-BB' }] }]),
      ),
    );
    expect(screen.getByText('Received 50 at BRW-BB')).toBeTruthy();
  });

  it('AC-D3: a cancelled PO line says "PO cancelled" on the PO chip', () => {
    show(cellOf(where, 'po_number', rowWith([{ ...PO_LINK, dead_reason: 'po_cancelled' }])));
    expect(screen.getByText('PO cancelled')).toBeTruthy();
  });

  it('AC-D3: a withdrawn SPO says "SPO withdrawn" on the SPO chip', () => {
    show(
      cellOf(
        where,
        'spo_number',
        rowWith([
          {
            id: 'l-spo', kind: 'spo', document: 'SPO-2026/09-0200', qty: '50',
            spo_allocation_id: 'a-1', received: false, receipts: [], dead_reason: 'spo_withdrawn',
          },
        ]),
      ),
    );
    expect(screen.getByText('SPO withdrawn')).toBeTruthy();
  });
});
