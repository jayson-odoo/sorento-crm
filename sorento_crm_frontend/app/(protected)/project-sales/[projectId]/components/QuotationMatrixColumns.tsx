'use client';

/**
 * The quotation Lines grid's quantity columns for a scope with column headers (PS-QUOTE-MATRIX,
 * mock v3 frames 1, 2 and 5): the single Qty column becomes one input per column, grouped under
 * its header, with a Qty / RM pair per header (R7), Total qty, and two footer lines (R8).
 *
 * The header IS the column editor on an editable version (R11): labels rename in place, a grip
 * drags (or arrow-keys) a header or a column within its header, the x removes with a countdown in
 * the header itself (Undo in place, no confirm), a narrow + adds a column, + Column header adds a
 * header. Every change is handed up whole as `MatrixHeader[]`; this file writes nothing.
 *
 * Every cell, header and footer renderer is a module-level component that reads its key off the
 * column id, so rebuilding the column list after a header change never remounts an input that is
 * being typed into.
 */
import * as React from 'react';
import type { CellContext, ColumnDef, HeaderContext } from '@tanstack/react-table';
import { GripVertical, Plus, Undo2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { compareMoney, formatMyrExact, formatQty, isDecimalString, multiplyMoney } from '../../_shared/lib/money';
import {
  hasPair,
  moveCol,
  moveHeader,
  renameKey,
  sumCells,
  anyCell,
  type MatrixFooter,
  type MatrixHeader,
} from '../../_shared/lib/quotationMatrix';
import type { QuotationFeedbackRow, StagedQuotationLine } from '../../_shared/types/project.types';
import { draftCells, isInlineChecked } from './quotationLineDraft';

/** The grid's row, as `QuotationLinesGrid` builds it. */
export interface MatrixGridRow {
  key: string;
  index: number;
  staged: StagedQuotationLine;
}

/** A header or column being removed: the countdown shown in its header. */
export interface PendingRemoval {
  key: string;
  label: string;
  /** Epoch ms when the removal commits. */
  commitAt: number;
  /** How many lines hold a quantity under it. */
  lines: number;
}

export interface MatrixGridContextValue {
  headers: MatrixHeader[];
  editing: boolean;
  /** The header can be edited: an editable version, in an edit session. */
  editable: boolean;
  /** A column write is on its way: every header control waits for it. */
  saving: boolean;
  footer: MatrixFooter;
  change: (next: MatrixHeader[]) => void;
  addCol: (headerKey: string) => void;
  addHeader: () => void;
  pending: PendingRemoval | null;
  startRemoval: (key: string) => void;
  undoRemoval: () => void;
  /** The label input to focus once it exists (a header or column just added). */
  focusKey: string | null;
  clearFocusKey: () => void;
  updateCell: (rowKey: string, leafKey: string, value: string) => void;
  pasteAt: (rowKey: string, leafKey: string, text: string) => void;
  labelOf: (row: MatrixGridRow) => string;
  /** Open feedback pointing at this cell (amber corner, mock frame 5). */
  cellNotes: (row: MatrixGridRow, leafKey: string) => QuotationFeedbackRow[];
  stockChip: (row: MatrixGridRow, quantity: string) => React.ReactNode;
}

const MatrixGridContext = React.createContext<MatrixGridContextValue | null>(null);

export function MatrixGridProvider({
  value,
  children,
}: {
  value: MatrixGridContextValue;
  children: React.ReactNode;
}) {
  return <MatrixGridContext.Provider value={value}>{children}</MatrixGridContext.Provider>;
}

function useMatrix(): MatrixGridContextValue {
  const value = React.useContext(MatrixGridContext);
  if (!value) throw new Error('A quantity column rendered outside the quotation grid');
  return value;
}

// ---------------------------------------------------------------------------- ids

const LEAF = 'mx-cell:';
const GROUP = 'mx-head:';
const ADD_COL = 'mx-add:';
const PAIR_QTY = 'mx-pair-qty:';
const PAIR_RM = 'mx-pair-rm:';
const ADD_HEADER = 'mx-add-header';
const TOTAL_QTY = 'mx-total-qty';

function keyOf(id: string, prefix: string): string {
  return id.startsWith(prefix) ? id.slice(prefix.length) : '';
}

export function leafColumnId(key: string): string {
  return `${LEAF}${key}`;
}

// ------------------------------------------------------------------------ formats

/** `1,522`: a quantity with its trailing zeros dropped and its thousands grouped. */
export function groupedQty(value: string | null | undefined): string {
  const text = formatQty(value);
  const [whole, fraction] = text.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return fraction ? `${grouped}.${fraction}` : grouped;
}

/** `10,800.00`: money under a heading that already says RM. */
export function plainMoney(value: string | null | undefined): string {
  return formatMyrExact(value).replace(/^RM /, '');
}

function isZero(value: string): boolean {
  return compareMoney(value, '0') === 0;
}

function notesTitle(notes: QuotationFeedbackRow[]): string {
  return notes.map((note) => note.note || 'Customer feedback').join('\n');
}

/** The amber corner on a cell with open customer feedback (mock frame 5). */
function FeedbackCorner({ notes }: { notes: QuotationFeedbackRow[] }) {
  if (notes.length === 0) return null;
  return (
    <span
      role="img"
      aria-label="Customer feedback"
      title={notesTitle(notes)}
      data-testid="matrix-feedback-corner"
      className="absolute end-0 top-0 size-0 border-s-[8px] border-t-[8px] border-s-transparent border-t-warning"
    />
  );
}

// ---------------------------------------------------------------------- countdown

function useSecondsLeft(commitAt: number | null): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (commitAt === null) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [commitAt]);
  return commitAt === null ? 0 : Math.max(0, Math.ceil((commitAt - now) / 1000));
}

/** The removal countdown, rendered in the header it removes (R11, mock frame 2). */
function RemovalCountdown({ compact }: { compact: boolean }) {
  const matrix = useMatrix();
  const pending = matrix.pending;
  const seconds = useSecondsLeft(pending?.commitAt ?? null);
  if (!pending) return null;
  const title =
    pending.lines > 0
      ? `${pending.lines} ${pending.lines === 1 ? 'line loses' : 'lines lose'} the quantities under it`
      : undefined;
  return (
    <div
      className="flex min-w-0 items-center justify-center gap-1 text-destructive normal-case"
      data-testid="matrix-removal-countdown"
      title={title}
    >
      <span role="timer" className="min-w-0 truncate tabular-nums">
        {compact ? `${seconds}s` : `${pending.label} · removing in ${seconds}s`}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-6 shrink-0 px-1.5"
        aria-label={`Undo removing ${pending.label}`}
        onClick={matrix.undoRemoval}
      >
        {compact ? <Undo2 className="size-3.5" aria-hidden /> : 'Undo'}
      </Button>
    </div>
  );
}

// ------------------------------------------------------------------- label editor

type DragKind = 'header' | 'col';
const DRAG_TYPE = 'application/x-sorento-matrix';

/**
 * One header or column label: an inline text box on an editable version, committed on Enter or
 * blur (a blank label is refused and reverts), plain text otherwise. The grip drags it, and the
 * arrow keys move it, among its siblings; the x starts the removal countdown.
 */
function LabelEditor({
  itemKey,
  label,
  kind,
  headerKey,
  canAddCol = false,
}: {
  itemKey: string;
  label: string;
  kind: DragKind;
  /** The header a column sits under (a header's own key for a header). */
  headerKey: string;
  /** A header with no columns offers its first one here. */
  canAddCol?: boolean;
}) {
  const matrix = useMatrix();
  const [value, setValue] = React.useState(label);
  const [over, setOver] = React.useState(false);
  React.useEffect(() => setValue(label), [label]);
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  React.useEffect(() => {
    if (matrix.focusKey === itemKey && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
      matrix.clearFocusKey();
    }
  }, [matrix, itemKey]);

  // A countdown only ever shows where it can be undone: in edit mode, with a handler.
  if (matrix.editable && matrix.pending?.key === itemKey) {
    return <RemovalCountdown compact={kind === 'col'} />;
  }

  if (!matrix.editable) {
    return (
      <span className="block truncate text-center" title={label}>
        {label}
      </span>
    );
  }

  const busy = matrix.saving || matrix.pending !== null;
  const commit = () => {
    const next = value.trim();
    if (!next) {
      setValue(label);
      return;
    }
    if (next !== label) matrix.change(renameKey(matrix.headers, itemKey, next));
  };
  const siblings =
    kind === 'header'
      ? matrix.headers.map((header) => header.key)
      : (matrix.headers.find((header) => header.key === headerKey)?.cols ?? []).map((col) => col.key);
  const moveTo = (target: string) => {
    if (!target || target === itemKey) return;
    matrix.change(
      kind === 'header'
        ? moveHeader(matrix.headers, itemKey, target)
        : moveCol(matrix.headers, itemKey, target),
    );
  };
  const dragValue = `${kind}:${headerKey}:${itemKey}`;

  return (
    <div className="flex w-full min-w-0 flex-col items-stretch gap-0.5 normal-case">
      <div
        role="group"
        aria-label={label}
        className={cn('flex w-full min-w-0 items-center gap-0.5 rounded-sm', over && 'ring-2 ring-primary')}
        onDragOver={(event) => {
          if (!event.dataTransfer.types.includes(DRAG_TYPE)) return;
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          setOver(false);
          const [dragKind, dragHeader, dragKey] = event.dataTransfer.getData(DRAG_TYPE).split(':');
          if (dragKind !== kind || (kind === 'col' && dragHeader !== headerKey)) return;
          event.preventDefault();
          if (!busy) moveTo(dragKey);
        }}
      >
        <button
          type="button"
          draggable={!busy}
          disabled={busy}
          aria-label={`Move ${label}`}
          title="Drag to reorder"
          className="shrink-0 cursor-grab text-muted-foreground disabled:cursor-default"
          onDragStart={(event) => {
            event.dataTransfer.setData(DRAG_TYPE, dragValue);
            event.dataTransfer.effectAllowed = 'move';
          }}
          onKeyDown={(event) => {
            const at = siblings.indexOf(itemKey);
            if (event.key === 'ArrowLeft' && at > 0) {
              event.preventDefault();
              moveTo(siblings[at - 1]);
            } else if (event.key === 'ArrowRight' && at >= 0 && at < siblings.length - 1) {
              event.preventDefault();
              moveTo(siblings[at + 1]);
            }
          }}
        >
          <GripVertical className="size-3" aria-hidden />
        </button>
        <Input
          ref={inputRef}
          variant="sm"
          value={value}
          maxLength={60}
          disabled={matrix.saving}
          aria-label={kind === 'header' ? `Column header ${label}` : `Column ${label}`}
          title={value}
          className="h-7 w-full min-w-0 flex-1 px-1 text-center text-xs font-medium"
          onChange={(event) => setValue(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              event.currentTarget.blur();
            } else if (event.key === 'Escape') {
              setValue(label);
            }
          }}
        />
        <button
          type="button"
          disabled={busy}
          aria-label={`Remove ${label}`}
          title="Remove"
          className="shrink-0 text-muted-foreground hover:text-destructive disabled:opacity-50"
          onClick={() => matrix.startRemoval(itemKey)}
        >
          <X className="size-3" aria-hidden />
        </button>
      </div>
      {canAddCol && (
        <button
          type="button"
          disabled={busy}
          className="text-2xs text-primary hover:underline disabled:opacity-50"
          onClick={() => matrix.addCol(headerKey)}
        >
          + Column
        </button>
      )}
    </div>
  );
}

// -------------------------------------------------------------------------- headers

function GroupHeader({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const key = keyOf(column.id, GROUP);
  const header = matrix.headers.find((row) => row.key === key);
  if (!header) return null;
  return <LabelEditor itemKey={key} label={header.label} kind="header" headerKey={key} />;
}

function LeafHeader({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const key = keyOf(column.id, LEAF);
  const own = matrix.headers.find((row) => row.key === key);
  // A header with no columns is its own quantity column: its label is the header's.
  if (own) return <LabelEditor itemKey={key} label={own.label} kind="header" headerKey={key} canAddCol />;
  const parent = matrix.headers.find((row) => row.cols.some((col) => col.key === key));
  const col = parent?.cols.find((row) => row.key === key);
  if (!parent || !col) return null;
  return <LabelEditor itemKey={key} label={col.label} kind="col" headerKey={parent.key} />;
}

function AddColHeader({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const key = keyOf(column.id, ADD_COL);
  const header = matrix.headers.find((row) => row.key === key);
  return (
    <Button
      type="button"
      mode="icon"
      variant="ghost"
      size="sm"
      className="size-6 text-primary"
      disabled={matrix.saving || matrix.pending !== null}
      aria-label={`Add a column under ${header?.label ?? 'this header'}`}
      title="Add a column"
      onClick={() => matrix.addCol(key)}
    >
      <Plus className="size-3.5" aria-hidden />
    </Button>
  );
}

function AddHeaderHeader() {
  const matrix = useMatrix();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-auto w-full whitespace-normal px-1 py-0.5 text-xs text-primary normal-case"
      disabled={matrix.saving || matrix.pending !== null}
      onClick={matrix.addHeader}
    >
      + Column header
    </Button>
  );
}

// ---------------------------------------------------------------------------- cells

function rowCells(row: MatrixGridRow) {
  return draftCells(row.staged.draft) ?? {};
}

function LeafCell({ row: tableRow, column }: CellContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const row = tableRow.original;
  const key = keyOf(column.id, LEAF);
  const value = rowCells(row)[key] ?? '';
  const notes = matrix.cellNotes(row, key);
  const removed = row.staged.removed;

  if (!matrix.editing || removed) {
    return (
      <span className="relative block min-h-5 text-end text-sm tabular-nums" title={notes.length ? notesTitle(notes) : undefined}>
        {value.trim() ? groupedQty(value) : ''}
        <FeedbackCorner notes={notes} />
      </span>
    );
  }

  const text = value.trim();
  const invalid = text !== '' && (!isDecimalString(text) || compareMoney(text, '0') === -1);
  return (
    <div className="relative">
      <Input
        variant="sm"
        value={value}
        inputMode="decimal"
        aria-label={`Qty on ${matrix.labelOf(row)}, ${column.columnDef.meta?.headerTitle ?? 'column'}`}
        aria-invalid={invalid || undefined}
        title={invalid ? 'Must be a number, 0 or more' : notes.length ? notesTitle(notes) : undefined}
        data-matrix-cell={key}
        className="w-full px-1 text-end tabular-nums"
        onChange={(event) => matrix.updateCell(row.key, key, event.target.value)}
        onPaste={(event) => {
          const pasted = event.clipboardData.getData('text/plain');
          if (!/[\t\n]/.test(pasted.replace(/\n$/, ''))) return;
          event.preventDefault();
          matrix.pasteAt(row.key, key, pasted);
        }}
      />
      <FeedbackCorner notes={notes} />
    </div>
  );
}

function headerCols(matrix: MatrixGridContextValue, headerKey: string): string[] {
  return (matrix.headers.find((row) => row.key === headerKey)?.cols ?? []).map((col) => col.key);
}

function PairQtyCell({ row: tableRow, column }: CellContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const row = tableRow.original;
  const keys = headerCols(matrix, keyOf(column.id, PAIR_QTY));
  const cells = rowCells(row);
  if (!anyCell(cells, keys)) return <span className="block text-center text-sm">-</span>;
  return <span className="block text-end text-sm tabular-nums">{groupedQty(sumCells(cells, keys))}</span>;
}

function PairRmCell({ row: tableRow, column }: CellContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const row = tableRow.original;
  const keys = headerCols(matrix, keyOf(column.id, PAIR_RM));
  const cells = rowCells(row);
  if (!anyCell(cells, keys) || isInlineChecked(row.staged.draft.is_rate_only)) {
    return <span className="block text-center text-sm">-</span>;
  }
  const amount = multiplyMoney(sumCells(cells, keys), (row.staged.draft.unit_price ?? '').trim() || '0') ?? '0';
  return <span className="block text-end text-xs tabular-nums">{plainMoney(amount)}</span>;
}

function TotalQtyCell({ row: tableRow }: CellContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const row = tableRow.original;
  const quantity = sumCells(rowCells(row));
  return (
    <div className="flex flex-col items-end gap-1">
      <span className="text-sm font-medium tabular-nums">{groupedQty(quantity)}</span>
      {matrix.stockChip(row, quantity)}
    </div>
  );
}

function EmptyCell() {
  return null;
}

// --------------------------------------------------------------------------- footer

/** Two stacked lines per footer cell, so the "Total qty" and "Total (RM)" rows line up. */
function FooterLines({ qty, rm }: { qty?: string; rm?: string }) {
  return (
    <div className="flex flex-col text-end text-xs tabular-nums">
      <span className="h-5 leading-5">{qty ?? ''}</span>
      <span className="h-5 leading-5">{rm ?? ''}</span>
    </div>
  );
}

function qtyOrBlank(value: string | undefined): string {
  return value && !isZero(value) ? groupedQty(value) : '';
}

function LabelFooter() {
  return (
    <div className="flex flex-col text-xs">
      <span className="h-5 leading-5">Total qty</span>
      <span className="h-5 leading-5">Total (RM)</span>
    </div>
  );
}

function LeafFooter({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  return <FooterLines qty={qtyOrBlank(matrix.footer.leafQty[keyOf(column.id, LEAF)])} />;
}

function PairQtyFooter({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  return <FooterLines qty={qtyOrBlank(matrix.footer.pairQty[keyOf(column.id, PAIR_QTY)])} />;
}

function PairRmFooter({ column }: HeaderContext<MatrixGridRow, unknown>) {
  const matrix = useMatrix();
  const value = matrix.footer.pairAmount[keyOf(column.id, PAIR_RM)];
  return <FooterLines rm={value ? plainMoney(value) : ''} />;
}

function TotalQtyFooter() {
  const matrix = useMatrix();
  return <FooterLines qty={groupedQty(matrix.footer.totalQty)} />;
}

/** The Amount column's footer: the scope total, on the Total (RM) line. */
export function MatrixAmountFooterLines({ total }: { total: string | null }) {
  return <FooterLines rm={total === null ? '-' : plainMoney(total)} />;
}

// -------------------------------------------------------------------------- columns

const NUMERIC = 'px-1 align-top';

/** A leaf column's narrowest width while its label is an input: room for grip, ~8 characters, x. */
export const EDIT_LEAF_MIN_WIDTH = 104;
const EDIT_LEAF_MAX_WIDTH = 200;

/**
 * A leaf column's width. Read: a number fits 72px. Edit: the label is an input between a grip
 * and an x, so the column grows with the label (about 7px a character at text-xs, plus 44px for
 * the grip, the x and padding), never under `EDIT_LEAF_MIN_WIDTH`.
 */
export function leafColumnWidth(label: string, editable: boolean, rowSpanHeader = false): number {
  if (!editable) return rowSpanHeader ? 96 : 72;
  const fit = 44 + label.trim().length * 7;
  return Math.min(EDIT_LEAF_MAX_WIDTH, Math.max(EDIT_LEAF_MIN_WIDTH + (rowSpanHeader ? 8 : 0), fit));
}

function leafColumn(
  key: string,
  title: string,
  label: string,
  editable: boolean,
  rowSpanHeader = false,
): ColumnDef<MatrixGridRow> {
  const size = leafColumnWidth(label, editable, rowSpanHeader);
  return {
    id: leafColumnId(key),
    header: LeafHeader,
    cell: LeafCell,
    footer: LeafFooter,
    size,
    minSize: editable ? EDIT_LEAF_MIN_WIDTH : 56,
    enableHiding: false,
    meta: {
      headerTitle: title,
      draggable: false,
      headerClassName: 'px-1 text-center',
      cellClassName: NUMERIC,
    },
  };
}

/**
 * The quantity columns for `headers`, in order (R7): per header its columns, then (editing) a
 * narrow +, then its Qty / RM pair when it has one; then (editing) + Column header, then Total qty.
 * The caller puts them where the single Qty column was and keeps every other column.
 */
export function buildMatrixColumns(
  headers: MatrixHeader[],
  editable: boolean,
): ColumnDef<MatrixGridRow>[] {
  const groups: ColumnDef<MatrixGridRow>[] = headers.map((header, index) => {
    if (header.cols.length === 0) return leafColumn(header.key, header.label, header.label, editable, true);
    const children: ColumnDef<MatrixGridRow>[] = header.cols.map((col) =>
      leafColumn(col.key, `${header.label} / ${col.label}`, col.label, editable),
    );
    if (editable) {
      children.push({
        id: `${ADD_COL}${header.key}`,
        header: AddColHeader,
        cell: EmptyCell,
        size: 32,
        minSize: 32,
        enableResizing: false,
        enableHiding: false,
        meta: { headerTitle: 'Add a column', draggable: false, headerClassName: 'px-0 text-center', cellClassName: 'px-0' },
      });
    }
    if (hasPair(headers, index)) {
      children.push(
        {
          id: `${PAIR_QTY}${header.key}`,
          header: 'Qty',
          cell: PairQtyCell,
          footer: PairQtyFooter,
          size: 60,
          minSize: 48,
          enableHiding: false,
          meta: { headerTitle: `${header.label} Qty`, draggable: false, headerClassName: 'px-1 text-end bg-muted/40', cellClassName: `${NUMERIC} bg-muted/30` },
        },
        {
          id: `${PAIR_RM}${header.key}`,
          header: 'RM',
          cell: PairRmCell,
          footer: PairRmFooter,
          size: 92,
          minSize: 72,
          enableHiding: false,
          meta: { headerTitle: `${header.label} RM`, draggable: false, headerClassName: 'px-1 text-end bg-muted/40', cellClassName: `${NUMERIC} bg-muted/30` },
        },
      );
    }
    return {
      id: `${GROUP}${header.key}`,
      header: GroupHeader,
      columns: children,
      enableResizing: false,
      meta: { headerTitle: header.label, draggable: false, headerClassName: 'px-1 text-center bg-primary/5' },
    };
  });

  const tail: ColumnDef<MatrixGridRow>[] = [];
  if (editable) {
    tail.push({
      id: ADD_HEADER,
      header: AddHeaderHeader,
      cell: EmptyCell,
      size: 84,
      minSize: 72,
      enableResizing: false,
      enableHiding: false,
      meta: { headerTitle: 'Add a column header', draggable: false, headerClassName: 'px-1 text-center', cellClassName: 'px-0' },
    });
  }
  tail.push({
    id: TOTAL_QTY,
    header: 'Total qty',
    cell: TotalQtyCell,
    footer: TotalQtyFooter,
    size: 84,
    minSize: 64,
    enableHiding: false,
    meta: { headerTitle: 'Total qty', draggable: false, headerClassName: 'px-1 text-end', cellClassName: NUMERIC },
  });
  return [...groups, ...tail];
}

export const MATRIX_LABEL_FOOTER = LabelFooter;
