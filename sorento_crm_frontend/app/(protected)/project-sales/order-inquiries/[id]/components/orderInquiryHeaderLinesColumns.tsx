'use client';

import * as React from 'react';
import { Check, ChevronDown, ChevronRight, History as HistoryIcon, Pencil } from 'lucide-react';
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
 * Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State, Reserve
 * actions. Taken/Remaining are S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1); SO
 * line is S6 (AC-B6-1). Product/Qty/Delivery date/Supplier/Location/Instruction reuse
 * the worklist's OWN cell renderers (`orderInquiryWorklistColumns.tsx`) so the same
 * fact reads the same way on both screens. PO/SPO are the ONE deliberate difference
 * (AC-DP-04): this single-header screen opens the simpler `OrderInquiryDocumentDialog`,
 * not the worklist's bundling/reallocate-aware `DocumentsCell` - a header's own lines
 * have no "which OTHER row is this bundled with" question to answer, since every row
 * here already belongs to the one document.
 *
 * Round 4 (`PLAN-oi-request-cs-reserve.md` section 6e.2, owner round 4, 24 Sep,
 * AC-RS-83): the State cell's own reserve pill is plain text again (round 3's
 * click-target button is retired) - the reserve icons render beside it in the same
 * cell (AC-RS-83c), gated by `canReserve` and driven by the
 * caller's own staged-decision map (`OrderInquiryDetail.tsx` owns that state; this
 * column is a pure renderer over it).
 */

/** One line's staged decision (6e.2) - not yet posted, held in `OrderInquiryDetail`'s
 * own `Record<rowId, StagedReserveEntry>` and cleared on commit or Undo. */
export interface StagedReserveEntry {
  kind: 'reserve' | 'amend';
  qty: number;
  /** Only meaningful for `kind: 'reserve'` - the chip's own "@ CODE" suffix
   * (AC-RS-84/85); an amend chip never names a location (its own is locked). */
  locationLabel?: string | null;
  warehouseId?: string | null;
  reason?: string | null;
}

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

function reserveChipText(staged: StagedReserveEntry): string {
  if (staged.kind === 'amend') return `Amend to ${staged.qty}`;
  // No location staged (the server defaults it): no dangling "@".
  if (staged.qty > 0 && staged.locationLabel) return `Reserve ${staged.qty} @ ${staged.locationLabel}`;
  return `Reserve ${staged.qty}`;
}

function ReserveActionsCell({
  row,
  staged,
  onTickReserve,
  onEditReserve,
  onAmendReserve,
  onHistoryClick,
  onUndoStaged,
}: {
  row: OrderInquiryWorklistRow;
  staged?: StagedReserveEntry;
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  onHistoryClick?: (row: OrderInquiryWorklistRow) => void;
  onUndoStaged?: (rowId: string) => void;
}) {
  if (staged) {
    const chipText = reserveChipText(staged);
    return (
      <div className="flex min-w-0 items-center gap-1.5">
        <span
          title={chipText}
          className="min-w-0 truncate rounded-full border border-dashed border-muted-foreground/50 px-2 py-0.5 text-xs text-muted-foreground"
        >
          {chipText}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-xs"
          onClick={() => onUndoStaged?.(row.id)}
        >
          Undo
        </Button>
      </div>
    );
  }
  if (row.reserve_state === 'requested') {
    return (
      <div className="flex items-center gap-1">
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="size-6"
          aria-label="Reserve"
          title="Reserve the full requested qty at the default pool"
          onClick={() => onTickReserve?.(row)}
        >
          <Check className="size-3.5" aria-hidden />
        </Button>
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="size-6"
          aria-label="Edit reserve"
          title="Edit reserve"
          onClick={() => onEditReserve?.(row)}
        >
          <Pencil className="size-3.5" aria-hidden />
        </Button>
      </div>
    );
  }
  // 6e.4 (AC-RS-83b): a declined line (CS answered 0) gets the same Amend + History
  // as a reserved one, so "0 -> up" stays reachable.
  if (row.reserve_state === 'reserved' || row.reserve_state === 'declined') {
    return (
      <div className="flex items-center gap-1">
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="size-6"
          aria-label="Amend reserve"
          title="Amend reserve"
          onClick={() => onAmendReserve?.(row)}
        >
          <Pencil className="size-3.5" aria-hidden />
        </Button>
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="size-6"
          aria-label="History"
          title="History"
          onClick={() => onHistoryClick?.(row)}
        >
          <HistoryIcon className="size-3.5" aria-hidden />
        </Button>
      </div>
    );
  }
  return null;
}

export function useOrderInquiryHeaderLinesColumns({
  canReserve,
  stagedByRowId,
  onTickReserve,
  onEditReserve,
  onAmendReserve,
  onHistoryClick,
  onUndoStaged,
}: {
  /** AC-RS-83/83c: gates the reserve icons inside the State cell - a viewer without
   * `projects.order_inquiries.reserve` sees the pills only. */
  canReserve?: boolean;
  /** 6e.2: this line's own staged (not yet committed) decision, keyed by row id -
   * `OrderInquiryDetail.tsx` owns the map, this column only renders over it. */
  stagedByRowId?: Record<string, StagedReserveEntry>;
  /** AC-RS-84: the tick - stages the full requested qty at the default pool, no dialog. */
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-RS-85: the pencil on a requested line - opens `ReserveLineForm` in reserve mode. */
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-RS-86: the pencil on a reserved line - opens `ReserveLineForm` in amend mode. */
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-RS-89: opens `ReserveLineHistoryDialog` for this row. */
  onHistoryClick?: (row: OrderInquiryWorklistRow) => void;
  /** Drops a staged decision, restoring the two icons. */
  onUndoStaged?: (rowId: string) => void;
} = {}): ColumnDef<OrderInquiryWorklistRow>[] {
  return React.useMemo<ColumnDef<OrderInquiryWorklistRow>[]>(() => {
    const columns: ColumnDef<OrderInquiryWorklistRow>[] = [
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
      // `PLAN-oi-request-cs-reserve.md` 6e.2 (AC-RS-83): the pill is plain text.
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        // AC-RS-83c (owner, 24 Sep: "this pen can put right next to state?"): the
        // reserve icons sit in this cell, right of the pill - no separate column, which
        // saved column preferences appended after Location. Wide enough for the pill
        // plus a staged chip and Undo. No `minSize`: a user who drags it narrower than
        // the icons is choosing that, and can drag it back out again (owner, 24 Sep).
        size: canReserve ? 380 : 190,
        meta: { headerTitle: 'State' },
        cell: ({ row }) => {
          const reserveState = row.original.reserve_state;
          const pill =
            reserveState === 'requested' ||
            reserveState === 'reserved' ||
            reserveState === 'declined' ? (
              <ReservePill
                reserveState={reserveState}
                reservedQty={row.original.reserved_qty}
                requestedQty={row.original.requested_qty}
              />
            ) : (
              <OrderInquiryStatePill state={row.original.state} />
            );
          if (!canReserve) return pill;
          return (
            <div className="flex min-w-0 items-center gap-1">
              <span className="shrink-0">{pill}</span>
              <ReserveActionsCell
                row={row.original}
                staged={stagedByRowId?.[row.original.id]}
                onTickReserve={onTickReserve}
                onEditReserve={onEditReserve}
                onAmendReserve={onAmendReserve}
                onHistoryClick={onHistoryClick}
                onUndoStaged={onUndoStaged}
              />
            </div>
          );
        },
      },
    ];

    return columns;
  }, [
    canReserve,
    stagedByRowId,
    onTickReserve,
    onEditReserve,
    onAmendReserve,
    onHistoryClick,
    onUndoStaged,
  ]);
}
