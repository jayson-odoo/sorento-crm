'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  Check,
  ChevronDown,
  ChevronRight,
  History as HistoryIcon,
  Pencil,
  X,
} from 'lucide-react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Skeleton } from '@/components/ui/skeleton';
import { OrderInquiryVerbPill } from '../../../_shared/components/OrderInquiryVerbPill';
import { OrderInquiryLineStatusPill } from '../../../_shared/components/OrderInquiryLineStatusPill';
import {
  LineDocumentsCell,
  lineDocumentsOf,
} from '../../components/OrderInquiryLineDocuments';
import { OrderInquiryStockGrid } from '../../../_shared/components/OrderInquiryStockGrid';
import {
  formatInquiryQty,
  orderInquirySoLineHref,
  raisedKindLabel,
} from '../../../_shared/lib/orderInquiryWorklist';
import {
  lineFooterTotals,
  lineOf,
  type OrderInquiryLine,
  type OrderInquiryLineRow,
} from '../../../_shared/lib/orderInquiryLineFold';
import {
  DeliveryDateCell,
  ItemCodeCell,
  LocationCell,
  orderInquiryReserveQtyColumns,
  orderInquirySuggestedColumn,
  RaisedCell,
  SupplierCell,
} from '../../components/orderInquiryWorklistColumns';
import type {
  OrderInquiryLineSplit,
  OrderInquiryWorklistRow,
} from '../../../_shared/types/orderInquiry.types';
import { SoLineAttachmentsButton } from '../../../_shared/components/SoLineAttachmentsButton';
import {
  LineSplitInfo,
  splitCount,
  splitDateText,
} from '../../../_shared/components/LineSplitInfo';
import type { SoLineAttachmentsByLine } from '../../../_shared/services/soLineAttachmentService';
import { NumberInput } from '@/components/ui/number-input';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatMoneyExact } from '../../../_shared/lib/money';
import { changedFrom } from '../../../_shared/lib/sparePartRequest';
import type { OrderInquiryType } from '../../../_shared/types/orderInquiry.types';
import type { LineSplitsPayload } from '../../../_shared/types/lineSplit.types';

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
 *
 * `PLAN-oi-no-double-count-25sep.md` S0 (issue #1248, owner rulings 26 Sep 2026): each
 * grid row is ONE sales order line (`OrderInquiryLineRow`: the line's primary row plus the
 * line, `orderInquiryLineFold.ts`). No. replaces the SO line column; SO Qty, Requested,
 * Taken, Remaining replace Qty / Taken / Remaining (G4) and carry no Was / now annotation
 * (G1); PO / SPO list every document of the line's live rows as first + "+N" (G5); the
 * State cell carries ONE History icon for the line (G3), replacing the reserve History
 * icon and the decision trail icon.
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

/** Where a split sits, in words: a numbered line, an unnumbered one, or a new line. */
function sitsOnText(split: OrderInquiryLineSplit, itemCode: string | null | undefined): string {
  if (split.is_cancel) return '';
  if (!split.sits_on_line_id) return 'New line (not in AutoCount yet)';
  if (split.sits_on_line_no != null) return `line ${split.sits_on_line_no}`;
  return itemCode ? `line ${itemCode}` : 'line';
}

/**
 * AC-D2: a part sitting on an SO line prints that line's date, with the part's own planned
 * date muted beside it when they differ; a part with no AutoCount line yet prints its planned
 * date marked "planned". A cancel part prints as it always did.
 */
export function SplitDateCell({ split }: { split: OrderInquiryLineSplit }) {
  const own = splitDateText(split.delivery_date);
  const onLine = split.sits_on_line_id ? splitDateText(split.sits_on_line_date) : '';
  const shown = onLine || own;
  const planned =
    !split.is_cancel && own && (!split.sits_on_line_id || (onLine && onLine !== own))
      ? `planned${split.sits_on_line_id ? ` ${own}` : ''}`
      : '';
  const title = planned ? `${shown} ${planned}` : shown;
  return (
    <span className="block truncate tabular-nums" title={title}>
      {shown}
      {planned ? <span className="ms-1 text-muted-foreground">{planned}</span> : null}
    </span>
  );
}

const SPLIT_COLUMNS = (itemCode: string | null | undefined): ColumnDef<OrderInquiryLineSplit>[] => [
  {
    accessorKey: 'qty',
    header: () => <span className="block text-right">Qty</span>,
    size: 80,
    meta: { headerTitle: 'Qty' },
    cell: ({ row }) => (
      <span className="block text-right tabular-nums">{formatInquiryQty(row.original.qty)}</span>
    ),
  },
  {
    accessorKey: 'delivery_date',
    header: 'Date',
    // dd/mm/yyyy, then "planned dd/mm/yyyy" beside it; truncates with a title.
    size: 240,
    meta: { headerTitle: 'Date' },
    cell: ({ row }) => <SplitDateCell split={row.original} />,
  },
  {
    accessorKey: 'change',
    header: 'Change',
    size: 150,
    meta: { headerTitle: 'Change' },
    cell: ({ row }) => (
      <OrderInquiryVerbPill
        verb={row.original.change === 'CANCEL BALANCE' ? 'CANCEL_BALANCE' : row.original.change}
      />
    ),
  },
  {
    id: 'sits_on',
    header: 'Sits on',
    size: 160,
    meta: { headerTitle: 'Sits on' },
    cell: ({ row }) => {
      const text = sitsOnText(row.original, itemCode);
      return (
        <span className="block truncate text-muted-foreground" title={text}>
          {text}
        </span>
      );
    },
  },
  {
    accessorKey: 'remark',
    header: 'Remark',
    size: 240,
    meta: { headerTitle: 'Remark' },
    cell: ({ row }) => (
      <span className="block truncate" title={row.original.remark}>
        {row.original.remark}
      </span>
    ),
  },
];

function LineSplitsGrid({
  splits,
  itemCode,
}: {
  splits: OrderInquiryLineSplit[];
  itemCode: string | null | undefined;
}) {
  const columns = React.useMemo(() => SPLIT_COLUMNS(itemCode), [itemCode]);
  const table = useReactTable({
    columns,
    data: splits,
    getRowId: (split) => split.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });
  return (
    <div className="mb-2 max-w-3xl">
      <DataGrid
        table={table}
        recordCount={splits.length}
        tableLayout={{
          width: 'fixed',
          columnsResizable: true,
          columnsDraggable: false,
          scrollerMaxHeight: false,
        }}
      >
        <DataGridTable />
      </DataGrid>
    </div>
  );
}

/** OI-LINE-SPLIT (UAC D3): the splits of the line, read-only: Qty, Date, Change, Sits on,
 * Remark. Nothing when the line is not split. */
function LineSplitsList({
  splits,
  itemCode,
}: {
  splits: OrderInquiryLineSplit[];
  itemCode: string | null | undefined;
}) {
  if (splits.length === 0) return null;
  return <LineSplitsGrid splits={splits} itemCode={itemCode} />;
}

function reserveChipText(staged: StagedReserveEntry): string {
  if (staged.kind === 'amend') return `Amend to ${staged.qty}`;
  // No location staged (the server defaults it): no dangling "@".
  if (staged.qty > 0 && staged.locationLabel) return `Reserve ${staged.qty} @ ${staged.locationLabel}`;
  return `Reserve ${staged.qty}`;
}

export function ReserveActionsCell({
  row,
  staged,
  onTickReserve,
  onRejectReserve,
  onEditReserve,
  onAmendReserve,
  onUndoStaged,
  canAmend = true,
}: {
  row: OrderInquiryWorklistRow;
  staged?: StagedReserveEntry;
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  onRejectReserve?: (row: OrderInquiryWorklistRow) => void;
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  onUndoStaged?: (rowId: string) => void;
  canAmend?: boolean;
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
        {/* OI-BULK-RESERVE (AC-BR-09): Reserve 0 + one reason, the line's own copy of the
            strip's Decide > Reject... */}
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="size-6"
          aria-label="Reject"
          title="Reject"
          onClick={() => onRejectReserve?.(row)}
        >
          <X className="size-3.5" aria-hidden />
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
  // 6e.4 (AC-RS-83b): a declined line (CS answered 0) gets the same Amend as a reserved
  // one, so "0 -> up" stays reachable. Its reserve history is the Reserve tab of the
  // line's one History dialog now (owner ruling 26 Sep, G3), not an icon of its own.
  // The cross-OI Lines page draws no Amend (OI-BULK-RESERVE v4): `canAmend={false}`.
  if (canAmend && (row.reserve_state === 'reserved' || row.reserve_state === 'declined')) {
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
      </div>
    );
  }
  return null;
}

/** AC-ND-17: a footer total over every loaded line (the tab loads the whole set at once,
 * so there is no server page this could disagree with). */
function LineFooter({
  rows,
  field,
}: {
  rows: OrderInquiryLineRow[];
  field: 'soQty' | 'requested' | 'taken' | 'remaining';
}) {
  const totals = lineFooterTotals(rows.map(lineOf));
  return <span className="tabular-nums">{formatInquiryQty(String(totals[field]))}</span>;
}

const QUANTITY_COLUMNS: {
  id: string;
  title: string;
  field: 'soQty' | 'requested' | 'taken' | 'remaining';
}[] = [
  // S2: `soQty` is the server's `so_line_qty`, the sales order grid's own Qty.
  { id: 'so_qty', title: 'SO Qty', field: 'soQty' },
  { id: 'requested', title: 'Requested', field: 'requested' },
  { id: 'taken', title: 'Taken', field: 'taken' },
  { id: 'remaining', title: 'Remaining', field: 'remaining' },
];

/** The SO Qty / Requested / Taken / Remaining column for one `QUANTITY_COLUMNS` entry. */
function quantityColumn({
  id,
  title,
  field,
}: (typeof QUANTITY_COLUMNS)[number]): ColumnDef<OrderInquiryLineRow> {
  return {
    id,
    accessorFn: (row) => lineOf(row)[field],
    header: ({ column }) => <DataGridColumnHeader title={title} column={column} />,
    size: id === 'requested' || id === 'remaining' ? 120 : 100,
    meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-10" /> },
    cell: ({ row }) => {
      // A row that names no sales order line has no SO Qty (L17).
      const value = lineOf(row.original)[field];
      return (
        <span className="tabular-nums">
          {value == null ? '-' : formatInquiryQty(String(value))}
        </span>
      );
    },
    footer: ({ table }) => (
      <LineFooter
        rows={table.getPrePaginationRowModel().rows.map((r) => r.original)}
        field={field}
      />
    ),
  };
}

/** The line's reserve figure: summed over its live rows of ANY verb (OI-RESERVE-ANY-ROW, owner
 * 5 Nov 2026: a DELAY or ADVANCE row is reservable too), the rows Taken counts reserve on
 * (`orderInquiryLineFold.ts`), so the columns beside it agree. */
function lineReserveQty(row: OrderInquiryLineRow, field: 'asked_reserve_qty' | 'reserved_qty') {
  const total = lineOf(row).liveRows.reduce(
    (sum, live) => sum + (Number(live[field] ?? '0') || 0),
    0,
  );
  return String(total);
}

/** The chevron that opens a line's splits (if any) and its stock table (AC-RS-40), shared by
 *  the sales-order and spare part column sets. */
function stockExpandColumn(): ColumnDef<OrderInquiryLineRow> {
  return {
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
      expandedContent: (line: OrderInquiryLineRow) => (
        <div className="px-3 py-2">
          <LineSplitsList splits={line.splits ?? []} itemCode={line.item_code} />
          {line.product_id ? (
            <OrderInquiryStockGrid productId={line.product_id} location={line.location ?? null} />
          ) : (
            <p className="text-xs text-muted-foreground">No product resolved for this line yet.</p>
          )}
        </div>
      ),
    },
  };
}

function locationColumn(): ColumnDef<OrderInquiryLineRow> {
  return {
    accessorKey: 'location',
    header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
    size: 130,
    meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-16" /> },
    cell: ({ row }) => <LocationCell row={row.original} />,
  };
}

function poColumn(): ColumnDef<OrderInquiryLineRow> {
  return {
    id: 'po_number',
    accessorFn: (row) => lineDocumentsOf(lineOf(row), 'po')[0]?.document ?? '',
    header: ({ column }) => <DataGridColumnHeader title="PO" column={column} />,
    size: 200,
    meta: { headerTitle: 'PO' },
    cell: ({ row }) => <LineDocumentsCell line={lineOf(row.original)} kind="po" />,
  };
}

/** AC-ND-13 (owner ruling 26 Sep, G3): the line's ONE History icon. */
function LineHistoryButton({
  line,
  onClick,
}: {
  line: OrderInquiryLine;
  onClick?: (line: OrderInquiryLine) => void;
}) {
  return (
    <Button
      type="button"
      mode="icon"
      variant="ghost"
      size="sm"
      className="size-6 shrink-0"
      aria-label="History"
      title="History"
      onClick={(event) => {
        event.stopPropagation();
        onClick?.(line);
      }}
    >
      <HistoryIcon className="size-3.5" aria-hidden />
    </Button>
  );
}

/** SPARE-PART-ORDER-REQUEST (UAC A3): what the approver changed on a line. */
export interface SparePartLineEdit {
  qty?: string;
  unit_price?: string;
}

/** "was 10" (a qty) or "was RM 35.00" (money, in the request's currency) beside a value the
 *  approver moved off what the requester submitted. */
function WasMark({
  current,
  submitted,
  money,
  currency,
}: {
  current?: string | null;
  submitted?: string | null;
  money?: boolean;
  currency?: string | null;
}) {
  if (!changedFrom(current, submitted)) return null;
  return (
    <span className="ms-1.5 whitespace-nowrap text-xs text-muted-foreground">
      was {money ? formatMoneyExact(submitted, currency) : formatInquiryQty(submitted)}
    </span>
  );
}

/** The approver's own qty / unit price box: commits on blur when the value moved. */
function ApproverNumberCell({
  value,
  label,
  onCommit,
}: {
  value: string | null | undefined;
  label: string;
  onCommit: (next: string) => void;
}) {
  const initial = value == null || value === '' ? null : Number(value);
  const [draft, setDraft] = React.useState<number | null>(initial);
  React.useEffect(() => setDraft(initial), [initial]);
  return (
    <NumberInput
      value={draft}
      onValueChange={setDraft}
      min={0}
      step="any"
      aria-label={label}
      className="h-7 w-[4.5rem] text-right tabular-nums"
      onClick={(event) => event.stopPropagation()}
      onBlur={() => {
        if (draft == null || Number.isNaN(draft) || draft < 0 || draft === initial) return;
        onCommit(String(draft));
      }}
    />
  );
}

/**
 * SPARE-PART-ORDER-REQUEST (UAC P4, A3): the Lines tab of a spare part request. The same
 * renderers as a sales-order inquiry where the fact is the same (stock grid, product,
 * documents, location, instruction, state, paperclip); no SO line, SO Qty, split or reserve
 * columns, since the request has no sales order. Unit price and Total in their place, and
 * while the request is pending approval a decider edits Qty and Unit price in place.
 *
 * Review R11: the visible sizes sum within the record page's card at 1280 (950 px), so Total
 * is never behind a sideways scroll. No Instruction column: every spare part line reads
 * "Replenish" (UAC P5), so it carried nothing a reader needs.
 */
function sparePartLineColumns({
  editable,
  currency,
  onEditLine,
  onLineHistoryClick,
  attachmentsByRow,
  canEditAttachments,
}: {
  editable: boolean;
  currency?: string | null;
  onEditLine?: (row: OrderInquiryWorklistRow, edit: SparePartLineEdit) => void;
  onLineHistoryClick?: (line: OrderInquiryLine) => void;
  attachmentsByRow?: SoLineAttachmentsByLine;
  canEditAttachments: boolean;
}): ColumnDef<OrderInquiryLineRow>[] {
  return [
    stockExpandColumn(),
    buildSelectColumn<OrderInquiryLineRow>({
      rowLabel: (row) => `Select ${row.original.item_code ?? 'line'}`,
    }),
    {
      accessorKey: 'item_code',
      header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
      size: 130,
      meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-32" /> },
      cell: ({ row }) => (
        <span className="block min-w-0 truncate">
          {/* G1: the requester's own description under the code, else the product's name. */}
          <ItemCodeCell
            row={{
              ...row.original,
              product_name: row.original.line_description || row.original.product_name,
            }}
          />
        </span>
      ),
    },
    { ...locationColumn(), size: 90 },
    {
      accessorKey: 'qty',
      header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
      size: 110,
      meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
      cell: ({ row }) => {
        const primary = lineOf(row.original).primary;
        return (
          // The "was" mark wraps under the value, as Unit price's does.
          <span className="flex min-w-0 flex-col items-start">
            {editable && onEditLine ? (
              <ApproverNumberCell
                value={primary.qty}
                label={`Qty for ${primary.item_code ?? 'this line'}`}
                onCommit={(qty) => onEditLine(primary, { qty })}
              />
            ) : (
              <span className="tabular-nums">{formatInquiryQty(primary.qty)}</span>
            )}
            <WasMark current={primary.qty} submitted={primary.submitted_qty} />
          </span>
        );
      },
    },
    {
      id: 'unit_price',
      accessorFn: (row) => Number(lineOf(row).primary.unit_price ?? 0),
      header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
      // D7: the value with its "was RM 35.00" mark wrapped under it.
      size: 120,
      meta: { headerTitle: 'Unit price', skeleton: <Skeleton className="h-4 w-16" /> },
      cell: ({ row }) => {
        const primary = lineOf(row.original).primary;
        return (
          // D7: the "was" mark wraps under the value, never clipped beside it.
          <span className="flex min-w-0 flex-col items-start">
            {editable && onEditLine ? (
              <ApproverNumberCell
                value={primary.unit_price}
                label={`Unit price for ${primary.item_code ?? 'this line'}`}
                onCommit={(unit_price) => onEditLine(primary, { unit_price })}
              />
            ) : (
              <span
                className="block max-w-full truncate tabular-nums"
                title={formatMoneyExact(primary.unit_price, currency)}
              >
                {formatMoneyExact(primary.unit_price, currency)}
              </span>
            )}
            <WasMark
              current={primary.unit_price}
              submitted={primary.submitted_unit_price}
              money
              currency={currency}
            />
          </span>
        );
      },
    },
    {
      id: 'line_total',
      accessorFn: (row) => Number(lineOf(row).primary.line_total ?? 0),
      header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
      size: 120,
      meta: { headerTitle: 'Total', skeleton: <Skeleton className="h-4 w-16" /> },
      cell: ({ row }) => {
        const total = lineOf(row.original).primary.line_total;
        return (
          <span className="block truncate tabular-nums" title={formatMoneyExact(total, currency)}>
            {formatMoneyExact(total, currency)}
          </span>
        );
      },
      // D5: the request's amount, over the lines still standing (a cancelled line is 0).
      footer: ({ table }) => {
        const rows = table.getPrePaginationRowModel().rows.map((r) => lineOf(r.original).primary);
        const live = rows.filter((r) => r.state !== 'cancelled');
        if (live.some((r) => r.line_total == null)) return <span className="text-muted-foreground">-</span>;
        const sum = live.reduce((acc, r) => acc + Number(r.line_total ?? 0), 0).toFixed(4);
        return <span className="tabular-nums font-medium">{formatMoneyExact(sum, currency)}</span>;
      },
    },
    { ...poColumn(), size: 100 },
    {
      id: 'state',
      accessorFn: (row) => lineOf(row).state,
      header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
      size: 190,
      minSize: 190,
      meta: { headerTitle: 'State' },
      cell: ({ row }) => {
        const line = lineOf(row.original);
        const primary = line.primary;
        return (
          <div className="flex min-w-0 items-center gap-1">
            <span className="shrink-0">
              {primary.state === 'draft' ? (
                // Before final approval the line is nobody's work yet.
                <span className={`${STATUS_PILL_BASE} ${statusPillClass('draft')}`}>
                  Not approved yet
                </span>
              ) : (
                <OrderInquiryLineStatusPill line={line} rejectedTestId={`lines-rejected-${primary.id}`} />
              )}
            </span>
            <LineHistoryButton line={line} onClick={onLineHistoryClick} />
            <SoLineAttachmentsButton
              lineId={primary.id}
              target={{ kind: 'order_inquiry_row', id: primary.id }}
              label={`${primary.inquiry_no ?? ''} ${primary.item_code ?? ''}`.trim()}
              attachments={attachmentsByRow?.[primary.id] ?? []}
              canEdit={canEditAttachments}
            />
          </div>
        );
      },
    },
  ];
}

export function useOrderInquiryHeaderLinesColumns({
  canReserve,
  stagedByRowId,
  onTickReserve,
  onRejectReserve,
  onEditReserve,
  onAmendReserve,
  onLineHistoryClick,
  onUndoStaged,
  attachmentsByLine,
  canEditAttachments = false,
  splitSheet,
  inquiryType = 'sales_order',
  headerState,
  canDecide = false,
  onEditLine,
  currency,
  attachmentsByRow,
}: {
  /** AC-RS-83/83c: gates the reserve icons inside the State cell - a viewer without
   * `projects.order_inquiries.reserve` sees the pills only. */
  canReserve?: boolean;
  /** 6e.2: this line's own staged (not yet committed) decision, keyed by row id -
   * `OrderInquiryDetail.tsx` owns the map, this column only renders over it. */
  stagedByRowId?: Record<string, StagedReserveEntry>;
  /** AC-RS-84: the tick - stages the full requested qty at the default pool, no dialog. */
  onTickReserve?: (row: OrderInquiryWorklistRow) => void;
  /** OI-BULK-RESERVE (AC-BR-09): the x on a requested line - opens "Reject 1 line". */
  onRejectReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-RS-85: the pencil on a requested line - opens `ReserveLineForm` in reserve mode. */
  onEditReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-RS-86: the pencil on a reserved line - opens `ReserveLineForm` in amend mode. */
  onAmendReserve?: (row: OrderInquiryWorklistRow) => void;
  /** AC-ND-13/14 (owner ruling 26 Sep, G3): opens the line's one History dialog. */
  onLineHistoryClick?: (line: OrderInquiryLine) => void;
  /** Drops a staged decision, restoring the two icons. */
  onUndoStaged?: (rowId: string) => void;
  /**
   * #1312 (AC-U6): every line's own clarification files, keyed by CORE sales-order
   * line id - `OrderInquiryLinesTab` owns the ONE lookup call this reads over
   * (`useSoLineAttachmentLookup`), the same shape the fulfilment board's own list
   * view passes into its columns. This is a pure renderer over it, like every other
   * prop here - no hook call of its own, since a cell function is invoked directly
   * by this file's own unit test (`orderInquiryHeaderLinesColumns.test.tsx`), outside
   * a real React render pass, where a hook call would break the Rules of Hooks.
   */
  attachmentsByLine?: SoLineAttachmentsByLine;
  /** #1312 (Q6): `projects.projects.edit` - gates the lightbox's own upload/remove. */
  canEditAttachments?: boolean;
  /**
   * OI-SPLIT-VIEW (UAC E5): the order's split sheet (`useLineSplits`, owned by the caller)
   * the line popups draw read-only; `payload` undefined while it loads.
   */
  splitSheet?: {
    payload: LineSplitsPayload | null | undefined;
    error?: unknown;
    onRetry?: () => void;
  };
  /** SPARE-PART-ORDER-REQUEST: the inquiry's type; a spare part request gets its own set. */
  inquiryType?: OrderInquiryType;
  /** The header's state: a decider edits Qty / Unit price only while `pending_approval`. */
  headerState?: string | null;
  /** The viewer is the current approver (server's `can_decide`). */
  canDecide?: boolean;
  /** The approver changed a line's qty or unit price (blur). */
  onEditLine?: (row: OrderInquiryWorklistRow, edit: SparePartLineEdit) => void;
  /** The request's currency, for Unit price / Total. */
  currency?: string | null;
  /** A spare part request's photos, keyed by ORDER INQUIRY ROW id. */
  attachmentsByRow?: SoLineAttachmentsByLine;
} = {}): ColumnDef<OrderInquiryLineRow>[] {
  return React.useMemo<ColumnDef<OrderInquiryLineRow>[]>(() => {
    if (inquiryType === 'spare_part_request') {
      return sparePartLineColumns({
        editable: canDecide && headerState === 'pending_approval',
        currency,
        onEditLine,
        onLineHistoryClick,
        attachmentsByRow,
        canEditAttachments,
      });
    }
    const columns: ColumnDef<OrderInquiryLineRow>[] = [
      // `PLAN-oi-request-cs-reserve.md` 3.9 (AC-RS-40): the board's own stock grid, a
      // chevron away - purchasing used to open the fulfilment board just to check BRW.
      stockExpandColumn(),
      buildSelectColumn<OrderInquiryLineRow>({
        rowLabel: (row) => `Select ${row.original.item_code ?? 'line'}`,
      }),
      // AC-ND-3 (owner ruling 26 Sep, G4): the sales order's own line No., replacing the
      // SO line column - the header already names the sales order.
      {
        id: 'line_no',
        accessorFn: (row) => lineOf(row).lineNo ?? Number.POSITIVE_INFINITY,
        header: ({ column }) => <DataGridColumnHeader title="No." column={column} />,
        size: 72,
        meta: { headerTitle: 'No.', skeleton: <Skeleton className="h-4 w-6" /> },
        cell: ({ row }) => {
          const line = lineOf(row.original);
          const lineNo = line.lineNo;
          if (lineNo == null) return <span className="text-muted-foreground">-</span>;
          // Owner hand test (5 Nov 2026): the No. opens the sales order's Lines tab at this
          // line, highlighted (`orderInquirySoLineHref`, the worklist's own SO line link).
          const linked = line.rows.find((r) => r.core_sales_order_id && r.core_line_id);
          const href = linked ? orderInquirySoLineHref(linked) : null;
          return href ? (
            <Link
              href={href}
              onClick={(event) => event.stopPropagation()}
              className="tabular-nums font-medium text-primary hover:underline"
            >
              {lineNo}
            </Link>
          ) : (
            <span className="tabular-nums">{lineNo}</span>
          );
        },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        size: 220,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-32" /> },
        // AC-DP-03, owner ruling 21 Sep: code only, one line - never the second
        // `product_name` line the worklist's own cell prints for a real row.
        cell: ({ row }) => (
          <span className="block min-w-0 truncate">
            <ItemCodeCell row={row.original} codeOnly />
          </span>
        ),
      },
      // OI-SPLIT-VIEW (UAC B1): "Split N" and the (i) popup in their own column right after
      // Product (the Product cell stays the product only), on Columns like the rest.
      {
        id: 'split',
        // B7a: sorts by the chip's N (the AutoCount extra row not counted).
        accessorFn: (row) => splitCount(row.split_view),
        header: ({ column }) => <DataGridColumnHeader title="Split" column={column} />,
        size: 110,
        meta: { headerTitle: 'Split' },
        cell: ({ row }) => {
          const line = lineOf(row.original);
          return (
            <LineSplitInfo
              lineNo={line.lineNo}
              itemCode={row.original.item_code}
              soNumber={row.original.so_number}
              oiNumber={row.original.inquiry_no}
              view={row.original.split_view}
              payload={splitSheet?.payload}
              loadError={splitSheet?.error}
              onRetry={splitSheet?.onRetry}
            />
          );
        },
      },
      // AC-ND-3..5b (owner ruling 26 Sep, G4): SO Qty, Requested, Taken, Remaining - the
      // line's own sums (`orderInquiryLineFold.ts`), no Was / now annotation (G1).
      // OI-RESERVE-PILL-QTY round 2: Reserve requested and Reserved sit right after
      // Requested, the shared columns the Lines list uses, summed over the line's live
      // rows (any verb, OI-RESERVE-ANY-ROW).
      ...QUANTITY_COLUMNS.slice(0, 2).map(quantityColumn),
      ...orderInquiryReserveQtyColumns<OrderInquiryLineRow>({
        requestedOf: (row) => lineReserveQty(row, 'asked_reserve_qty'),
        reservedOf: (row) => lineReserveQty(row, 'reserved_qty'),
      }),
      ...QUANTITY_COLUMNS.slice(2).map(quantityColumn),
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        size: 180,
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
      poColumn(),
      {
        id: 'spo_number',
        accessorFn: (row) => lineDocumentsOf(lineOf(row), 'spo')[0]?.document ?? '',
        header: ({ column }) => <DataGridColumnHeader title="SPO" column={column} />,
        // LINKAGE-UNIFY U3 round 3/7: number, "via PO", the whole "Received <qty> at <bin>"
        // and "+1" side by side at 1280 (this table's number is wider than the worklist's).
        // Round 7b: measured in the browser.
        size: 420,
        // Round 9 (owner): no `minSize`, so the column shrinks like the PO column; the pill
        // ellipsizes and the number stays whole.
        meta: { headerTitle: 'SPO' },
        cell: ({ row }) => <LineDocumentsCell line={lineOf(row.original)} kind="spo" />,
      },
      // AC-LT-07: the SAME Suggested column the worklist carries, right after SPO. It
      // reads the primary row's suggestions (S2 wires a line-level read).
      orderInquirySuggestedColumn() as ColumnDef<OrderInquiryLineRow>,
      locationColumn(),
      {
        accessorKey: 'verb',
        header: ({ column }) => <DataGridColumnHeader title="Instruction" column={column} />,
        size: 200,
        meta: { headerTitle: 'Instruction', skeleton: <Skeleton className="h-4 w-24" /> },
        // G5: the line's most urgent instruction (CANCEL_BALANCE > CHANGE_SO > DELAY >
        // ADVANCE > the primary row's own verb). The pill only, never the shared cell's
        // note (i): G1 moves the note ("Replaces 2 used ...") to History's Why (review
        // B2). A cancelled line has nothing to instruct, so it reads "-" (review N1).
        cell: ({ row }) => {
          const line = lineOf(row.original);
          if (line.lineCancelled) return <span className="text-muted-foreground">-</span>;
          return <OrderInquiryVerbPill verb={line.instructionRow.verb} />;
        },
      },
      {
        // AC-DT-6 (`PLAN-oi-decision-trail-ui.md`): the same Raised column the worklist
        // carries - `RaisedCell` is shared so the same row reads the same way on both
        // screens. Hidden by default on BOTH now (round 2 ruling); `accessorFn` is what
        // the column picker keys "can this be listed" on
        // (`data-grid-column-visibility.tsx`), so a bare `id` + `cell` made this column
        // impossible to ever turn back on.
        id: 'raise_event',
        accessorFn: (row) => raisedKindLabel(row) ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Raised via" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Raised via', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => <RaisedCell row={row.original} />,
      },
      // `PLAN-oi-request-cs-reserve.md` 6e.2 (AC-RS-83): the pill is plain text.
      {
        // PR #1266 review nit: sorts on the line's own State, what the cell shows, not
        // the primary row's raw state (To confirm, Line cancelled and Nothing to buy
        // sorted as raised / placed). Same id, so saved column preferences still apply.
        id: 'state',
        accessorFn: (row) => lineOf(row).state,
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        // AC-RS-83c (owner, 24 Sep: "this pen can put right next to state?"): the
        // reserve icons sit in this cell, right of the pill - no separate column, which
        // saved column preferences appended after Location. Wide enough for the pill
        // plus a staged chip and Undo. No `minSize`: a user who drags it narrower than
        // the icons is choosing that, and can drag it back out again (owner, 24 Sep).
        // OI-BULK-RESERVE: +28 for the x between the tick and the pen.
        size: canReserve ? 438 : 220,
        // The pill never shrinks, so a narrow saved width is clamped in both layouts.
        minSize: 190,
        meta: { headerTitle: 'State' },
        cell: ({ row }) => {
          const line = lineOf(row.original);
          const primary = line.primary;
          // SO-LINE-OI-STATUS-UNIFY: the ONE line status, shared with the Sales Order's
          // Lines tab (`OrderInquiryLineStatusPill`).
          // Review S1: a rejected line's reason truncates inside the cell, so the
          // History, paperclip and reserve icons beside it stay in reach.
          const pillWrap =
            primary.ack_state === 'rejected' ? 'flex min-w-0 shrink' : 'shrink-0';
          const pill = (
            <OrderInquiryLineStatusPill
              line={line}
              rejectedTestId={`lines-rejected-${primary.id}`}
            />
          );
          // AC-ND-13 (owner ruling 26 Sep, G3): ONE History icon on every line - rows,
          // decisions and reserve history behind one dialog - never gated on a core line
          // or on `canReserve`.
          const history = <LineHistoryButton line={line} onClick={onLineHistoryClick} />;
          // #1312 (AC-U6): the same paperclip the fulfilment board carries, on every
          // line that names a core sales-order line - a row raised before AutoCount
          // reconciled it (`core_line_id` null) has nowhere to file a clarification
          // against, same rule the board's own list view follows.
          const coreLineId = row.original.core_line_id;
          const attachments = coreLineId ? (attachmentsByLine?.[coreLineId] ?? []) : null;

          if (!canReserve || line.liveRows.length === 0) {
            return (
              <div className="flex min-w-0 items-center gap-1">
                <span className={pillWrap}>{pill}</span>
                {history}
                {coreLineId ? (
                  <SoLineAttachmentsButton
                    lineId={coreLineId}
                    label={`${row.original.so_number ?? ''} L${line.lineNo ?? ''} ${row.original.item_code ?? ''}`}
                    attachments={attachments ?? []}
                    canEdit={canEditAttachments}
                  />
                ) : null}
              </div>
            );
          }
          return (
            <div className="flex min-w-0 items-center gap-1">
              <span className={pillWrap}>{pill}</span>
              {history}
              {coreLineId ? (
                <SoLineAttachmentsButton
                  lineId={coreLineId}
                  label={`${row.original.so_number ?? ''} L${line.lineNo ?? ''} ${row.original.item_code ?? ''}`}
                  attachments={attachments ?? []}
                  canEdit={canEditAttachments}
                />
              ) : null}
              <ReserveActionsCell
                row={primary}
                staged={stagedByRowId?.[primary.id]}
                onTickReserve={onTickReserve}
                onRejectReserve={onRejectReserve}
                onEditReserve={onEditReserve}
                onAmendReserve={onAmendReserve}
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
    onRejectReserve,
    onEditReserve,
    onAmendReserve,
    onLineHistoryClick,
    onUndoStaged,
    attachmentsByLine,
    canEditAttachments,
    splitSheet,
    inquiryType,
    headerState,
    canDecide,
    onEditLine,
    currency,
    attachmentsByRow,
  ]);
}
