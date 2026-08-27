'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { CircleCheck, CircleDashed, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { ackStateOf, isAcknowledgeable } from '../../_shared/lib/orderInquiryAck';
import { OrderInquiryAckCell } from './OrderInquiryAckCell';
import { OrderInquiryVerbPill } from '../../_shared/components/OrderInquiryVerbPill';
import { SupplyBar } from '../../_shared/components/SupplyBar';
import {
  KIND_COLOURS,
  KIND_LABELS,
  fullyLinked,
  segmentsOfRow,
} from '../../_shared/lib/orderInquiryKinds';
import {
  flowExclusionLabel,
  formatInquiryQty,
  linkedSummary,
  orderInquiryRowHref,
} from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import { OrderInquiryDocumentLink } from './OrderInquiryDocumentDialog';

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

/**
 * Is what this row shows a DRAFT or a real allocation (R1)?
 *
 * There is no state on the link: a link is a draft while its ROW is still to confirm, and
 * it is confirmed the moment purchasing stamps the row. One source of truth, read two
 * ways, so the mark and the Confirmed column can never disagree.
 */
function DraftMark({ row }: { row: OrderInquiryWorklistRow }) {
  const state = ackStateOf(row);
  // A refused row's links are gone; there is nothing to mark as anything.
  if (state === 'rejected') return null;
  if (state === 'acknowledged') {
    const who = row.acknowledged_by_name ?? 'Purchasing';
    const when = row.acknowledged_at ? ` ${formatDateInMalaysia(row.acknowledged_at)}` : '';
    const label = `Confirmed by ${who}${when}`;
    return (
      <span data-testid="link-confirmed-mark" title={label} aria-label={label}>
        <CircleCheck className="size-3.5 shrink-0 text-emerald-600" aria-hidden />
      </span>
    );
  }
  return (
    <span
      data-testid="link-draft-mark"
      title="Draft, confirm to allocate"
      aria-label="Draft, confirm to allocate"
    >
      <CircleDashed className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
    </span>
  );
}

/**
 * The worklist's columns, in the spreadsheet's own order (`JAN - DEC 2026 ORDER.xlsx`).
 *
 * Shared between the main list and the calendar's day drilldown, so a person reading
 * either sees the same columns in the same order rather than a second, looser table
 * invented for the calendar.
 */
export function useOrderInquiryWorklistColumns({
  selectable = false,
}: {
  /**
   * Draw the row checkboxes (AC-H2). Only where a bulk bar can act on them: the calendar
   * drilldown reuses these columns and has no Confirm press, so a tick there would
   * select rows nothing could be done with.
   */
  selectable?: boolean;
} = {}): ColumnDef<OrderInquiryWorklistRow>[] {
  return React.useMemo<ColumnDef<OrderInquiryWorklistRow>[]>(
    () => [
      ...(selectable
        ? [
            buildSelectColumn<OrderInquiryWorklistRow>({
              // Only a row that CAN be acknowledged is tickable: the bulk press takes on
              // awaiting and changed rows, and the server refuses the rest - so a box
              // that could be ticked on an acknowledged row would build a selection the
              // press then failed on whole.
              enableRow: (row) => isAcknowledgeable(row.original),
              disabledReason: (row) =>
                ackStateOf(row.original) === 'rejected'
                  ? 'Rejected rows go back to CS, not to purchasing'
                  : row.original.state === 'cancelled'
                    ? 'This instruction was called off'
                    : row.original.state === 'actioned'
                      ? 'This row has already been answered'
                      : 'Already acknowledged',
              rowLabel: (row) =>
                `Select ${row.original.item_code ?? 'row'} on ${row.original.so_number ?? 'this order'}`,
            }),
          ]
        : []),
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
        accessorKey: 'inquiry_no',
        header: ({ column }) => (
          <DataGridColumnHeader title="Order inquiry" column={column} />
        ),
        size: 130,
        meta: { headerTitle: 'Order inquiry', skeleton: <Skeleton className="h-4 w-20" /> },
        // Which instruction this row belongs to, by the number purchasing quotes. An
        // amendment raises a SECOND inquiry on the same sales order, so the S/O no beside
        // it cannot answer "which one was I told about".
        cell: ({ row }) =>
          row.original.inquiry_no ? (
            <span className="block truncate tabular-nums" title={row.original.inquiry_no}>
              {row.original.inquiry_no}
            </span>
          ) : (
            <Muted>Not numbered</Muted>
          ),
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
        // Blank means nobody has linked it yet, exactly as a blank cell does on their
        // sheet. Never filled in with a guess at who would supply it.
        cell: ({ row }) =>
          row.original.supplier ? (
            <span className="block truncate" title={row.original.supplier}>
              {row.original.supplier}
            </span>
          ) : (
            <Muted>Not linked</Muted>
          ),
      },
      {
        // WHERE the quantity sits (AC-D16/AC-D17). One row holds many links
        // (`projects.order_inquiry_links`), so the cell states the coverage first -
        // `8 of 8` - and then names each document with the LOCATION and quantity it
        // holds, which is the shape the buyer keys into AutoCount. Either kind of
        // document number opens the lightbox.
        //
        // The column id stays `po_number` even though the header no longer says PO: it
        // is what a saved column layout is keyed by, and renaming it would silently
        // exile the column to the right of everyone's grid.
        id: 'po_number',
        accessorFn: (row) => row.po_number ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Outstanding PO/SPO" column={column} />
        ),
        size: 280,
        meta: { headerTitle: 'Outstanding PO/SPO', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => {
          const summary = linkedSummary(
            row.original.qty,
            row.original.linked_qty,
            row.original.links,
          );
          // The same bar the schedule draws, off the same three kinds (AC-I14), so the
          // two views of this worklist cannot read differently: an unlinked row is a
          // faded rose bar over the words that say so (faded because nothing has been
          // committed to yet), a row linked 5 of 8 is sky over rose. No legend beside it
          // - the cards above the list carry the words.
          const bar = (
            <SupplyBar
              segments={segmentsOfRow(row.original)}
              decided={fullyLinked([row.original])}
              labels={KIND_LABELS}
              colours={KIND_COLOURS}
              className="mt-1 max-w-[120px]"
            />
          );
          if (!summary) {
            // Nothing in either book can cover this row, so it is a NEW order rather
            // than an oversight (AC-D2). "Not linked" read as a step somebody had
            // forgotten to take; the links are drafted the moment a row is raised now,
            // so an empty cell means the cascade looked and found nothing.
            return (
              <div className="min-w-0">
                <Muted>Not found (new order)</Muted>
                {bar}
              </div>
            );
          }
          return (
            <div className="min-w-0">
              <span className="flex min-w-0 items-center gap-1 text-xs font-medium tabular-nums">
                <DraftMark row={row.original} />
                <span className="truncate">{summary.headline}</span>
              </span>
              {bar}
              {summary.documents.map((entry) => {
                const link = (row.original.links ?? []).find(
                  (candidate) =>
                    candidate.document === entry.document && candidate.kind === entry.kind,
                );
                const lateWords =
                  entry.lateDays !== null
                    ? ` - lands ${entry.lateDays} day${entry.lateDays === 1 ? '' : 's'} after ${
                        row.original.delivery_date
                          ? formatDateInMalaysia(row.original.delivery_date)
                          : 'the required date'
                      }`
                    : entry.late
                      ? ' - arrives late'
                      : '';
                // The line label lives HERE and nowhere else (AC-D16): it names which
                // line of the document holds the quantity, which matters once the
                // document is open and never while the list is being scanned.
                const label = `${entry.document}: ${entry.partsTitle}${lateWords}`;
                return (
                  <span
                    key={`${entry.kind}-${entry.document}`}
                    className="flex min-w-0 items-center gap-1"
                    title={label}
                  >
                    <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                      {entry.kind}
                    </span>
                    <OrderInquiryDocumentLink
                      kind={entry.kind}
                      document={entry.document}
                      poId={link?.po_id}
                    />
                    <span className="truncate text-xs text-muted-foreground">
                      {entry.parts}
                    </span>
                    {/* AC-D17: it lands after this row needs it, and by how much. Said,
                        never acted on - nothing is unlinked for lateness. */}
                    {entry.late ? (
                      <span
                        data-testid={`link-late-${entry.document}`}
                        className="shrink-0 rounded-sm bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-800"
                      >
                        {entry.lateDays !== null ? `late ${entry.lateDays} d` : 'late'}
                      </span>
                    ) : null}
                  </span>
                );
              })}
            </div>
          );
        },
      },
      {
        accessorKey: 'taken_from_po',
        header: ({ column }) => (
          <DataGridColumnHeader title="Taken by PO/SPO" column={column} />
        ),
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Taken by PO/SPO', skeleton: <Skeleton className="h-4 w-14" /> },
        // What has actually been taken off a document for this row's own SO line - the
        // sum of every link on every ORDER / ORDER BACK row of that line, never this
        // row's own qty alone. A row whose OWN verb is neither (an ADVANCE/DELAY/...)
        // is not what this figure is about, and printing it anyway reads as "this
        // instruction is fully handled" next to one that is not placeable at all - so it
        // names what actually happened to ITS OWN row instead.
        cell: ({ row }) => {
          const excluded = flowExclusionLabel(row.original.verb);
          if (excluded) {
            return (
              <Muted>
                <span title="Only ORDER and ORDER BACK rows on this SO line count toward Taken by PO/SPO">
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
                <span title="Only ORDER and ORDER BACK rows on this SO line still flow to reorder planning">
                  {excluded}
                </span>
              </Muted>
            );
          }
          return (
            <span
              className="tabular-nums"
              title="What still flows to reorder planning: the unlinked remainder of this SO line\u2019s ORDER and ORDER BACK rows"
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
        // The verb is what purchasing DOES with the row: an ORDER and an ORDER BACK both
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
        // WHO pushed this to purchasing. Sorted server-side on the person's name, which
        // is why the column id is `raised_by_name` rather than `raised_by`: the id is
        // what the filter sends, the name is what this column is about.
        accessorKey: 'raised_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Raised by" column={column} />,
        size: 150,
        meta: { headerTitle: 'Raised by', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) =>
          row.original.raised_by_name ? (
            <span className="block truncate" title={row.original.raised_by_name}>
              {row.original.raised_by_name}
            </span>
          ) : (
            <Muted>Not recorded</Muted>
          ),
      },
      {
        // The TIME, not just the day: two revisions of the same order are raised hours
        // apart, and a date alone cannot tell them apart. Malaysian wall clock, from a
        // naive UTC stamp.
        accessorKey: 'raised_at',
        header: ({ column }) => <DataGridColumnHeader title="Raised at" column={column} />,
        size: 170,
        meta: { headerTitle: 'Raised at', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) =>
          row.original.raised_at ? (
            <span className="whitespace-nowrap">
              {formatDateTimeInMalaysia(row.original.raised_at)}
            </span>
          ) : (
            <Muted>Unknown</Muted>
          ),
      },
      {
        // The handshake, beside the supply state (AC-H2/AC-H5/AC-H8). Not sortable: the
        // server sorts a closed set of columns and this is not one of them, and a grid
        // drawing an arrow on a column the server ignored is a screen telling a lie.
        accessorKey: 'ack_state',
        header: ({ column }) => <DataGridColumnHeader title="Confirmed" column={column} />,
        size: 210,
        enableSorting: false,
        meta: { headerTitle: 'Confirmed', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => <OrderInquiryAckCell row={row.original} />,
      },
    ],
    [selectable],
  );
}
