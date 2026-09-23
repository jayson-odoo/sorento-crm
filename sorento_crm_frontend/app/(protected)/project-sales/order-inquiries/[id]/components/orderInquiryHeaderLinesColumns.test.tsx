/**
 * S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1): the Lines tab's own columns - Product,
 * Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State -
 * with Taken/Remaining hideable through Columns like the rest of the grid. `SO line` is S6
 * (AC-B6-1), also asserted here since it sits in this same list; its own href/label
 * behaviour is `orderInquiryWorklist.test.ts`'s and `orderInquiryWorklistColumns.test.tsx`'s.
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
import { fireEvent, render, renderHook, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';
import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

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
 * Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G2, AC-RS-68). The separate
 * `reserve` id column (see the `'Reserve'` title in the AC-B3-1 list above - a round-2
 * artefact this round retires) is deleted; the State cell itself becomes the click
 * target - amber `Request to reserve` / green `Reserved N` with a tick, both a button
 * named `Reserve`, and the plain `OrderInquiryStatePill` on every other row.
 *
 * `column.cell(...)` is called directly with a minimal `{ row: { original } }` context
 * - the same shape the real cell renderer destructures (`({ row }) => ...row.original`)
 * - rather than mounting a full react-table instance, the same trick
 * `useOrderInquiryHeaderLinesColumns` itself needs no table state to answer.
 */
describe('AC-RS-68: the State cell carries the reserve state; no separate Reserve column', () => {
  function stateColumnCell(
    row: OrderInquiryWorklistRow,
    onReserveClick?: (row: OrderInquiryWorklistRow) => void,
  ) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns({ onReserveClick }));
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(stateColumn).toBeDefined();
    return stateColumn!.cell({ row: { original: row } });
  }

  it('no column carries id "reserve" any more', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());

    expect(
      result.current.find((column) => (column as { id?: string }).id === 'reserve'),
    ).toBeUndefined();
  });

  it('a requested row: amber "Request to reserve" pill, a Reserve button, calling onReserveClick with the row', () => {
    const onReserveClick = vi.fn();
    const requestedRow = linesRow({
      id: 'row-req',
      state: 'raised',
      reserve_state: 'requested',
    });

    render(<>{stateColumnCell(requestedRow, onReserveClick)}</>);

    const button = screen.getByRole('button', { name: 'Reserve' });
    expect(button).toHaveTextContent('Request to reserve');
    fireEvent.click(button);
    expect(onReserveClick).toHaveBeenCalledWith(requestedRow);
  });

  it('a reserved row: green "Reserved N" pill with a Check tick, a Reserve button, calling onReserveClick with the row', () => {
    const onReserveClick = vi.fn();
    const reservedRow = linesRow({
      id: 'row-res',
      state: 'partly_linked',
      reserve_state: 'reserved',
      reserved_qty: '3',
    });

    const { container } = render(<>{stateColumnCell(reservedRow, onReserveClick)}</>);

    const button = screen.getByRole('button', { name: 'Reserve' });
    expect(button).toHaveTextContent('Reserved 3');
    expect(container.querySelector('svg.lucide-check')).toBeInTheDocument();
    fireEvent.click(button);
    expect(onReserveClick).toHaveBeenCalledWith(reservedRow);
  });

  it('a row with no reserve state: the plain OrderInquiryStatePill, no Reserve button', () => {
    const plainRow = linesRow({ id: 'row-plain', state: 'placed', reserve_state: null });

    render(<>{stateColumnCell(plainRow)}</>);

    expect(screen.queryByRole('button', { name: 'Reserve' })).not.toBeInTheDocument();
    expect(screen.getByText('On PO/SPO')).toBeInTheDocument();
  });

  /**
   * Nit (fix round 2): the Reserve pill sits inside a grid row that may carry its own
   * click handler (a `rowHref` navigate). Clicking Reserve must never also fire it.
   *
   * TEST-FIRST (fix round 2): today the call site's own `onClick` ignores the event
   * entirely (`() => onReserveClick(row.original)`) - a red here is "the wrapper's own
   * onClick fired too", never a fixture bug.
   */
  it('nit: clicking the Reserve pill stops the click reaching a wrapping row click handler', () => {
    const onReserveClick = vi.fn();
    const rowClick = vi.fn();
    const requestedRow = linesRow({
      id: 'row-req',
      state: 'raised',
      reserve_state: 'requested',
    });

    render(
      // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
      <div onClick={rowClick}>{stateColumnCell(requestedRow, onReserveClick)}</div>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reserve' }));

    expect(onReserveClick).toHaveBeenCalledWith(requestedRow);
    expect(rowClick).not.toHaveBeenCalled();
  });
});
