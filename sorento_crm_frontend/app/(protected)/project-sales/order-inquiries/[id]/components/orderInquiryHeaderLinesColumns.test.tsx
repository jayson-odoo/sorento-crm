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
import { cleanup, render, renderHook, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
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
 * Round 3's own AC-RS-68 suite ("the State cell carries the reserve state; no
 * separate Reserve column", a `role=button` pill calling `onReserveClick`) is
 * RETIRED here, superseded by AC-RS-83 directly below: round 4
 * (`PLAN-oi-request-cs-reserve.md` section 6e.2, owner round 4, 24 Sep) makes the
 * pill plain text and moves the click target to its own `reserve_actions` icon
 * column - `onReserveClick`/`role=button` no longer describe this cell at all.
 */

/**
 * Round 4 (`PLAN-oi-request-cs-reserve.md` section 6e, `oi-request-cs-reserve-
 * acceptance-criteria.md` AC-RS-83). Supersedes the AC-RS-68 suite above: the State
 * pill is no longer a button at all (plan 6e.2, "The pill is no longer a button"),
 * and the reserve action moves to its own `reserve_actions` column of icon buttons,
 * gated by a NEW `canReserve` option the hook does not accept yet.
 *
 * Field-name note for the captain (same one `OrderInquiryDetail.reserveStaging.test
 * .tsx` carries): the worklist row type has no field today for "the open request's
 * own requested qty on this row" - this suite invents `requested_qty` on the row
 * fixture for it, cast through `Record<string, unknown>` since the real
 * `OrderInquiryWorklistRow` type does not declare it.
 *
 * TEST-FIRST (Phase 2): today `useOrderInquiryHeaderLinesColumns` accepts no
 * `canReserve` option, the State cell's `reserve_state requested` branch renders
 * `ReservePill` as a `role=button` with plain text "Request to reserve" (no qty), and
 * no column carries id `reserve_actions` - a red here is exactly those gaps, never a
 * fixture bug.
 */
describe('AC-RS-83 (round 4): the State cell prints the requested qty as TEXT, not a button; a separate reserve_actions column carries the icons', () => {
  function stateColumnCell(
    row: OrderInquiryWorklistRow,
    options: { onReserveClick?: (row: OrderInquiryWorklistRow) => void; canReserve?: boolean } = {},
  ) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(stateColumn).toBeDefined();
    return stateColumn!.cell({ row: { original: row } });
  }

  it('a requested row: the State cell reads "Request to reserve 107" as plain text, not a button', () => {
    const requestedRow = {
      ...linesRow({ id: 'row-req', state: 'raised', reserve_state: 'requested' }),
      requested_qty: '107',
    } as unknown as OrderInquiryWorklistRow;

    render(<>{stateColumnCell(requestedRow, { canReserve: true })}</>);

    expect(screen.getByText('Request to reserve 107')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reserve/i })).not.toBeInTheDocument();
  });

  it('a reserve_actions column exists and renders the icon buttons only when canReserve is true', () => {
    const requestedRow = {
      ...linesRow({ id: 'row-req', state: 'raised', reserve_state: 'requested' }),
      requested_qty: '107',
    } as unknown as OrderInquiryWorklistRow;

    const { result: withPermission } = renderHook(() =>
      useOrderInquiryHeaderLinesColumns({ canReserve: true } as never),
    );
    const actionsColumnWith = withPermission.current.find(
      (column) => (column as { id?: string }).id === 'reserve_actions',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(actionsColumnWith).toBeDefined();

    render(<>{actionsColumnWith!.cell({ row: { original: requestedRow } })}</>);
    expect(screen.getByLabelText('Edit reserve')).toBeInTheDocument();

    cleanup();

    const { result: withoutPermission } = renderHook(() =>
      useOrderInquiryHeaderLinesColumns({ canReserve: false } as never),
    );
    const actionsColumnWithout = withoutPermission.current.find(
      (column) => (column as { id?: string }).id === 'reserve_actions',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    if (actionsColumnWithout) {
      render(<>{actionsColumnWithout.cell({ row: { original: requestedRow } })}</>);
      expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
    }
  });
});
