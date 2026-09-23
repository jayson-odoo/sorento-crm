'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Skeleton } from '@/components/ui/skeleton';
import { OrderInquiryStatePill, ReservePill } from '../../../_shared/components/OrderInquiryVerbPill';
import { OrderInquiryStockGrid } from '../../../_shared/components/OrderInquiryStockGrid';
import { formatInquiryQty, inquiryFooterTotals } from '../../../_shared/lib/orderInquiryWorklist';
import {
  DeliveryDateCell,
  InstructionCell,
  ItemCodeCell,
  LocationCell,
  orderInquirySoLineColumn,
  orderInquiryTakenRemainingColumns,
  QtyCell,
  SupplierCell,
} from '../../components/orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import { OrderInquiryDocumentLink } from '../../components/OrderInquiryDocumentDialog';

/**
 * The Lines tab's own columns (AC-DP-03): Expand, Product, SO line, Qty, Taken,
 * Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State. Taken/
 * Remaining are S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1); SO line is S6
 * (AC-B6-1). Product/Qty/Delivery date/Supplier/Location/Instruction reuse the
 * worklist's OWN cell renderers (`orderInquiryWorklistColumns.tsx`) so the same fact
 * reads the same way on both screens. PO/SPO are the ONE deliberate difference
 * (AC-DP-04): this single-header screen opens the simpler `OrderInquiryDocumentDialog`,
 * not the worklist's bundling/reallocate-aware `DocumentsCell` - a header's own lines
 * have no "which OTHER row is this bundled with" question to answer, since every row
 * here already belongs to the one document.
 *
 * Round 3 (section 6d G2, AC-RS-68): the separate `reserve` icon column round 2 added
 * is retired - the State cell itself carries the reserve state now (`ReservePill`
 * beside/instead of `OrderInquiryStatePill`), one fewer column on an already-wide grid.
 */

/** The first PO (or SPO) link this line carries, for a document trigger. `null` when the
 * line names none of that kind - the cell then reads a plain dash, same as the worklist. */
function firstLinkOf(row: OrderInquiryWorklistRow, kind: 'po' | 'spo') {
  return (row.links ?? []).find((link) => link.kind === kind) ?? null;
}

function DocumentCell({ row, kind }: { row: OrderInquiryWorklistRow; kind: 'po' | 'spo' }) {
  const link = firstLinkOf(row, kind);
  if (!link) return <span className="text-muted-foreground">-</span>;
  return (
    <OrderInquiryDocumentLink kind={kind} document={link.document} poId={link.po_id} />
  );
}

export function useOrderInquiryHeaderLinesColumns({
  onReserveClick,
}: {
  /** `PLAN-oi-request-cs-reserve.md` section 6c F2: opens `ReserveRowDialog` for this
   * row. Omitted -> the Reserve column renders nothing (a caller that never wires the
   * dialog gets no dead button). */
  onReserveClick?: (row: OrderInquiryWorklistRow) => void;
} = {}): ColumnDef<OrderInquiryWorklistRow>[] {
  return React.useMemo<ColumnDef<OrderInquiryWorklistRow>[]>(
    () => [
      // `PLAN-oi-request-cs-reserve.md` 3.9 (AC-RS-40): the board's own stock grid, a
      // chevron away - purchasing used to open the fulfilment board just to check BRW.
      {
        id: 'expand',
        header: () => <span className="sr-only">Expand</span>,
        cell: ({ row }) => (
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            className="size-6"
            aria-label={`${row.getIsExpanded() ? 'Hide' : 'Show'} stock for ${
              row.original.item_code ?? 'this line'
            }`}
            aria-expanded={row.getIsExpanded()}
            onClick={(event) => {
              event.stopPropagation();
              row.toggleExpanded();
            }}
          >
            {row.getIsExpanded() ? (
              <ChevronDown className="size-3.5" aria-hidden />
            ) : (
              <ChevronRight className="size-3.5" aria-hidden />
            )}
          </Button>
        ),
        size: 44,
        minSize: 44,
        enableSorting: false,
        enableResizing: false,
        enableHiding: false,
        meta: {
          headerTitle: 'Expand',
          expandedContent: (line: OrderInquiryWorklistRow) => (
            <div className="px-3 py-2">
              {line.product_id ? (
                <OrderInquiryStockGrid
                  productId={line.product_id}
                  location={line.location ?? null}
                />
              ) : (
                <p className="text-xs text-muted-foreground">
                  No product resolved for this line yet.
                </p>
              )}
            </div>
          ),
        },
      },
      buildSelectColumn<OrderInquiryWorklistRow>({
        rowLabel: (row) => `Select ${row.original.item_code ?? 'line'}`,
      }),
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        size: 220,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-32" /> },
        // AC-DP-03, owner ruling 21 Sep: code only, one line - never the second
        // `product_name` line the worklist's own cell prints for a real row.
        cell: ({ row }) => <ItemCodeCell row={row.original} codeOnly />,
      },
      // S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-1): the exact sales-order line this
      // row belongs to, linking straight there - the same shared column the worklist uses.
      orderInquirySoLineColumn(),
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 160,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => <QtyCell row={row.original} />,
        // AC-DP-03/AC-B3-5: a footer total under Qty, over the rows actually loaded (this
        // tab's whole set - Phase 1 and Phase 2 both hand this table every non-cancelled
        // line at once, so there is no server page this total could disagree with) - buy
        // rows only, the same gate Taken/Remaining's own footers read, so the three
        // numbers beside each other can never disagree about which rows they total.
        footer: ({ table }) => {
          const totals = inquiryFooterTotals(
            table.getPrePaginationRowModel().rows.map((r) => r.original),
          );
          return <span className="tabular-nums">{formatInquiryQty(String(totals.qty))}</span>;
        },
      },
      // S3 (AC-B3-1..5): Taken / Remaining, right after Qty - the same shared columns the
      // worklist uses (`orderInquiryWorklistColumns.tsx`), so the two screens read one row
      // the same way.
      ...orderInquiryTakenRemainingColumns(),
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        size: 140,
        meta: { headerTitle: 'Delivery date', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <DeliveryDateCell row={row.original} />,
      },
      {
        accessorKey: 'supplier',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        size: 170,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <SupplierCell row={row.original} />,
      },
      {
        id: 'po_number',
        accessorFn: (row) => firstLinkOf(row, 'po')?.document ?? '',
        header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
        size: 170,
        meta: { headerTitle: 'PO' },
        cell: ({ row }) => <DocumentCell row={row.original} kind="po" />,
      },
      {
        id: 'spo_number',
        accessorFn: (row) => firstLinkOf(row, 'spo')?.document ?? '',
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        size: 170,
        meta: { headerTitle: 'SPO' },
        cell: ({ row }) => <DocumentCell row={row.original} kind="spo" />,
      },
      {
        accessorKey: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        size: 130,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <LocationCell row={row.original} />,
      },
      {
        accessorKey: 'verb',
        header: ({ column }) => <DataGridColumnHeader title="Instruction" column={column} />,
        size: 200,
        meta: { headerTitle: 'Instruction', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => <InstructionCell row={row.original} />,
      },
      // `PLAN-oi-request-cs-reserve.md` section 6d G2 (AC-RS-68): the separate `reserve`
      // icon column (round 2's own artefact) is gone - the State cell itself is the
      // click target now, amber `Request to reserve` / green `Reserved N` with a tick
      // while an open request or an actual reserve exists on the row, the plain state
      // pill otherwise. `onReserveClick` absent -> `ReservePill` renders a read-only
      // span, same as the worklist's own usage beside Instruction.
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 190,
        meta: { headerTitle: 'State' },
        cell: ({ row }) => {
          const reserveState = row.original.reserve_state;
          if (reserveState === 'requested' || reserveState === 'reserved') {
            return (
              <ReservePill
                reserveState={reserveState}
                reservedQty={row.original.reserved_qty}
                onClick={
                  onReserveClick
                    ? (event) => {
                        // Nit (fix round 2): the row itself may carry its own click
                        // handler (a `rowHref` navigate) - the pill's own click must
                        // never also trigger it.
                        event.stopPropagation();
                        onReserveClick(row.original);
                      }
                    : undefined
                }
              />
            );
          }
          return <OrderInquiryStatePill state={row.original.state} />;
        },
      },
    ],
    [onReserveClick],
  );
}
