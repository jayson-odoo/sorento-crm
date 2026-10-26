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
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
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

const getOrderInquirySpoDetail = vi.fn();
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquirySpoDetail: (...args: unknown[]) => getOrderInquirySpoDetail(...args),
  };
});

import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import { useOrderInquiryHeaderLinesColumns } from '../[id]/components/orderInquiryHeaderLinesColumns';
import { foldInquiryLines, toLineRows } from '../../_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

type Link = Record<string, unknown>;

function rowWith(links: Link[], over: Record<string, unknown> = {}): OrderInquiryWorklistRow {
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
    ...over,
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


// ---------------------------------------------------------------------------- round 2

const SPO = 'SPO-2026/09-0107';
const L12_RECEIVED: Link = {
  id: 'l12', kind: 'spo', document: SPO, line_label: 'L12', spo_allocation_id: 'a-12',
  qty: '60', received: true, received_qty: '60', receipts: [{ qty: '60', bin: 'BRW-BB' }],
  dead_reason: null,
};
const L7_DEAD: Link = {
  id: 'l7', kind: 'spo', document: SPO, line_label: 'L7', spo_allocation_id: 'a-7',
  qty: '294', received: false, receipts: [], dead_reason: 'spo_withdrawn',
};

describe.each<Where>(['worklist', 'lines'])('F1 one chip per SPO line on the %s', (where) => {
  it('the visible chip is the live line with its receipt; the withdrawn line waits under +1', async () => {
    // The dead link is FIRST in the data: dead chips sort after live ones.
    show(cellOf(where, 'spo_number', rowWith([L7_DEAD, L12_RECEIVED])));
    expect(screen.getByText(SPO)).toBeTruthy();
    expect(screen.getByText('Received 60 at BRW-BB')).toBeTruthy();
    expect(screen.queryByText('SPO withdrawn')).toBeNull();

    fireEvent.click(screen.getByText('+1'));
    expect(await screen.findByText('SPO withdrawn')).toBeTruthy();
    expect(screen.getAllByText(/L7/).length).toBeGreaterThan(0);
  });
});

describe('F2 the Lines tab sums one SPO line across the SO line\'s OI rows', () => {
  it('L12 reads "Received 354 at BRW-BB" and L7 keeps its red pill under +1', async () => {
    const poLink: Link = {
      id: 'l-po', kind: 'po', document: '202607-S0100', po_id: 'po-1', po_line_id: 'pl-1',
      qty: '294', received: false, receipts: [], dead_reason: null,
    };
    const derived: Link = {
      id: 'derived-12', kind: 'spo', derived: true, document: SPO, line_label: 'L12',
      source_po_number: '202607-S0100', qty: '294', received: true,
      receipts: [{ qty: '294', bin: 'BRW-BB' }], dead_reason: null,
    };
    const rowA = rowWith([poLink, derived], { id: 'row-a' });
    const rowB = rowWith([L7_DEAD, L12_RECEIVED], { id: 'row-b', qty: '354' });
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const column = result.current.find(
      (c) => (c as { id?: string }).id === 'spo_number',
    ) as { cell: (ctx: unknown) => React.ReactNode };
    const [lineRow] = toLineRows(foldInquiryLines([rowA, rowB]));
    show(column.cell({ row: { original: lineRow } }));

    expect(screen.getByText('Received 354 at BRW-BB')).toBeTruthy();
    expect(screen.queryByText('SPO withdrawn')).toBeNull();
    fireEvent.click(screen.getByText('+1'));
    expect(await screen.findByText('SPO withdrawn')).toBeTruthy();
  });
});

describe.each<Where>(['worklist', 'lines'])('F3 and F4 receipts on one chip, on the %s', (where) => {
  it('F3: a real link and a derived entry on the same SPO line add up to one pill', () => {
    const real: Link = { ...L12_RECEIVED, receipts: [{ qty: '194', bin: 'B1' }] };
    const derived: Link = {
      ...L12_RECEIVED, id: 'derived-x', derived: true, receipts: [{ qty: '194', bin: 'B1' }],
    };
    show(cellOf(where, 'spo_number', rowWith([real, derived])));
    expect(screen.getByText('Received 388 at B1')).toBeTruthy();
    expect(screen.queryByText('+1')).toBeNull();
  });

  it('F4: several bins are several visible pills, never a hover-only +N', () => {
    const link: Link = {
      ...L12_RECEIVED,
      receipts: [{ qty: '30', bin: 'B1' }, { qty: '20', bin: 'B2' }],
    };
    show(cellOf(where, 'spo_number', rowWith([link])));
    expect(screen.getByText('Received 30 at B1')).toBeTruthy();
    expect(screen.getByText('Received 20 at B2')).toBeTruthy();
    expect(screen.queryByText(/^\+\d+$/)).toBeNull();
  });
});

describe('F5 the Lines tab receipt pill is clickable like the worklist\'s', () => {
  it('clicking "Received 60 at BRW-BB" opens the SPO document, as the document link does', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: SPO, supplier_name: 'S', lines: [], allocations: [],
    });
    show(cellOf('lines', 'spo_number', rowWith([L12_RECEIVED])));
    fireEvent.click(screen.getByText('Received 60 at BRW-BB'));
    await waitFor(() => expect(getOrderInquirySpoDetail).toHaveBeenCalled());
  });
});

// ---------------------------------------------------------------------------- round 3 (layout)
// jsdom has no layout, so these pin the structure that keeps the SPO number readable: a width
// floor on the number, pills that never shrink or truncate, and a column wide enough for
// number + "via PO" + "Received <qty> at <bin>" side by side.

const SPO_VIA_RECEIVED: Link = {
  id: 'derived-9', kind: 'spo', derived: true, document: SPO, line_label: 'L12',
  qty: '60', received: true, receipts: [{ qty: '60', bin: 'BRW-BB' }], dead_reason: null,
};

describe.each<Where>(['worklist', 'lines'])('R3 layout of the SPO cell on the %s', (where) => {
  it('(1) the SPO number never truncates: shrink-0, no truncate / max-w, title holds the full number', () => {
    // Owner ruling (26 Oct, #1870 hand test) SUPERSEDES the round-3 "min-width floor": the
    // number is the focus and never gives way; the receipt pill gives way first (R5 below).
    show(cellOf(where, 'spo_number', rowWith([SPO_VIA_RECEIVED])));
    const button = screen.getByText(SPO).closest('button') as HTMLElement;
    expect(button.getAttribute('title')).toContain(SPO);
    expect(button.className).toContain('shrink-0');
    expect(button.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis|(^|\s)max-w-/);
  });

  it('(2) the pills keep their full text: shrink-0 and no truncation class', () => {
    show(cellOf(where, 'spo_number', rowWith([SPO_VIA_RECEIVED])));
    // (The receipt pill is the one that gives way first now: see R5.)
    for (const text of ['via PO']) {
      const pill = screen.getByText(text);
      expect(pill.className).toContain('shrink-0');
      expect(pill.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis/);
    }
  });
});

describe('R3 the SPO column is wide enough on both tables', () => {
  function sizeOf(columns: unknown[]) {
    const column = columns.find((c) => (c as { id?: string }).id === 'spo_number') as
      | { size?: number }
      | undefined;
    expect(column).toBeDefined();
    return column!.size ?? 0;
  }

  it('(3) the worklist SPO column is at least 320 wide', () => {
    const { result } = renderHook(() => useOrderInquiryWorklistColumns());
    expect(sizeOf(result.current)).toBeGreaterThanOrEqual(320);
  });

  it('(3) the Lines tab SPO column is at least 320 wide', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    expect(sizeOf(result.current)).toBeGreaterThanOrEqual(320);
  });
});


/**
 * R4, as amended by the round-6 ruling (lead, from the owner's "if I resize, I still need to
 * see the number"): the SPO column may shrink to what still fits the full number + "via PO"
 * + the compact chip, so the chip is reachable. Measured: worklist number 124 px, Lines tab
 * number 143 px, "via PO" 52, chip 66, padding ~24. A saved narrower width clamps UP to that
 * table's own minimum, not to the old 320.
 */
describe('R4 the SPO column floor keeps the number, "via PO" and the compact chip', () => {
  const tables: Array<[string, () => unknown[], number, number]> = [
    ['worklist', () => useOrderInquiryWorklistColumns() as unknown[], 270, 300],
    ['lines', () => useOrderInquiryHeaderLinesColumns() as unknown[], 290, 320],
  ];

  it.each(tables)('(a) the %s SPO column minSize is within its range', (_n, build, low, high) => {
    const { result } = renderHook(build);
    const column = result.current.find((c) => (c as { id?: string }).id === 'spo_number') as {
      minSize?: number;
    };
    expect(column.minSize ?? 0).toBeGreaterThanOrEqual(low);
    expect(column.minSize ?? 0).toBeLessThanOrEqual(high);
  });

  it.each(tables)('(b) the %s table clamps a saved width of 170 up to its own minSize', (_n, build, low, high) => {
    const { result } = renderHook(() => {
      const columns = build();
      return useReactTable({
        data: [] as unknown[],
        columns: columns as never,
        getCoreRowModel: getCoreRowModel(),
        state: { columnSizing: { spo_number: 170 } },
      });
    });
    const size = result.current.getColumn('spo_number')!.getSize();
    expect(size).toBeGreaterThanOrEqual(low);
    expect(size).toBeLessThanOrEqual(high);
  });
});

// ---------------------------------------------------------------------------- round 5

function receiptPill() {
  return screen.getByText('Received 60 at BRW-BB');
}

describe.each<Where>(['worklist', 'lines'])('R5 the number leads, the receipt gives way, on the %s', (where) => {
  it('T1 a PO number never truncates either', () => {
    show(cellOf(where, 'po_number', rowWith([PO_LINK])));
    const button = screen.getByText('202607-S0083').closest('button') as HTMLElement;
    expect(button.getAttribute('title')).toContain('202607-S0083');
    expect(button.className).toContain('shrink-0');
    expect(button.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis|(^|\s)max-w-/);
  });

  it('T2 the receipt pill is quiet and gives way first', () => {
    show(cellOf(where, 'spo_number', rowWith([SPO_VIA_RECEIVED])));
    const pill = receiptPill();
    const classes = pill.className;
    expect(classes).toContain('truncate');
    expect(classes).toContain('min-w-0');
    expect(classes).toContain('text-2xs');
    expect(classes).toMatch(/(^|\s)px-1(\s|$)/);
    expect(classes).toContain('text-muted-foreground');
    expect(pill.getAttribute('title')).toBe('Received 60 at BRW-BB');
  });

  it('T3 a compact clickable fallback names the receipt and opens the same view as +N', async () => {
    show(cellOf(where, 'spo_number', rowWith([SPO_VIA_RECEIVED])));
    const fallback = document.querySelector(
      'button[aria-label*="Received 60 at BRW-BB"]',
    ) as HTMLElement | null;
    expect(fallback).not.toBeNull();
    fireEvent.click(fallback!);
    expect(await screen.findByRole('dialog')).toBeTruthy();
  });

  it('T4 container queries pick which one shows', () => {
    show(cellOf(where, 'spo_number', rowWith([SPO_VIA_RECEIVED])));
    const number = screen.getByText(SPO).closest('button') as HTMLElement;
    expect(number.closest('[class~="@container"]')).not.toBeNull();

    let hider: HTMLElement | null = receiptPill();
    let hides = false;
    while (hider && !hides) {
      hides = /(^|\s)@max-\[300px\]:hidden(\s|$)/.test(hider.className);
      hider = hider.parentElement;
    }
    expect(hides).toBe(true);

    const fallback = document.querySelector(
      'button[aria-label*="Received 60 at BRW-BB"]',
    ) as HTMLElement | null;
    expect(fallback).not.toBeNull();
    expect(fallback!.className).toMatch(/(^|\s)hidden(\s|$)/);
    expect(fallback!.className).toMatch(/@max-\[300px\]:(inline-flex|flex|inline-block|block)/);
  });
});
