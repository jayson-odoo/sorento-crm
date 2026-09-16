'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { CircleCheck, CircleDashed, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { ackStateOf, movedNoteOf, previousValueOf } from '../../_shared/lib/orderInquiryAck';
import { OrderInquiryVerbPill } from '../../_shared/components/OrderInquiryVerbPill';
import {
  bundledHeadline,
  flowExclusionLabel,
  formatInquiryQty,
  orderInquiryRowHref,
} from '../../_shared/lib/orderInquiryWorklist';
import type {
  OrderInquiryLinkSuggestion,
  OrderInquiryWorklistRow,
} from '../../_shared/types/orderInquiry.types';
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
 * The distinct document NUMBERS this row is linked to, of one book, in link order.
 *
 * Distinct numbers rather than links: two containers of one shipping order are one
 * document to the person reading the list (AC-R-27), and the `+N` pill counts documents,
 * not placements. The lightbox behind the number still lists every link.
 *
 * The PO side also answers with the purchase order a SHIPMENT came from (7.2, owner 14 Sep
 * evening: "we definitely cannot double count, but by this linking it helps us to know the
 * PO and SPO corresponding to this order inquiry"). The importer stopped linking a purchase
 * order line for units already on its own ship, so a row whose whole quantity has sailed
 * holds no `po` link at all, and this column would go blank on exactly the rows purchasing
 * most wants to trace. A purchase order and its own shipment are ONE number here: the
 * partly shipped row carries both a `po` link and an `spo` link naming the same purchase
 * order, and the list must not read that as two.
 */
/**
 * One document number for this cell's book, and whether it is DERIVED (S5, R-E) - the
 * PO column's number read off an SPO link's `source_po_number` (`via: 'spo'`), or the
 * SPO column's number that is really the linked PO's own open shipment (`via: 'po'`).
 * Written nowhere: no link is created for either, so `via` never appears outside these
 * two columns.
 */
interface DocumentEntry {
  document: string;
  via: 'po' | 'spo' | null;
  /**
   * The FIRST link naming this document is fully received (S1,
   * `PLAN-oi-replan-received-links.md`, AC-RL-02) - goods that have landed, not a promise
   * still in transit. `receivedQty`/`qty` back the chip's own title; both are the LINK's
   * own figures, never the row's.
   */
  received: boolean;
  receivedQty: string | null;
  qty: string | null;
  /**
   * S1b (`PLAN-oi-replan-received-links.md`, AC-RL-20 to AC-RL-24): the FIRST link
   * naming this document carries a repoint/unlink instruction. Never on a received
   * link (S1's own `received` and S1b's `suggestion` are mutually exclusive by
   * construction on the wire, but the chip reads whichever the link states).
   */
  suggestion: OrderInquiryLinkSuggestion | null;
}

function documentsOf(row: OrderInquiryWorklistRow, kind: 'po' | 'spo'): DocumentEntry[] {
  const entries: DocumentEntry[] = [];
  const seen = new Set<string>();
  for (const link of row.links ?? []) {
    let named: string | null = null;
    let via: 'po' | 'spo' | null = null;
    if (kind === 'po') {
      if (link.kind === 'po') named = link.document;
      else if (link.kind === 'spo' && link.source_po_number) {
        named = link.source_po_number;
        via = link.derived_po ? 'spo' : null;
      }
    } else if (link.kind === 'spo') {
      named = link.document;
      via = link.derived ? 'po' : null;
    }
    const document = (named ?? '').trim();
    if (!document || seen.has(document)) continue;
    seen.add(document);
    entries.push({
      document,
      via,
      received: Boolean(link.received),
      receivedQty: link.received_qty ?? null,
      qty: link.qty ?? null,
      suggestion: link.suggestion ?? null,
    });
  }
  return entries;
}

/** `Repoint to OI-000539 · CB2805A-DIY · needed 01/12/2026 · open 90`, or `Unlink · no
 * sooner inquiry needs this item` (AC-RL-24). One concrete instruction, never a reason -
 * "early" is never printed. */
function suggestionInstruction(suggestion: OrderInquiryLinkSuggestion): string {
  if (suggestion.kind === 'unlink') return 'Unlink · no sooner inquiry needs this item';
  return (
    `Repoint to ${suggestion.inquiry_no ?? 'another inquiry'} · ` +
    `${suggestion.item_code ?? 'this item'} · ` +
    `needed ${formatDateInMalaysia(suggestion.delivery_date)} · ` +
    `open ${formatInquiryQty(suggestion.open_qty)}`
  );
}

/**
 * S1b (`PLAN-oi-replan-received-links.md`, AC-RL-20 to AC-RL-24): the muted `repoint`/
 * `unlink` word beside the PO/SPO chip, and the popover its own tap (or hover) opens -
 * the instruction text, never a reason. Nothing is written from here: purchasing acts
 * in AutoCount, and S5 (our own link follows the book) reacts to that.
 */
function LinkSuggestionMark({
  suggestion,
  testId,
}: {
  suggestion: OrderInquiryLinkSuggestion;
  testId: string;
}) {
  const word = suggestion.kind === 'repoint' ? 'repoint' : 'unlink';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          className="shrink-0 text-2xs text-muted-foreground underline-offset-2 hover:underline focus-visible:outline-none"
          onClick={(event) => event.stopPropagation()}
        >
          {word}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto max-w-xs text-xs" onClick={(event) => event.stopPropagation()}>
        {suggestionInstruction(suggestion)}
      </PopoverContent>
    </Popover>
  );
}

/**
 * The PO cell and the SPO cell, which are the same cell over two books (owner, 14 Sep,
 * live look at prod: "1 column to show the linked PO and 1 column to show the linked SPO
 * (if linked to more than 1 then put as +1 pill) ... then I can click on the PO and SPO to
 * view the lightbox popup which is what we currently have").
 *
 * ONE LINE: the draft/confirmed mark, the first document number as the trigger, and a `+N`
 * pill when the row stands on more than one number of that book. The coverage headline and
 * the info icon left the cell in this slice - both already live in the lightbox, the
 * headline as its subtitle, and the number is a better trigger than an icon because it
 * answers the question ("which PO?") before it is clicked.
 *
 * A row linked in the OTHER book only reads as a muted dash here: it is linked, and this
 * is not where it is linked. Only a row linked in NEITHER book is a new order, and the PO
 * cell says that in words.
 *
 * The dialog mounts only once opened, so a page of a hundred rows does not carry two
 * hundred dialogs - the same pattern the info icon used.
 */
function DocumentsCell({ row, kind }: { row: OrderInquiryWorklistRow; kind: 'po' | 'spo' }) {
  const [open, setOpen] = React.useState(false);
  const numbers = documentsOf(row, kind);
  if (numbers.length === 0) return <Muted>-</Muted>;
  const [first, ...rest] = numbers;
  const what = row.item_code ?? row.so_number ?? 'this row';
  // The PO trigger keeps the id the info icon carried, so AC-A5's lightbox contract holds
  // and nothing that already points at it has to be told about this change.
  const triggerId =
    kind === 'spo' ? `backing-documents-trigger-spo-${row.id}` : `backing-documents-trigger-${row.id}`;
  const open_ = (event: React.MouseEvent) => {
    event.stopPropagation();
    setOpen(true);
  };
  // AC-RL-02: a received document's title states the receipt rather than just the
  // number - goods that have landed read differently from a promise still in transit.
  const title = first.received
    ? `${first.document} - received ${formatInquiryQty(first.receivedQty ?? '0')} of ${formatInquiryQty(first.qty ?? '0')}`
    : first.document;
  return (
    <span className="flex min-w-0 items-center gap-1">
      <DraftMark row={row} />
      <button
        type="button"
        data-testid={triggerId}
        title={title}
        aria-label={`Show documents backing ${what}`}
        className="block min-w-0 truncate rounded-sm text-xs font-medium tabular-nums text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={open_}
      >
        {first.document}
      </button>
      {/* S5, R-E: never a real link - the SAME allocation read the other book's own
          number off (an SPO's `source_po_number`, or the PO's own open shipment). */}
      {first.via ? (
        <span
          data-testid={
            kind === 'spo'
              ? `backing-documents-via-spo-${row.id}`
              : `backing-documents-via-${row.id}`
          }
          className="shrink-0 text-2xs text-muted-foreground"
        >
          {first.via === 'po' ? 'via PO' : 'via SPO'}
        </span>
      ) : null}
      {/* S1, AC-RL-02: the document is fully received - location stock now, not a
          promise still in transit. Same muted style as the "via" mark beside it. */}
      {first.received ? (
        <span
          data-testid={
            kind === 'spo'
              ? `backing-documents-received-spo-${row.id}`
              : `backing-documents-received-${row.id}`
          }
          className="shrink-0 text-2xs text-muted-foreground"
        >
          received
        </span>
      ) : null}
      {/* S1b, AC-RL-24: a repoint/unlink instruction, mutually exclusive with the
          `received` mark above (a received link never carries a suggestion). */}
      {first.suggestion ? (
        <LinkSuggestionMark
          suggestion={first.suggestion}
          testId={
            kind === 'spo'
              ? `backing-documents-suggestion-spo-${row.id}`
              : `backing-documents-suggestion-${row.id}`
          }
        />
      ) : null}
      {rest.length ? (
        <Badge asChild size="sm" variant="secondary" appearance="light">
          <button
            type="button"
            data-testid={
              kind === 'spo'
                ? `backing-documents-pill-spo-${row.id}`
                : `backing-documents-pill-${row.id}`
            }
            aria-label={`Show all ${numbers.length} documents backing ${what}`}
            className="shrink-0 tabular-nums"
            onClick={open_}
          >
            +{rest.length}
          </button>
        </Badge>
      ) : null}
      {open ? (
        <OrderInquiryBackingDocumentsDialog row={row} open onOpenChange={setOpen} />
      ) : null}
    </span>
  );
}

/**
 * The PO cell's info icon for a BUNDLED row (UAC D1-D3, D10;
 * PLAN-scm-supplied-with-companions.md section 3.4). The only info icon left on this list
 * since S3 (14 Sep): a bundled row has no document number of its own to click, so the icon
 * is still the way into the anchor's lightbox.
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
  // AC-RL-46 (`PLAN-oi-replan-received-links.md` S5): a row the book redirected off is
  // neither rejected nor changed - a settle never touched it - so the gate widens to the
  // same note `follow_book_repairing` wrote, the only other fact this icon ever shows.
  const moved = Boolean(movedNoteOf(row));
  if (!rejected && !changed && !moved) return null;
  const label = rejected
    ? `Show why ${row.item_code ?? row.so_number ?? 'this row'} was rejected`
    : changed
      ? `Show what changed on ${row.item_code ?? row.so_number ?? 'this row'}`
      : `Show what AutoCount changed on ${row.item_code ?? row.so_number ?? 'this row'}`;
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
 * The Qty cell's `redirected` mark (S3, `PLAN-oi-replan-received-links.md`, AC-RL-04):
 * a row a replan could not carry forward because its only coverage had already landed
 * elsewhere. Its `qty` still reads as history - the mark is what tells purchasing not
 * to act on it, since the fresh Buy sits on a row of its own with no mark at all.
 */
function RedirectedMark({ row }: { row: OrderInquiryWorklistRow }) {
  if (!row.redirected_to_pool) return null;
  const label = 'Redirected: this document already went to other orders, kept here as history';
  return (
    <span
      data-testid={`redirected-mark-${row.id}`}
      title={label}
      aria-label={label}
      className="shrink-0 text-2xs text-muted-foreground"
    >
      redirected
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
              // Informational only - TanStack reads `getCanSelect` off the TABLE's own
              // `enableRowSelection`, never a column's (`OrderInquiriesClient`'s own
              // note over the same trap), which is where R-A's rule actually lives now
              // (S4, PLAN-scm-oi-worklist-excel-parity.md): every row except `cancelled`
              // ticks, fully linked rows included. Kept here only so this column's own
              // `disabledReason` still applies to the one row the table itself blocks.
              disabledReason: (row) =>
                row.original.state === 'cancelled'
                  ? 'This instruction was called off'
                  : undefined,
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
            <RedirectedMark row={row.original} />
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
        // WHICH PURCHASE ORDER this row stands on (AC-R-26..R-31, owner 14 Sep, live look
        // at prod after the migration upload). The cell is ONE LINE: the draft/confirmed
        // mark, the first PO number as the trigger for the backing-documents lightbox, and
        // a `+N` pill when the row stands on more than one. The coverage headline and the
        // info icon left this cell in that slice - both are in the lightbox already (the
        // headline is its subtitle), and the owner's question of the list is "which PO",
        // which an icon cannot answer until it is clicked.
        //
        // The column id stays `po_number`: it is what a saved column layout is keyed by,
        // and renaming it would silently exile the column to the right of everyone's grid.
        id: 'po_number',
        accessorFn: (row) => documentsOf(row, 'po')[0]?.document ?? '',
        header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
        // Wide enough for `202605-S0005` AND the "via SPO" tag beside it at 1280 (review
        // round): at 150 the number itself truncated the moment a row's PO was derived,
        // which is the one row where reading the whole number matters.
        size: 200,
        meta: { headerTitle: 'PO', skeleton: <Skeleton className="h-4 w-24" /> },
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
          if ((row.original.links ?? []).length === 0) {
            // Nothing in either book can cover this row (S5, AC-D4): a plain dash, the
            // same "no explanation in the UI" rule every other blank cell here follows -
            // "Not found (new order)" read as a caption nobody asked for. Nothing is
            // clickable: there is nothing behind it to open.
            return (
              <div className="min-w-0">
                <Muted>-</Muted>
              </div>
            );
          }
          // Linked in the other book only: a muted dash, and the SPO cell beside this one
          // is where that row says where it stands.
          return <DocumentsCell row={row.original} kind="po" />;
        },
      },
      {
        // WHICH SHIPPING ORDER this row stands on - the other half of the owner's ruling,
        // and a new column rather than a second line in the PO cell, because "I want all
        // rows to have 1 line only".
        id: 'spo_number',
        accessorFn: (row) => documentsOf(row, 'spo')[0]?.document ?? '',
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        // Same width as PO beside it, for the same reason - plus "awaiting shipment",
        // which this column prints in full.
        size: 200,
        meta: { headerTitle: 'SPO', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => {
          // A bundled row's documents are the anchor's, and the PO cell already says so
          // in words (`Included with ...`) with the bundled lightbox behind it. Repeating
          // any of that here would make the bundle read as two separate facts.
          const bundledQty = Number(row.original.bundled_qty ?? '0');
          const bundled =
            row.original.bundled_with && Number.isFinite(bundledQty) && bundledQty > 0;
          if (bundled) return <Muted>-</Muted>;
          // S5, AC-D4: bought but not yet on a shipment - distinct from a plain dash,
          // which means nobody has put this row anywhere at all.
          if (
            documentsOf(row.original, 'spo').length === 0 &&
            documentsOf(row.original, 'po').length > 0
          ) {
            return <Muted>awaiting shipment</Muted>;
          }
          return <DocumentsCell row={row.original} kind="spo" />;
        },
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
