'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { formatDateInMalaysia } from '@/lib/helpers';
import { OrderInquiryRowActions } from '../../_shared/components/OrderInquiryRowActions';
import {
  OrderInquiryStatePill,
  OrderInquiryVerbPill,
} from '../../_shared/components/OrderInquiryVerbPill';
import {
  flowExclusionLabel,
  formatInquiryQty,
  orderInquiryRowHref,
} from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import { OrderInquiryPoDetailPopover } from './OrderInquiryPoDetailPopover';

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

/**
 * The worklist's columns, in the spreadsheet's own order (`JAN - DEC 2026 ORDER.xlsx`).
 *
 * Shared between the main list and the calendar's day drilldown, so a person reading
 * either sees the same columns in the same order rather than a second, looser table
 * invented for the calendar.
 */
export function useOrderInquiryWorklistColumns(): ColumnDef<OrderInquiryWorklistRow>[] {
  return React.useMemo<ColumnDef<OrderInquiryWorklistRow>[]>(
    () => [
      {
        accessorKey: 'so_date',
        header: ({ column }) => <DataGridColumnHeader title="SO date" column={column} />,
        size: 120,
        meta: { headerTitle: 'SO date', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.so_date ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.so_date)}
            </span>
          ) : (
            <Muted>No date</Muted>
          ),
      },
      {
        accessorKey: 'so_number',
        header: ({ column }) => <DataGridColumnHeader title="S/O no" column={column} />,
        size: 150,
        meta: { headerTitle: 'S/O no', skeleton: <Skeleton className="h-4 w-20" /> },
        // The way in. An adopted row reaches the CORE sales order and an authored one its
        // project document; a row that can reach neither is plain text rather than a link
        // that answers 404.
        cell: ({ row }) => {
          const reference = row.original.so_number ?? 'Not numbered';
          const href = orderInquiryRowHref(row.original);
          if (!href)
            return (
              <span className="block truncate" title={reference}>
                {reference}
              </span>
            );
          return (
            <Link
              href={href}
              className="block truncate font-medium text-primary hover:underline"
              title={reference}
            >
              {reference}
            </Link>
          );
        },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        size: 180,
        meta: { headerTitle: 'Item code', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate font-medium" title={row.original.item_code ?? ''}>
              {row.original.item_code || <Muted>Unresolved</Muted>}
            </span>
            {/* Only when it says something the code does not: plenty of products are
                named after their own code, and printing it twice reads as a defect. */}
            {row.original.product_name &&
              row.original.product_name !== row.original.item_code && (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={row.original.product_name}
                >
                  {row.original.product_name}
                </span>
              )}
          </div>
        ),
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 90,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">{formatInquiryQty(row.original.qty)}</span>
        ),
      },
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Delivery date" column={column} />
        ),
        size: 140,
        meta: { headerTitle: 'Delivery date', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.delivery_date ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.delivery_date)}
            </span>
          ) : (
            <Muted>No date</Muted>
          ),
      },
      {
        accessorKey: 'project_customer',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project / customer" column={column} />
        ),
        size: 260,
        meta: {
          headerTitle: 'Project / customer',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
        cell: ({ row }) =>
          row.original.project_customer ? (
            <span className="block truncate" title={row.original.project_customer}>
              {row.original.project_customer}
            </span>
          ) : (
            <Muted>Not attributed</Muted>
          ),
      },
      {
        accessorKey: 'agent_code',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        size: 110,
        meta: { headerTitle: 'Agent', skeleton: <Skeleton className="h-4 w-14" /> },
        // Who sold it, off the core sales order. Blank when the row reaches no core order
        // or that order carries no agent - never a guess.
        cell: ({ row }) =>
          row.original.agent_code ? (
            <span
              className="block truncate"
              title={row.original.agent_label || row.original.agent_code}
            >
              {row.original.agent_code}
            </span>
          ) : (
            <Muted>Not assigned</Muted>
          ),
      },
      {
        accessorKey: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        size: 130,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-16" /> },
        // Where the PO gets placed for, not where the item is bought TO. Blank when
        // nobody has stamped a location and the line has no fulfilment warehouse either -
        // never a dash standing in for "unknown".
        cell: ({ row }) =>
          row.original.location ? (
            <span className="block truncate" title={row.original.location}>
              {row.original.location}
            </span>
          ) : null,
      },
      {
        accessorKey: 'supplier',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        size: 150,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-20" /> },
        // Blank means nobody has placed it yet, exactly as a blank cell does on their
        // sheet. Never filled in with a guess at who would supply it.
        cell: ({ row }) =>
          row.original.supplier ? (
            <span className="block truncate" title={row.original.supplier}>
              {row.original.supplier}
            </span>
          ) : (
            <Muted>Not placed</Muted>
          ),
      },
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO no" column={column} />,
        size: 150,
        meta: { headerTitle: 'PO no', skeleton: <Skeleton className="h-4 w-20" /> },
        // A placed row's PO number opens that purchase order's own header and every
        // line (the captain, 20 Aug) - a row nobody has placed has nothing to open.
        cell: ({ row }) =>
          row.original.po_number && row.original.po_id ? (
            <OrderInquiryPoDetailPopover
              poId={row.original.po_id}
              poNumber={row.original.po_number}
            />
          ) : row.original.po_number ? (
            <span className="block truncate tabular-nums" title={row.original.po_number}>
              {row.original.po_number}
            </span>
          ) : (
            <Muted>Not placed</Muted>
          ),
      },
      {
        accessorKey: 'taken_from_po',
        header: ({ column }) => <DataGridColumnHeader title="Taken from PO" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Taken from PO', skeleton: <Skeleton className="h-4 w-14" /> },
        // What has actually been taken off a purchase order for this row's own SO line -
        // the sum of every PLACED `ORDER`-verb sibling row, never this row's own qty
        // alone. A row whose OWN verb is not `ORDER` (an ADVANCE/DELAY/CANCEL BALANCE/...)
        // is not what this figure is about, and printing it anyway reads as "this
        // instruction is fully handled" next to one that is not placeable at all - so it
        // names what actually happened to ITS OWN row instead.
        cell: ({ row }) => {
          const excluded = flowExclusionLabel(row.original.verb);
          if (excluded) {
            return (
              <Muted>
                <span title="Only ORDER-verb rows on this SO line count toward Taken from PO">
                  {excluded}
                </span>
              </Muted>
            );
          }
          return (
            <span className="tabular-nums">
              {formatInquiryQty(row.original.taken_from_po ?? '0')}
            </span>
          );
        },
      },
      {
        accessorKey: 'remaining_open',
        header: ({ column }) => <DataGridColumnHeader title="Remaining" column={column} />,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Remaining', skeleton: <Skeleton className="h-4 w-14" /> },
        cell: ({ row }) => {
          const excluded = flowExclusionLabel(row.original.verb);
          if (excluded) {
            return (
              <Muted>
                <span title="Only ORDER-verb rows on this SO line still flow to reorder planning">
                  {excluded}
                </span>
              </Muted>
            );
          }
          return (
            <span
              className="tabular-nums"
              title="What still flows to reorder planning, counting ORDER-verb rows on this SO line only"
            >
              {formatInquiryQty(row.original.remaining_open ?? '0')}
            </span>
          );
        },
      },
      {
        accessorKey: 'verb',
        header: ({ column }) => <DataGridColumnHeader title="Instruction" column={column} />,
        size: 210,
        meta: { headerTitle: 'Instruction', skeleton: <Skeleton className="h-4 w-24" /> },
        // The verb is what purchasing DOES with the row: an ORDER and a BORROW SHORTFALL both
        // cost money, a CANCEL BALANCE takes it back, and the state alone tells them apart
        // from nothing. The server's own sentence ("Borrowed N for SOxxx line n; CODE goes
        // short by q") is the reasoning behind the verb, not the instruction itself, so it
        // moves behind the info icon rather than sitting inline under the pill.
        // Qty already has its own column; repeating it here duplicated the number rather
        // than adding to it.
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-1.5">
            <OrderInquiryVerbPill verb={row.original.verb} />
            {row.original.note && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    aria-label="Why this instruction"
                    className="size-5 shrink-0 text-muted-foreground"
                  >
                    <Info className="size-3.5" aria-hidden />
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs break-words">
                  {row.original.note}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        ),
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 120,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <OrderInquiryStatePill state={row.original.state} />,
      },
      {
        accessorKey: 'raised_at',
        header: ({ column }) => <DataGridColumnHeader title="Raised" column={column} />,
        size: 130,
        meta: { headerTitle: 'Raised', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.raised_at ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.raised_at)}
            </span>
          ) : (
            <Muted>Unknown</Muted>
          ),
      },
      {
        id: 'actions',
        header: 'Actions',
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => (
          <OrderInquiryRowActions
            rowId={row.original.id}
            verb={row.original.verb}
            state={row.original.state}
            itemCode={row.original.item_code}
            qty={row.original.qty}
            poLabel={row.original.po_number}
            hasOpenPoLine={row.original.has_open_po_line}
          />
        ),
      },
    ],
    [],
  );
}
