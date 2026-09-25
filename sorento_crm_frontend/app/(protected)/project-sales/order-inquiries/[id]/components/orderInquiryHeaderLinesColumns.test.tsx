/**
 * S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1): the Lines tab's own columns - Product,
 * Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Suggested, Location, Instruction,
 * State - with Taken/Remaining hideable through Columns like the rest of the grid. `SO line`
 * is S6 (AC-B6-1), also asserted here since it sits in this same list; its own href/label
 * behaviour is `orderInquiryWorklist.test.ts`'s and `orderInquiryWorklistColumns.test.tsx`'s.
 * `Suggested`, after SPO, is `PLAN-oi-links-autocount-truth-24sep.md` AC-LT-07 - reuses the
 * worklist's own `orderInquirySuggestedColumn()`.
 *
 * Column-order list updated at the #1119 x oi-request-cs-reserve merge (22 Sep, cross-lane):
 * main's own version of this assertion predates a column this lane already shipped in
 * Phase 1 - `Expand` (the board stock-grid chevron, `PLAN-oi-request-cs-reserve.md` 3.9)
 * sits FIRST, before Product. Real, shipped, not a merge artefact.
 *
 * Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G2, AC-RS-68): the round-2 `Reserve`
 * column this list used to end with is retired - the State cell itself is the reserve
 * click target now (`AC-RS-68` suite below), so the census here drops back to one column
 * per fact.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, renderHook, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getOrderInquiryPoDetail = vi.fn();
const getOrderInquirySpoDetail = vi.fn();

vi.mock('../../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoDetail: (...args: unknown[]) => getOrderInquiryPoDetail(...args),
    getOrderInquirySpoDetail: (...args: unknown[]) => getOrderInquirySpoDetail(...args),
  };
});

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function renderWithClient(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

function headerTitleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

describe('AC-B3-1: the Lines tab reads Product, Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State', () => {
  it('carries every named column, in order, after the select column', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const titles = result.current.map((column) => headerTitleOf(column)).filter(Boolean);

    expect(titles).toEqual([
      'Expand',
      'Product',
      'SO line',
      'Qty',
      'Taken',
      'Remaining',
      'Delivery date',
      'Supplier',
      'PO',
      'SPO',
      'Suggested',
      'Location',
      'Instruction',
      'State',
    ]);
  });

  it('Taken and Remaining are hideable through Columns, the same as the rest of the grid', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const taken = result.current.find((column) => headerTitleOf(column) === 'Taken') as
      | { enableHiding?: boolean }
      | undefined;
    const remaining = result.current.find((column) => headerTitleOf(column) === 'Remaining') as
      | { enableHiding?: boolean }
      | undefined;

    expect(taken).toBeDefined();
    expect(remaining).toBeDefined();
    // Only the select column opts out of hiding (`buildSelectColumn`'s own `enableHiding:
    // false`); Taken/Remaining carry no such flag, so they are hideable by the grid's
    // default the same way Supplier or Location already are.
    expect(taken?.enableHiding).not.toBe(false);
    expect(remaining?.enableHiding).not.toBe(false);
  });
});

function linesRow(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

/** Only the FOOTER row: the three sums are what this is about, and rendering the cells
 * would drag every per-cell dependency (documents dialog, state pill, links) into a test
 * that asserts none of them. */
function LinesFooter({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const columns = useOrderInquiryHeaderLinesColumns();
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <table>
      <tfoot>
        <tr>
          {table.getFooterGroups().flatMap((group) =>
            group.headers.map((header) => (
              <td key={header.id} data-testid={`footer-${header.column.id}`}>
                {header.column.columnDef.footer
                  ? flexRender(header.column.columnDef.footer, header.getContext())
                  : null}
              </td>
            )),
          )}
        </tr>
      </tfoot>
    </table>
  );
}

/**
 * AC-B3-4/AC-B3-5, review round 22 Sep (kill test): the Lines tab's OWN Qty footer had no
 * test of its own - only Taken/Remaining's shared footer did
 * (`orderInquiryWorklistColumns.test.tsx`) - so a Qty footer that summed EVERY loaded row
 * rather than the buy rows alone would have shipped green, printing a total that included
 * a notice row's quantity and a cancelled row's.
 */
describe('AC-B3-5: the Lines tab footers total the buy rows only', () => {
  it('excludes notice rows and cancelled rows from Qty, Taken and Remaining alike', () => {
    const buyRows = Array.from({ length: 10 }, (_unused, index) =>
      linesRow({ id: `buy-${index}`, qty: '10', linked_qty: '4' }),
    );
    render(
      <LinesFooter
        rows={[
          ...buyRows,
          // A notice row carries a quantity of its own and never a link: counted, it
          // would add 999 to Qty and 999 to Remaining.
          linesRow({ id: 'notice', verb: 'ADVANCE', qty: '999', linked_qty: '0' }),
          // A cancelled row is quantity the book called off: counted, it would add 500
          // to Qty and 250 to Taken.
          linesRow({
            id: 'cancelled',
            state: 'cancelled',
            qty: '500',
            linked_qty: '250',
          }),
        ]}
      />,
    );

    expect(screen.getByTestId('footer-qty')).toHaveTextContent(/^100$/);
    expect(screen.getByTestId('footer-taken')).toHaveTextContent(/^40$/);
    expect(screen.getByTestId('footer-remaining')).toHaveTextContent(/^60$/);
  });
});

/**
 * Round 4 (`PLAN-oi-request-cs-reserve.md` 6e) + AC-RS-83c (owner, 24 Sep: "this pen can
 * put right next to state?"): the State pill is plain text (never a button), and the
 * reserve icons render INSIDE the State cell to the right of it - no separate
 * `reserve_actions` column (saved column preferences appended an unknown id at the end,
 * after Location). Gated exactly as before: `canReserve` plus the line's reserve state.
 * `requested_qty` is cast onto the fixture: the local `linesRow` helper types only the
 * fields it sets.
 */
describe('AC-RS-83 / 83b / 83c: the reserve icons live inside the State cell', () => {
  function stateCell(
    row: OrderInquiryWorklistRow,
    options: Record<string, unknown> = {},
  ) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(stateColumn).toBeDefined();
    return stateColumn!.cell({ row: { original: row } });
  }

  const requestedRow = {
    ...linesRow({ id: 'row-req', state: 'raised', reserve_state: 'requested' }),
    requested_qty: '107',
  } as unknown as OrderInquiryWorklistRow;

  it('AC-RS-83c: no column carries id reserve_actions, with or without the permission', () => {
    for (const canReserve of [true, false]) {
      const { result } = renderHook(() =>
        useOrderInquiryHeaderLinesColumns({ canReserve } as never),
      );
      expect(
        result.current.some((column) => (column as { id?: string }).id === 'reserve_actions'),
      ).toBe(false);
    }
  });

  it('a requested row with the permission: pill text (not a button) + Reserve and Edit reserve in the same cell', () => {
    render(<>{stateCell(requestedRow, { canReserve: true })}</>);
    const pill = screen.getByText('Request to reserve 107');
    expect(pill.closest('button')).toBeNull();
    expect(screen.getByLabelText('Reserve')).toBeInTheDocument();
    expect(screen.getByLabelText('Edit reserve')).toBeInTheDocument();
  });

  it('AC-RS-83c: with the permission the State column starts at 380 wide with no minSize, so it can be narrowed back down', () => {
    const { result } = renderHook(() =>
      useOrderInquiryHeaderLinesColumns({ canReserve: true } as never),
    );
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { size?: number; minSize?: number };
    expect(stateColumn.size).toBe(380);
    expect(stateColumn.minSize).toBeUndefined();
  });

  it('without the permission: the pill only, no icons', () => {
    render(<>{stateCell(requestedRow, { canReserve: false })}</>);
    expect(screen.getByText('Request to reserve 107')).toBeInTheDocument();
    expect(screen.queryByLabelText('Reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
  });

  it('AC-RS-83b: a declined row reads Not reserved with Amend reserve + History beside it', () => {
    const declinedRow = linesRow({ id: 'row-decl', state: 'raised', reserve_state: 'declined' });
    render(<>{stateCell(declinedRow, { canReserve: true })}</>);
    expect(screen.getByText('Not reserved')).toBeInTheDocument();
    expect(screen.getByLabelText('Amend reserve')).toBeInTheDocument();
    expect(screen.getByLabelText('History')).toBeInTheDocument();
  });

  it('a line with no reserve state: the plain state pill, no icons', () => {
    render(<>{stateCell(linesRow({ id: 'row-plain', state: 'raised' }), { canReserve: true })}</>);
    expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amend reserve')).not.toBeInTheDocument();
  });

  it('a staged line shows the chip and Undo inside the State cell', () => {
    render(
      <>
        {stateCell(requestedRow, {
          canReserve: true,
          stagedByRowId: { 'row-req': { kind: 'reserve', qty: 107, locationLabel: 'BRW' } },
        })}
      </>,
    );
    expect(screen.getByText('Reserve 107 @ BRW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();
  });
});

/**
 * Issue #1215 point 5. Before this, the PO cell's own `firstLinkOf` read only
 * `link.kind === 'po'`, so a row whose ONLY link is an SPO carrying `source_po_number`
 * (`derived_po: true`) showed a bare dash here even though the worklist's own
 * `DocumentsCell`/`documentsOf` already printed the PO number "via SPO" for the exact
 * same row. Reusing `documentsOf` closes that gap without changing what counts as a
 * link - the underlying link is still SPO-kind, only the derived DISPLAY changes.
 */
describe('issue #1215 point 5: the PO cell reads "via SPO" for an SPO-only link naming its source PO', () => {
  function poCell(row: OrderInquiryWorklistRow) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const poColumn = result.current.find(
      (column) => (column as { id?: string }).id === 'po_number',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(poColumn).toBeDefined();
    return poColumn!.cell({ row: { original: row } });
  }

  it('prints the source PO number with a "via SPO" mark, not a dash', () => {
    const row = linesRow({
      id: 'row-spo-only',
      links: [
        {
          id: 'link-1',
          kind: 'spo',
          document: 'SPO-2026/09-0080',
          source_po_number: '202607-S0105',
          derived_po: true,
          qty: '6',
        },
      ],
    } as never);

    renderWithClient(<>{poCell(row)}</>);

    expect(screen.getByText('202607-S0105')).toBeInTheDocument();
    expect(screen.getByText(/via SPO/)).toBeInTheDocument();
    expect(screen.queryByText('-')).not.toBeInTheDocument();
  });

  it('still reads a plain dash when the row carries no link naming a PO at all', () => {
    const row = linesRow({ id: 'row-none', links: [] } as never);

    renderWithClient(<>{poCell(row)}</>);

    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('a real PO-kind link carries no "via" mark', () => {
    const row = linesRow({
      id: 'row-real-po',
      links: [{ id: 'link-2', kind: 'po', document: '202607-S0031', qty: '4' }],
    } as never);

    renderWithClient(<>{poCell(row)}</>);

    expect(screen.getByText('202607-S0031')).toBeInTheDocument();
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
  });
});

/**
 * R17 (owner rulings, 25 Sep 2026, hand test on stack C): "I also need here to be
 * clickable" - reversing review round 1's should-fix 4 plain-text fix. The via-SPO PO
 * cell opens the PO lightbox for the source PO, resolved by `purchase_order_id` when
 * the payload carries it, else by number.
 */
describe('R17: the via-SPO PO cell is clickable again', () => {
  function poCell(row: OrderInquiryWorklistRow) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const poColumn = result.current.find(
      (column) => (column as { id?: string }).id === 'po_number',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(poColumn).toBeDefined();
    return poColumn!.cell({ row: { original: row } });
  }

  it('opens the PO lightbox by purchase_order_id when the payload carries it, never a dead-lightbox message', async () => {
    getOrderInquiryPoDetail.mockResolvedValue({
      id: 'po-source-1',
      po_number: '202607-S0105',
      supplier_name: 'DAFUYUAN',
      status: 'confirmed',
      expected_date: '2026-09-01',
      lines: [],
      allocations: [],
    });
    const row = linesRow({
      id: 'row-spo-only',
      links: [
        {
          id: 'link-1',
          kind: 'spo',
          document: 'SPO-2026/09-0080',
          source_po_number: '202607-S0105',
          derived_po: true,
          purchase_order_id: 'po-source-1',
          qty: '6',
        },
      ],
    } as never);

    renderWithClient(<>{poCell(row)}</>);
    fireEvent.click(screen.getByTestId('document-detail-trigger-202607-S0105'));

    expect(await screen.findByText('DAFUYUAN')).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).toHaveBeenCalledWith('po-source-1');
    expect(
      screen.queryByText('This link does not reach a purchase order in the system.'),
    ).not.toBeInTheDocument();
  });

  it('Should fix 3 (review round 2): purchase_order_id is resolved on the SERVER now, never a client scan - a payload carrying none reads the same dead-lightbox message as any other unresolved PO', async () => {
    const row = linesRow({
      id: 'row-spo-only-no-id',
      links: [
        {
          id: 'link-2',
          kind: 'spo',
          document: 'SPO-2026/09-0081',
          source_po_number: '202607-S0105',
          derived_po: true,
          purchase_order_id: null,
          qty: '6',
        },
      ],
    } as never);

    renderWithClient(<>{poCell(row)}</>);
    fireEvent.click(screen.getByTestId('document-detail-trigger-202607-S0105'));

    expect(
      await screen.findByText('This link does not reach a purchase order in the system.'),
    ).toBeInTheDocument();
    expect(getOrderInquiryPoDetail).not.toHaveBeenCalled();
  });
});

/**
 * R15 (owner rulings, 25 Sep 2026, hand test on stack C): the SPO cell threads the
 * REAL link's `spo_allocation_id` through, so the SPO lightbox opened from the Lines
 * tab can highlight the exact line - the same identity the worklist's own
 * backing-documents dialog now carries.
 */
describe('R15: the SPO cell threads spo_allocation_id through', () => {
  function spoCell(row: OrderInquiryWorklistRow) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const spoColumn = result.current.find(
      (column) => (column as { id?: string }).id === 'spo_number',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(spoColumn).toBeDefined();
    return spoColumn!.cell({ row: { original: row } });
  }

  it('highlights the exact SPO line the real link names', async () => {
    getOrderInquirySpoDetail.mockResolvedValue({
      spo_number: 'SPO-2026/09-0051',
      supplier_name: 'CHAOSHENG',
      lines: [
        { id: 'spo-line-taken', sku: 'TPE-9204', allocated: '10', received: '0', remaining: '10' },
        { id: 'spo-line-other', sku: 'TPE-9204', allocated: '5', received: '0', remaining: '5' },
      ],
      allocations: [],
    });
    const row = linesRow({
      id: 'row-spo-real',
      links: [
        {
          id: 'link-3',
          kind: 'spo',
          document: 'SPO-2026/09-0051',
          spo_allocation_id: 'spo-line-taken',
          qty: '10',
        },
      ],
    } as never);

    renderWithClient(<>{spoCell(row)}</>);
    fireEvent.click(screen.getByTestId('document-detail-trigger-SPO-2026/09-0051'));

    const rows = (await screen.findAllByText('TPE-9204')).map(
      (cell) => cell.closest('tr') as HTMLElement,
    );
    expect(rows).toHaveLength(2);
    const takenRow = rows.find((r) => r.getAttribute('data-linked-line') === 'true');
    expect(takenRow).toBeTruthy();
    const otherRow = rows.find((r) => r !== takenRow);
    expect(otherRow).not.toHaveAttribute('data-linked-line');
  });
});
