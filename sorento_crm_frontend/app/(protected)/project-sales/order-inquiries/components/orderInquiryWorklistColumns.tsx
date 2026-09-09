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
import {
  ackStateOf,
  isBulkRejectable,
  previousValueOf,
} from '../../_shared/lib/orderInquiryAck';
import { OrderInquiryVerbPill } from '../../_shared/components/OrderInquiryVerbPill';
import {
  bundledHeadline,
  flowExclusionLabel,
  formatInquiryQty,
  linkedSummary,
  orderInquiryRowHref,
} from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import { OrderInquiryBackingDocumentsDialog } from './OrderInquiryBackingDocumentsDialog';
import { OrderInquiryQtyAnnotationDialog } from './OrderInquiryQtyAnnotationDialog';

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

/**
 * Is what this row shows firm, or still a row nobody has acknowledged (S1: essentially
 * never, since a row is born acknowledged - this reads a legacy `awaiting`/`changed` row
 * only, kept honest rather than assumed away)?
 *
 * There is no state on the link: a link is firm the moment its row reads `acknowledged`.
 * One source of truth, read two ways, so this mark can never disagree with the row itself.
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
    <span data-testid="link-draft-mark" title="Proposed" aria-label="Proposed">
      <CircleDashed className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
    </span>
  );
}

/**
 * The "Outstanding PO/SPO" cell's own info icon (AC-A5): opens
 * `OrderInquiryBackingDocumentsDialog`, mounted only once asked for so a page of a hundred
 * rows does not carry a hundred dialogs - the same pattern `OrderInquiryDocumentLink` uses.
 */
function BackingDocumentsButton({ row }: { row: OrderInquiryWorklistRow }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        data-testid={`backing-documents-trigger-${row.id}`}
        aria-label={`Show documents backing ${row.item_code ?? row.so_number ?? 'this row'}`}
        className="size-5 shrink-0 text-muted-foreground"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <Info className="size-3.5" aria-hidden />
      </Button>
      {open ? (
        <OrderInquiryBackingDocumentsDialog row={row} open onOpenChange={setOpen} />
      ) : null}
    </>
  );
}

/**
 * The "Outstanding PO/SPO" cell's info icon for a BUNDLED row (UAC D1-D3, D10;
 * PLAN-scm-supplied-with-companions.md section 3.4).
 *
 * A row that rides ENTIRELY inside the item(s) it is bundled with has no backing
 * documents of its own - the icon opens the ANCHOR row's own lightbox instead ("the
 * info icon opens the HOST row's lightbox", never named that in the UI). A row that is
 * only PART bundled keeps its own lightbox (its own links back the ala carte
 * remainder), with a leading entry naming what the rest rides with.
 */
function BundledDocumentsButton({
  row,
  anchorRow,
  fullyBundled,
}: {
  row: OrderInquiryWorklistRow;
  anchorRow: OrderInquiryWorklistRow | null;
  fullyBundled: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const bundled = row.bundled_with;
  if (!bundled) return null;
  const itemCodes = bundled.item_codes.length ? bundled.item_codes : [bundled.item_code];
  const dialogRow = fullyBundled ? (anchorRow ?? row) : row;
  return (
    <>
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        data-testid={`backing-documents-trigger-${row.id}`}
        aria-label={`Show documents backing ${row.item_code ?? row.so_number ?? 'this row'}`}
        className="size-5 shrink-0 text-muted-foreground"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <Info className="size-3.5" aria-hidden />
      </Button>
      {open ? (
        <OrderInquiryBackingDocumentsDialog
          row={dialogRow}
          open
          onOpenChange={setOpen}
          bundleNote={
            fullyBundled
              ? { itemCodes, fullyBundled: true }
              : { itemCodes, fullyBundled: false, qty: row.bundled_qty ?? '0' }
          }
        />
      ) : null}
    </>
  );
}

/**
 * The Qty cell's own info icon (owner's 9 Sep feedback, live look at the running lane):
 * the same one-line defect slice A fixed for the Outstanding column also sat here - a
 * rejected row's reason or a changed row's Was/Now table rendered as a second line, so
 * those rows read taller than every other one. Rendered ONLY when the row actually has
 * something to say (a rejection, a change stamp, or both); a plain acknowledged row shows
 * the quantity alone.
 *
 * The two states stay distinguishable at a glance without adding words to the cell: a
 * REJECTED row's icon reads as a warning (the design system's own warning token, matching
 * `Badge variant="warning"` elsewhere on this screen) because it is the one that needs
 * purchasing to look again; a row that only carries a change stamp reads muted, the same
 * colour every other icon-only trigger on this list uses, because it is informational.
 * Both facts win the warning colour when both apply - a rejection is the more urgent of
 * the two.
 */
function QtyAnnotationButton({ row }: { row: OrderInquiryWorklistRow }) {
  const [open, setOpen] = React.useState(false);
  const rejected = ackStateOf(row) === 'rejected';
  const changed = Boolean(previousValueOf(row));
  if (!rejected && !changed) return null;
  const label = rejected
    ? `Show why ${row.item_code ?? row.so_number ?? 'this row'} was rejected`
    : `Show what changed on ${row.item_code ?? row.so_number ?? 'this row'}`;
  return (
    <>
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        data-testid={`qty-annotation-trigger-${row.id}`}
        aria-label={label}
        className={`size-5 shrink-0 ${
          rejected
            ? 'text-[var(--color-warning-accent,var(--color-yellow-700))]'
            : 'text-muted-foreground'
        }`}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <Info className="size-3.5" aria-hidden />
      </Button>
      {open ? (
        <OrderInquiryQtyAnnotationDialog row={row} open onOpenChange={setOpen} />
      ) : null}
    </>
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
              // Only a row Reject may still take is tickable now (S1): every row is born
              // acknowledged, so there is no Confirm press left for the tick to feed, and
              // Reject is the last remaining bulk action gated on the row's own state.
              enableRow: (row) => isBulkRejectable(row.original),
              disabledReason: (row) =>
                ackStateOf(row.original) === 'rejected'
                  ? 'Rejected rows go back to CS, not to purchasing'
                  : row.original.state === 'cancelled'
                    ? 'This instruction was called off'
                    : row.original.state === 'actioned'
                      ? 'This row has already been answered'
                      : 'Nothing left to act on',
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
        // Qty carries the handshake now (S1, AC-1.5): a rejection and its reason, or a
        // settle-in-place and its Was/Now, are the two facts that still matter to a buyer
        // scanning the row. ONE LINE (AC-A8, owner's 9 Sep feedback against the running
        // lane - the same defect slice A fixed for the Outstanding column): the quantity,
        // and an info icon only when there is something to say. A row that is simply
        // acknowledged (the ordinary case) shows the number and nothing else.
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 150,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1 tabular-nums">
            {formatInquiryQty(row.original.qty)}
            <QtyAnnotationButton row={row.original} />
          </span>
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
        // WHERE the quantity sits (AC-A1..AC-A7, owner's 8 Sep cut of the mock). The cell
        // is ONE LINE: the draft/confirmed mark, the coverage headline - `115 of 493` -
        // and, when there is something to explain, an info icon that opens
        // `OrderInquiryBackingDocumentsDialog`. No SupplyBar (a proportion of a number the
        // cell already prints in full), no document number, no count and no lateness -
        // every one of those moved behind the icon or off the cell entirely.
        //
        // The column id stays `po_number` even though the header no longer says PO: it
        // is what a saved column layout is keyed by, and renaming it would silently
        // exile the column to the right of everyone's grid.
        id: 'po_number',
        accessorFn: (row) => row.po_number ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Outstanding PO/SPO" column={column} />
        ),
        size: 220,
        meta: { headerTitle: 'Outstanding PO/SPO', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row, table }) => {
          const bundled = row.original.bundled_with;
          const bundledQty = Number(row.original.bundled_qty ?? '0');
          if (bundled && Number.isFinite(bundledQty) && bundledQty > 0) {
            const headline = bundledHeadline(row.original);
            if (headline) {
              // The FULL anchor row, for the info icon's own lightbox only (it needs
              // the anchor's real documents, not just its headline) - the headline text
              // above never depends on this: it comes straight off `bundled.anchor_headline`,
              // resolved server-side. `table.options.data` is the loaded rows, never a
              // second fetch; a page that does not happen to hold the anchor falls back
              // to the row's own lightbox (`dialogRow` inside `BundledDocumentsButton`).
              const rows = table.options.data as OrderInquiryWorklistRow[];
              const anchorRow = rows.find((r) => r.id === bundled.row_id) ?? null;
              const qty = Number(row.original.qty ?? '0');
              const fullyBundled = qty - bundledQty <= 0;
              return (
                <span className="flex min-w-0 items-center gap-1 text-xs font-medium tabular-nums">
                  <DraftMark row={row.original} />
                  <span className="truncate" title={headline}>
                    {headline}
                  </span>
                  <BundledDocumentsButton
                    row={row.original}
                    anchorRow={anchorRow}
                    fullyBundled={fullyBundled}
                  />
                </span>
              );
            }
          }
          const summary = linkedSummary(
            row.original.qty,
            row.original.linked_qty,
            row.original.links,
          );
          if (!summary) {
            // Nothing in either book can cover this row, so it is a NEW order rather
            // than an oversight (AC-A7). "Not linked" read as a step somebody had
            // forgotten to take; the links are drafted the moment a row is raised now,
            // so an empty cell means the cascade looked and found nothing. No icon: there
            // is nothing behind it to open.
            return (
              <div className="min-w-0">
                <Muted>Not found (new order)</Muted>
              </div>
            );
          }
          return (
            <span className="flex min-w-0 items-center gap-1 text-xs font-medium tabular-nums">
              <DraftMark row={row.original} />
              <span className="truncate" title={summary.headline}>
                {summary.headline}
              </span>
              <BackingDocumentsButton row={row.original} />
            </span>
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
      // No Confirmed column (S1, AC-1.5): there is no manual confirm left to report on,
      // and the two facts that column existed to carry - a rejection and a settle-in-place
      // Was/Now - render in the qty cell above instead.
    ],
    [selectable],
  );
}
