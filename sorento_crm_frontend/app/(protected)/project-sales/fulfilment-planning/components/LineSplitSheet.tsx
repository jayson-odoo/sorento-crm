'use client';

import * as React from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Check, CirclePlus, GripVertical, Plus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DatePicker, parseDateInput } from '@/components/ui/date-picker';
import { Textarea } from '@/components/ui/textarea';
import {
  COARSE_HIT_TARGET_CLASS,
  PRESSED_CLASS,
} from '@/components/ui/primitive-classes';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataGridTableHeadRowCellResize } from '@/components/ui/data-grid-table';
import { cn } from '@/lib/utils';
import {
  changeOf,
  formatSplitDate,
  gapOf,
  groupKeyOf,
  readsRemain,
  splitsOf,
  type SplitDraft,
  type SplitLine,
} from '../lib/lineSplitModel';
import { ChangePill, QtyInput } from './lineSplitParts';

/**
 * OI-LINE-SPLIT v4: the one split sheet (UAC A2 to A12, F1; mock v4
 * `documentation/mockups/OI-LINE-SPLIT/index.html`). Every open line of the SO in one table,
 * one `<tbody>` per line (its drop target), a split's rows stacked under its line with the
 * line's own cells merged across them. The dialog owns the state, the drag context and Save;
 * this file only draws and reports edits.
 */

/** What a grip or a "N left" chip carries into a drag. */
export type DragSource =
  | { kind: 'split'; lineId: string; splitId: string }
  | { kind: 'line'; lineId: string; splitId: string }
  | { kind: 'rest'; lineId: string };

export const DROP_NEW = 'drop:new';
export const DROP_CANCEL = 'drop:cancel';
export const lineDropId = (lineId: string) => `line:${lineId}`;

/**
 * FULFIL-SO-REMARK (AC-9): the line ids a `Mockup` badge sits on, provided by the Confirm guide
 * only when the chosen lines of the order mix mockup and actual lines. Empty everywhere else.
 */
export const MockupLinesContext = React.createContext<ReadonlySet<string>>(new Set());

/** The id the focus helpers find a split's date input by. */
export const dateInputId = (splitId: string) => `split-date-${splitId}`;

/** A line AutoCount added in the pending change: nothing of its own to split (base 0). */
export function isAddedLine(line: SplitLine): boolean {
  return !line.baseQty && line.splits.length === 0 && !line.deliveredInFull;
}

export interface SheetDrag {
  source: DragSource;
  groupKey: string;
}

export interface SheetHandlers {
  /** An unsplit line's value cell clicked or typed on (`typed` = the key, put into the cell). */
  open: (line: SplitLine, cell: 'qty' | 'date', typed?: string) => void;
  qty: (line: SplitLine, splitId: string, qty: number) => void;
  date: (line: SplitLine, splitId: string, iso: string | null) => void;
  remark: (line: SplitLine, splitId: string, remark: string) => void;
  add: (line: SplitLine) => void;
  remove: (line: SplitLine, splitId: string) => void;
  fieldBlur: () => void;
  /**
   * OI-SPLIT-GUIDE (UAC F26): the REMARK of a saved line whose remark lives in its saved
   * decision (`SplitLine.remarkInDraft`), never as a one-row split.
   */
  lineRemark?: (line: SplitLine, remark: string) => void;
}

type DataAttributes = { [key: `data-${string}`]: string | undefined };

const DESKTOP_ONLY = 'max-md:hidden';
const GRIP_STICKY = 'max-md:sticky max-md:left-0';
const ITEM_STICKY = 'max-md:sticky max-md:left-[28px]';
/** With no grip column (read-only, or no drag) the item column pins at the left edge. */
const NO_GRIP_ITEM_STICKY = 'max-md:sticky max-md:left-0';

/**
 * Fixed widths except REMARK, which takes the rest: the sheet fills the 1240px page at 1280 with
 * no sideways scroll, and scrolls sideways only below its 1180px minimum.
 */
const COLUMNS: Array<{
  key: string;
  label: string;
  width?: number;
  className?: string;
  change?: boolean;
  aria?: string;
}> = [
  { key: 'grip', label: '', width: 28, className: GRIP_STICKY, aria: 'Drag' },
  // No Line column (OI-SPLIT-GUIDE UAC F21, owner ruling): a line's number stays internal
  // (keys, test ids, aria labels, the save body); the item and its rows tell lines apart.
  { key: 'soDate', label: 'SO date', width: 80, className: DESKTOP_ONLY },
  { key: 'soNo', label: 'S/O no', width: 76, className: DESKTOP_ONLY },
  { key: 'item', label: 'Item code', width: 112, className: ITEM_STICKY },
  { key: 'location', label: 'Location', width: 64, className: DESKTOP_ONLY },
  { key: 'qty', label: 'Qty', width: 52 },
  { key: 'newQty', label: 'New qty', width: 56 },
  { key: 'date', label: 'Delivery date', width: 96 },
  { key: 'newDate', label: 'New date', width: 96 },
  // OI-SPLIT-CONFIRM-POLISH (owner, 21 Oct 2026): "Breakdown", not "Change", so an untouched
  // line does not read as changed.
  { key: 'changeQty', label: 'Breakdown qty', width: 80, change: true },
  // DD/MM/YYYY in full beside the calendar button and the widest pill (ADVANCE).
  { key: 'changeDate', label: 'Breakdown date', width: 236, change: true },
  { key: 'remark', label: 'Remark', change: true },
  { key: 'balance', label: 'Balance', width: 88 },
  { key: 'remove', label: '', width: 34, aria: 'Remove' },
];

/**
 * OI-SPLIT-VIEW (UAC E1, E2): the read-only sheet the split popups draw. The same columns in the
 * same order, less the drag grip, Balance and the remove column; with no grip the item column
 * pins at the left edge on a phone.
 */
const READ_ONLY_DROPPED = new Set(['grip', 'balance', 'remove']);
const withoutColumns = (dropped: ReadonlySet<string>) =>
  COLUMNS.filter((column) => !dropped.has(column.key)).map((column) =>
    column.key === 'item' ? { ...column, className: NO_GRIP_ITEM_STICKY } : column,
  );
const READ_ONLY_COLUMNS = withoutColumns(READ_ONLY_DROPPED);
/** OI-SPLIT-CONFIRM-POLISH: the edit sheet with no drag (the guided Confirm): no grip column. */
const NO_DRAG_COLUMNS = withoutColumns(new Set(['grip']));
/**
 * PRODUCT-CHANGE-TALLY (owner, 28 Oct 2026): as the Order Inquiry email and its Excel print a
 * product AutoCount swapped, ITEM CODE the old code and NEW ITEM CODE the new one beside it,
 * the column there only when a line on the sheet was swapped.
 */
const withNewItemCode = (columns: typeof COLUMNS) =>
  columns.flatMap((column) =>
    column.key === 'item'
      ? [column, { key: 'newItem', label: 'New item code', width: 112 }]
      : [column],
  );
const COLUMNS_NEW_ITEM = withNewItemCode(COLUMNS);
const READ_ONLY_COLUMNS_NEW_ITEM = withNewItemCode(READ_ONLY_COLUMNS);
const NO_DRAG_COLUMNS_NEW_ITEM = withNewItemCode(NO_DRAG_COLUMNS);

/**
 * Never resized: the grip and remove buttons, and REMARK, which takes whatever width the other
 * columns leave (dragging any other column's edge moves it).
 */
const FIXED_COLUMNS = new Set(['grip', 'remark', 'remove']);
/** The narrowest a dragged column gets. */
const MIN_COLUMN_WIDTH = 40;
/** What REMARK keeps once columns are dragged wider: the sheet scrolls sideways instead. */
const REMARK_MIN_WIDTH = 100;

const CELL =
  'h-9 border-b border-e border-border bg-background px-1.5 py-1 text-center align-middle text-xs';
const BASE_CELL = cn(CELL, 'text-foreground');

function isoToDate(iso: string | null): Date | undefined {
  if (!iso) return undefined;
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function dateToIso(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${mm}-${dd}`;
}

/** A grip or the "N left" chip: one @dnd-kit draggable (pointer, touch long-press, keyboard). */
function DragHandle({
  id,
  source,
  label,
  disabled,
  className,
  children,
  ...rest
}: {
  id: string;
  source: DragSource;
  label: string;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
} & DataAttributes) {
  const { attributes, listeners, setNodeRef } = useDraggable({
    id,
    data: source,
    disabled,
  });
  return (
    <button
      type="button"
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onMouseDown={(event) => {
        listeners?.onMouseDown?.(event);
        // A press on a grip or chip never starts a text selection (browser pass D3).
        event.preventDefault();
      }}
      {...rest}
      aria-label={label}
      data-drag-handle=""
      className={cn(
        'touch-none select-none [-webkit-touch-callout:none] focus-visible:outline-2 focus-visible:outline-primary',
        COARSE_HIT_TARGET_CLASS,
        PRESSED_CLASS,
        disabled ? 'cursor-default opacity-40' : 'cursor-grab',
        className,
      )}
    >
      {children ?? <GripVertical aria-hidden className="size-3.5" />}
    </button>
  );
}

/** One line block: a `<tbody>` drop target (UAC A8). */
function DropBody({
  id,
  enabled,
  children,
  ...rest
}: {
  id: string;
  enabled: boolean;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLTableSectionElement> &
  DataAttributes) {
  const { setNodeRef } = useDroppable({ id, disabled: !enabled });
  return (
    <tbody
      ref={setNodeRef}
      {...rest}
      data-drop-id={id}
      data-drop-target={enabled ? 'true' : undefined}
    >
      {children}
    </tbody>
  );
}

function DateCell({
  split,
  label,
  onDate,
  onBlur,
}: {
  split: SplitDraft;
  label: string;
  onDate: (iso: string | null) => void;
  onBlur: () => void;
}) {
  // One Date per ISO day: a new object each render would reset what is being typed.
  const value = React.useMemo(
    () => isoToDate(split.deliveryDate),
    [split.deliveryDate],
  );
  const cellRef = React.useRef<HTMLDivElement | null>(null);
  const latest = React.useRef({ onDate, onBlur });
  latest.current = { onDate, onBlur };
  React.useEffect(() => {
    const cell = cellRef.current;
    if (!cell) return undefined;
    const onFocusOut = (event: FocusEvent) => {
      const input = event.target as HTMLInputElement;
      // A typed date that is not a day leaves the split with no date: "date to fill".
      if (
        input.tagName === 'INPUT' &&
        input.value.trim() &&
        !parseDateInput(input.value)
      )
        latest.current.onDate(null);
      latest.current.onBlur();
    };
    cell.addEventListener('focusout', onFocusOut);
    return () => cell.removeEventListener('focusout', onFocusOut);
  }, []);
  return (
    <div ref={cellRef} data-nav-col="date" className="min-w-0 flex-1">
      <DatePicker
        id={dateInputId(split.id)}
        ariaLabel={label}
        value={value}
        onChange={(date) => onDate(date ? dateToIso(date) : null)}
        className="min-w-0 gap-1"
        inputClassName="h-7 min-w-0 px-2 text-xs"
      />
    </div>
  );
}

/**
 * An unsplit line's BREAKDOWN QTY / BREAKDOWN DATE cell (UAC A4): its own base qty or date as a
 * plain value (base, also inside Confirm), a button that splits the line on click or a typed key.
 */
const RemainButton = ({
  label,
  cell,
  line,
  handlers,
}: {
  label: string;
  cell: 'qty' | 'date';
  line: SplitLine;
  handlers: SheetHandlers;
}) => (
  <button
    type="button"
    aria-label={label}
    data-nav-col={cell}
    data-remain={cell}
    onClick={() => handlers.open(line, cell)}
    onKeyDown={(event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.length !== 1) return;
      if (!/\d/.test(event.key) && !(cell === 'date' && event.key === '/'))
        return;
      event.preventDefault();
      event.stopPropagation();
      handlers.open(line, cell, event.key);
    }}
    className={cn(
      'h-7 w-full cursor-text select-none whitespace-nowrap rounded-md border border-dashed border-transparent text-xs text-foreground hover:border-input focus-visible:outline-2 focus-visible:outline-primary',
      cell === 'qty' && 'tabular-nums',
      COARSE_HIT_TARGET_CLASS,
      PRESSED_CLASS,
    )}
  >
    {cell === 'qty' ? line.baseQty : formatSplitDate(line.baseDate) || '-'}
  </button>
);

/** A split of another line that sits on this one: drawn in this line's block (AC-G2). */
interface IncomingRow {
  origin: SplitLine;
  split: SplitDraft;
  /** Its place among its own line's splits (the labels name it by its own line). */
  n: number;
}

/** The API's cap on one remark (`MAX_REMARK_LENGTH`). */
const REMARK_MAX = 500;

/**
 * How many rows a remark box needs: one per line of its text, a long line wrapping onto more
 * (about 32 characters to a row), at most 8. Set as `rows` so the box grows on every browser,
 * not only where CSS field-sizing works (UAC F31: iOS Safari).
 */
function remarkRows(text: string): number {
  const rows = text
    .split('\n')
    .reduce((total, line) => total + Math.max(1, Math.ceil(line.length / 32)), 0);
  return Math.min(8, Math.max(1, rows));
}

/**
 * REMARK cell (OI-SPLIT-GUIDE UAC F25, F29, F31): a wrapping text box whose VALUE is the
 * row's remark, else its default words (`generated`: the change word, or the purchasing
 * email's words for a saved line). Typing over it stores the new text and marks it edited;
 * clearing it, or typing the default back, stores nothing. A box cleared while focused stays
 * empty for fresh text, and shows the default again once left empty. At most 500 characters.
 */
function RemarkCell({
  value,
  generated,
  label,
  onValue,
  onBlur,
  edited: editedOverride,
}: {
  value: string;
  generated: string;
  label: string;
  onValue: (remark: string) => void;
  onBlur: () => void;
  /** The host's own reading of "edited" (a saved line's stored remark); else value vs default. */
  edited?: boolean;
}) {
  // What the focused box holds while the planner types (it may be empty); null otherwise.
  const [typing, setTyping] = React.useState<string | null>(null);
  const edited = editedOverride ?? (Boolean(value.trim()) && value !== generated);
  const text = typing ?? (value || generated);
  // Showing the default words (nothing stored): marked, and read muted (AC-G5).
  const showsDefault = typing === null && !value && Boolean(generated);
  return (
    <div className="flex flex-col items-stretch gap-0.5">
      <Textarea
        variant="sm"
        rows={remarkRows(text)}
        maxLength={REMARK_MAX}
        data-nav-col="remark"
        data-remark-generated={showsDefault ? 'true' : undefined}
        aria-label={label}
        value={text}
        onChange={(event) => {
          const next = event.target.value;
          if (event.target === document.activeElement) setTyping(next);
          onValue(!next.trim() || next === generated ? '' : next);
        }}
        onBlur={() => {
          setTyping(null);
          onBlur();
        }}
        className={cn(
          'min-h-7 resize-none px-2 py-1 text-start break-words whitespace-pre-wrap [field-sizing:content]',
          showsDefault && 'text-muted-foreground',
        )}
      />
      {edited ? (
        <span className="text-start text-2xs text-muted-foreground">edited</span>
      ) : null}
    </div>
  );
}

/** A REMARK as the read-only sheet prints it, wrapping: the typed remark, else the generated
 * one muted. */
function RemarkText({ value, generated }: { value: string; generated: string }) {
  const text = value || generated;
  return (
    <span
      className={cn(
        'block ps-2 text-start break-words whitespace-normal',
        !value && 'text-muted-foreground',
      )}
      title={text || undefined}
    >
      {text}
    </span>
  );
}

interface LineBlockProps {
  line: SplitLine;
  /** OI-SPLIT-VIEW (UAC E2): values as text, no grip, Balance, + Split, remove or click-to-edit. */
  readOnly: boolean;
  /** OI-SPLIT-CONFIRM-POLISH: rows and "N left" can be dragged (no grip column when not). */
  canDrag: boolean;
  incomingRows: IncomingRow[];
  /** The draft changed this line's splits or the splits dropped on it: AutoCount's extra is stale. */
  extraStale: boolean;
  soNumber: string;
  soDate: string;
  /** More than one location on the SO: the phone shows it under the item code. */
  multiLocation: boolean;
  /** A line on the sheet was swapped to another product: the New item code column shows. */
  newItemColumn: boolean;
  open: boolean;
  itemTop: boolean;
  flash: boolean;
  dimmed: boolean;
  target: boolean;
  source: boolean;
  over: boolean;
  handlers: SheetHandlers;
}

const LineBlock = React.memo(function LineBlock({
  line,
  readOnly: sheetReadOnly,
  canDrag,
  incomingRows,
  extraStale,
  soNumber,
  soDate,
  multiLocation,
  newItemColumn,
  open,
  itemTop,
  flash,
  dimmed,
  target,
  source,
  over,
  handlers,
}: LineBlockProps) {
  const no = line.lineNo ?? '';
  const mockup = React.useContext(MockupLinesContext).has(line.lineId);
  // Read-only rows: a line AutoCount added (it only receives) or delivered in full (UAC A3).
  const delivered = Boolean(line.deliveredInFull);
  const added = isAddedLine(line);
  const locked = added || delivered;
  const grip = !sheetReadOnly && canDrag;
  const remain = !locked && !open && readsRemain(line);
  const allOwn = locked ? [] : splitsOf(line);
  // Variant B (AC-G2): a split dropped on another line is drawn under that line, so this
  // block holds the splits that stay on it (or on a new line, or cancel) ...
  const splits = allOwn.filter(
    (split) =>
      split.isCancel ||
      !split.sitsOnLineId ||
      split.sitsOnLineId === line.lineId,
  );
  // ... then other lines' splits sitting on it, then AutoCount's extra (AC-G3).
  const extraQty =
    !delivered && !extraStale && line.extraQty ? line.extraQty : null;
  const ownRows = remain || locked ? 1 : Math.max(1, splits.length);
  const rows =
    ownRows + (delivered ? 0 : incomingRows.length) + (extraQty ? 1 : 0);
  const span = rows > 1 ? rows : undefined;
  const gap = gapOf(line);
  const top = itemTop ? 'border-t-2 border-t-muted-foreground/40' : '';
  const baseCell = cn(BASE_CELL, top, flash && 'jump-flash');

  const baseCells = (
    <>
      <TableCell rowSpan={span} className={cn(baseCell, DESKTOP_ONLY)}>
        {soDate}
      </TableCell>
      <TableCell rowSpan={span} className={cn(baseCell, DESKTOP_ONLY)}>
        {soNumber}
      </TableCell>
      {/* Pinned at 375: an opaque cell in every row state, so no flash on it (the
          flash fades its background to transparent). */}
      <TableCell
        rowSpan={span}
        data-pinned=""
        className={cn(
          BASE_CELL,
          top,
          grip ? ITEM_STICKY : NO_GRIP_ITEM_STICKY,
          'max-md:z-[1]',
        )}
      >
        <span className="font-semibold" data-testid={`item-code-${no}`}>
          {line.wasItemCode || line.itemCode}
        </span>
        {mockup ? (
          <Badge
            variant="warning"
            appearance="light"
            size="sm"
            className="ms-1.5"
            data-testid="confirm-guide-mockup-badge"
          >
            Mockup
          </Badge>
        ) : null}
        {multiLocation ? (
          <span className="block text-2xs text-muted-foreground md:hidden">
            {line.location}
          </span>
        ) : null}
      </TableCell>
      {newItemColumn ? (
        <TableCell
          rowSpan={span}
          data-testid={`new-item-code-${no}`}
          className={cn(baseCell, 'font-semibold')}
        >
          {line.wasItemCode ? line.itemCode : ''}
        </TableCell>
      ) : null}
      <TableCell rowSpan={span} className={cn(baseCell, DESKTOP_ONLY)}>
        {line.location}
      </TableCell>
      <TableCell rowSpan={span} className={cn(baseCell, 'tabular-nums')}>
        {delivered ? (line.deliveredQty ?? 0) : added ? 0 : line.baseQty}
      </TableCell>
      <TableCell
        rowSpan={span}
        data-testid={`new-qty-${no}`}
        className={cn(baseCell, 'tabular-nums')}
      >
        {line.newQty ?? ''}
      </TableCell>
      <TableCell rowSpan={span} className={baseCell}>
        <span>{added ? '-' : formatSplitDate(line.baseDate)}</span>
        {line.stale ? (
          <Badge
            variant="warning"
            appearance="light"
            size="sm"
            className="mt-0.5"
          >
            AutoCount changed
          </Badge>
        ) : null}
      </TableCell>
      <TableCell
        rowSpan={span}
        data-testid={`new-date-${no}`}
        className={baseCell}
      >
        {formatSplitDate(line.newDate)}
      </TableCell>
    </>
  );

  const addButton = locked || sheetReadOnly ? null : (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-6 px-1.5"
      aria-label={`Add a split to line ${no}`}
      onClick={() => handlers.add(line)}
    >
      <Plus aria-hidden />
      Split
    </Button>
  );

  const balance = sheetReadOnly ? null : (
    <TableCell
      rowSpan={span}
      data-testid={`balance-${no}`}
      className={cn(baseCell)}
    >
      {locked ? null : (
        <div className="flex flex-col items-center gap-1">
          {remain ? null : gap === 0 ? (
            <span className="inline-flex items-center gap-0.5 font-semibold tabular-nums text-success">
              0
              <Check aria-hidden className="size-3.5" />
            </span>
          ) : gap > 0 && !grip ? (
            <span className="inline-flex items-center whitespace-nowrap rounded-full border border-warning/40 bg-warning/10 px-2 py-px font-semibold tabular-nums text-warning">
              {`${gap} left`}
            </span>
          ) : gap > 0 ? (
            <DragHandle
              id={`drag-rest:${line.lineId}`}
              source={{ kind: 'rest', lineId: line.lineId }}
              label={`Drag the ${gap} left of line ${no}`}
              className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-full border border-warning/40 bg-warning/10 py-px ps-1 pe-2 font-semibold tabular-nums text-warning"
            >
              <GripVertical aria-hidden className="size-3" />
              {`${gap} left`}
            </DragHandle>
          ) : (
            <span className="whitespace-nowrap font-semibold tabular-nums text-destructive">
              {`${-gap} over`}
            </span>
          )}
          {addButton}
        </div>
      )}
    </TableCell>
  );

  const gripCell = cn(CELL, top, GRIP_STICKY, 'max-md:z-[1] px-0');
  const changeCell = cn(CELL, top);
  // The grip and remove columns are the edit sheet's; the read-only sheet has neither, and a
  // sheet with no drag has no grip.
  const emptyGrip = !grip ? null : (
    <TableCell data-pinned="" className={gripCell} />
  );
  const emptyRemove = sheetReadOnly ? null : <TableCell className={changeCell} />;

  // OI-SPLIT-GUIDE (UAC F3, F18, F25): the guided Confirm's words for the line's saved
  // decision (only the guide sets them), and the planner's own remark over them.
  const savedRemark = line.savedRemark || null;
  const ownRemark = line.ownRemark || '';
  let body: React.ReactNode;
  if (delivered && line.remarkInDraft) {
    // UAC F28: Confirm drops a line delivered in full, so nothing of it reaches purchasing:
    // its remark stays read-only and the row says why.
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {emptyGrip}
        {baseCells}
        <TableCell colSpan={2} className={cn(changeCell, 'ps-2 text-start')}>
          <span className="text-2xs text-muted-foreground">
            Delivered in full: nothing goes to purchasing
          </span>
        </TableCell>
        <TableCell className={changeCell}>
          <RemarkText value={ownRemark} generated={savedRemark ?? ''} />
        </TableCell>
        {balance}
        {emptyRemove}
      </TableRow>
    );
  } else if (delivered && !savedRemark) {
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {emptyGrip}
        {baseCells}
        <TableCell colSpan={2} className={cn(changeCell, 'ps-2 text-start')}>
          <span className="text-2xs text-muted-foreground">
            {`Delivered ${line.deliveredQty ?? 0}`}
          </span>
        </TableCell>
        <TableCell className={changeCell} />
        {balance}
        {emptyRemove}
      </TableRow>
    );
  } else if (added || delivered) {
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {emptyGrip}
        {baseCells}
        <TableCell colSpan={2} className={changeCell} />
        <TableCell className={changeCell}>
          {added && !sheetReadOnly && line.remarkInDraft && handlers.lineRemark ? (
            // A line AutoCount added (nothing of its own to split) still takes a remark when
            // it carries a saved decision: kept in that decision, as any saved line's is.
            <RemarkCell
              label={`Remark, line ${no}`}
              value={ownRemark}
              generated={savedRemark ?? ''}
              edited={line.remarkEdited}
              onValue={(remark) => handlers.lineRemark?.(line, remark)}
              onBlur={handlers.fieldBlur}
            />
          ) : savedRemark || ownRemark ? (
            <RemarkText value={ownRemark || savedRemark || ''} generated="" />
          ) : null}
        </TableCell>
        {balance}
        {emptyRemove}
      </TableRow>
    );
  } else if (remain && sheetReadOnly) {
    const only = splits[0];
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {baseCells}
        <TableCell className={cn(changeCell, 'tabular-nums')}>{line.baseQty}</TableCell>
        <TableCell className={changeCell}>{formatSplitDate(line.baseDate) || '-'}</TableCell>
        <TableCell className={changeCell}>
          <RemarkText
            value={ownRemark || savedRemark || only?.remark || ''}
            generated={line.remarkGenerated ?? ''}
          />
        </TableCell>
      </TableRow>
    );
  } else if (remain) {
    const only = splits[0];
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {grip ? (
        <TableCell data-pinned="" className={gripCell}>
          <DragHandle
            id={`drag-line:${line.lineId}`}
            source={{
              kind: 'line',
              lineId: line.lineId,
              splitId: only?.id ?? '',
            }}
            label={`Drag line ${no}`}
            disabled={!only?.qty}
            className="inline-flex h-7 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          />
        </TableCell>
        ) : null}
        {baseCells}
        <TableCell className={changeCell}>
          <RemainButton
            label={`Split line ${no} quantity`}
            cell="qty"
            line={line}
            handlers={handlers}
          />
        </TableCell>
        <TableCell className={changeCell}>
          <RemainButton
            label={`Split line ${no} date`}
            cell="date"
            line={line}
            handlers={handlers}
          />
        </TableCell>
        <TableCell className={changeCell}>
          {line.remarkInDraft && handlers.lineRemark ? (
            // UAC F26: a saved line's remark is kept in its saved decision, never a split.
            <RemarkCell
              label={`Remark, line ${no}`}
              value={ownRemark}
              generated={savedRemark ?? line.remarkGenerated ?? ''}
              edited={line.remarkEdited}
              onValue={(remark) => handlers.lineRemark?.(line, remark)}
              onBlur={handlers.fieldBlur}
            />
          ) : (
            <RemarkCell
              label={`Remark, line ${no}`}
              // OI-SPLIT-GEAR-REMARK: a stored split remark wins, then the server's words, then
              // the line's confirmed remark (display only, never copied into the split state).
              value={only?.remark || (savedRemark ? '' : line.ownRemark) || ''}
              generated={savedRemark ?? line.remarkGenerated ?? ''}
              onValue={(remark) =>
                only &&
                handlers.remark(
                  line,
                  only.id,
                  // Typing the confirmed remark back stores nothing (H8), unless a split remark
                  // was stored for the line as loaded: then X replaces it (H9).
                  line.ownRemark && !savedRemark && !line.remarkStored && remark === line.ownRemark
                    ? ''
                    : remark,
                )
              }
              onBlur={handlers.fieldBlur}
            />
          )}
        </TableCell>
        {balance}
        <TableCell className={changeCell} />
      </TableRow>
    );
  } else if (splits.length === 0) {
    // Every split of the line sits on another line: its own row keeps the base cells.
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {emptyGrip}
        {baseCells}
        <TableCell colSpan={2} className={changeCell} />
        <TableCell className={changeCell} />
        {balance}
        {emptyRemove}
      </TableRow>
    );
  } else {
    body = splits.map((split, index) =>
      splitRow(line, split, allOwn.indexOf(split) + 1, index === 0),
    );
  }

  /**
   * One split row. `origin` is the line the split belongs to (its labels, handlers and drag
   * name it); a split sitting on another line is drawn under that line.
   */
  function splitRow(origin: SplitLine, split: SplitDraft, n: number, first: boolean) {
    const originNo = origin.lineNo ?? '';
    const cell = cn(CELL, first && top);
    const word = changeOf(split, origin);
    if (sheetReadOnly) {
      return (
        <TableRow
          key={split.id}
          data-split-id={split.id}
          data-origin-line-id={origin.lineId}
          className="border-0 hover:bg-transparent"
        >
          {first ? baseCells : null}
          <TableCell className={cn(cell, 'font-semibold tabular-nums')}>
            {split.qty}
          </TableCell>
          <TableCell className={cell}>
            {split.isCancel ? (
              <ChangePill word="CANCEL" />
            ) : (
              <div className="flex items-center justify-center gap-1">
                <span className="tabular-nums">
                  {formatSplitDate(split.deliveryDate)}
                </span>
                {split.deliveryDate ? (
                  <span className="shrink-0">
                    <ChangePill word={word} />
                  </span>
                ) : null}
              </div>
            )}
          </TableCell>
          <TableCell className={cell}>
            <RemarkText value={split.remark} generated={split.remarkGenerated ?? ''} />
          </TableCell>
        </TableRow>
      );
    }
    return (
      <TableRow
        key={split.id}
        data-split-id={split.id}
        data-origin-line-id={origin.lineId}
        className="border-0 hover:bg-transparent"
      >
        {grip ? (
        <TableCell
          data-pinned=""
          className={cn(cell, GRIP_STICKY, 'max-md:z-[1] px-0')}
        >
          <DragHandle
            id={`drag-split:${split.id}`}
            source={{ kind: 'split', lineId: origin.lineId, splitId: split.id }}
            label={`Drag split ${n} of line ${originNo}`}
            disabled={!split.qty}
            data-grip-split={split.id}
            className="inline-flex h-7 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          />
        </TableCell>
        ) : null}
        {first ? baseCells : null}
        <TableCell className={cell}>
          <QtyInput
            variant="sm"
            data-nav-col="qty"
            data-qty-split={split.id}
            aria-label={`Quantity, line ${originNo} split ${n}`}
            value={split.qty}
            onValue={(qty) => handlers.qty(origin, split.id, qty)}
            onBlur={handlers.fieldBlur}
            className="text-center font-semibold tabular-nums"
          />
        </TableCell>
        <TableCell className={cell}>
          {split.isCancel ? (
            <ChangePill word="CANCEL" />
          ) : (
            <div className="flex items-center gap-1">
              <DateCell
                split={split}
                label={`Date, line ${originNo} split ${n}`}
                onDate={(iso) => handlers.date(origin, split.id, iso)}
                onBlur={handlers.fieldBlur}
              />
              {split.deliveryDate ? (
                <span className="shrink-0">
                  <ChangePill word={word} />
                </span>
              ) : null}
            </div>
          )}
        </TableCell>
        <TableCell className={cell}>
          <RemarkCell
            label={`Remark, line ${originNo} split ${n}`}
            value={split.remark}
            generated={split.remarkGenerated ?? ''}
            onValue={(remark) => handlers.remark(origin, split.id, remark)}
            onBlur={handlers.fieldBlur}
          />
        </TableCell>
        {first ? balance : null}
        <TableCell className={cn(cell, 'px-0')}>
          <Button
            type="button"
            variant="ghost"
            mode="icon"
            size="sm"
            className="size-7 text-muted-foreground"
            aria-label={`Remove split ${n} of line ${originNo}`}
            title="Remove split"
            onClick={() => handlers.remove(origin, split.id)}
          >
            <X aria-hidden />
          </Button>
        </TableCell>
      </TableRow>
    );
  }

  const extraDate = formatSplitDate(line.newDate ?? line.baseDate);
  const tail = (
    <>
      {delivered
        ? null
        : incomingRows.map(({ origin, split, n }) =>
            splitRow(origin, split, n, false),
          )}
      {extraQty ? (
        <TableRow
          data-extra-row=""
          className="border-0 hover:bg-transparent"
        >
          {grip ? (
            <TableCell data-pinned="" className={cn(CELL, GRIP_STICKY, 'max-md:z-[1] px-0')} />
          ) : null}
          <TableCell className={cn(CELL, 'tabular-nums font-semibold')}>
            {extraQty}
          </TableCell>
          <TableCell className={cn(CELL, 'tabular-nums')}>{extraDate}</TableCell>
          <TableCell className={cn(CELL, 'text-start text-muted-foreground')}>
            <span
              className="block ps-2 break-words whitespace-normal"
              title={line.extraRemark ?? undefined}
            >
              {line.extraRemark ?? ''}
            </span>
          </TableCell>
          {sheetReadOnly ? null : <TableCell className={CELL} />}
        </TableRow>
      ) : null}
    </>
  );

  if (sheetReadOnly) {
    // Nothing is dropped on a read-only sheet: a plain block, no drop target.
    return (
      <tbody
        data-testid={`split-line-${line.lineNo ?? line.lineId}`}
        data-line-id={line.lineId}
      >
        {body}
        {tail}
      </tbody>
    );
  }

  return (
    <DropBody
      id={lineDropId(line.lineId)}
      enabled={target}
      data-testid={`split-line-${line.lineNo ?? line.lineId}`}
      data-line-id={line.lineId}
      data-dimmed={dimmed ? 'true' : undefined}
      data-over={over ? 'true' : undefined}
      // The pinned cells (grip, item) stay opaque at 375 while the sheet scrolls sideways
      // under them: tints are opaque mixes over the background, and a faded line fades a
      // pinned cell's content, never the cell itself.
      className={cn(
        dimmed &&
          '[&>tr>td:not([data-pinned])]:opacity-40 [&>tr>td[data-pinned]>*]:opacity-40',
        source &&
          '[&>tr>td]:bg-[color-mix(in_oklab,var(--muted)_60%,var(--background))]',
        over &&
          '[&>tr>td]:bg-[color-mix(in_oklab,var(--primary)_10%,var(--background))]',
      )}
    >
      {body}
      {tail}
    </DropBody>
  );
});

function DropRow({
  id,
  testId,
  over,
  destructive,
  span,
  children,
}: {
  id: string;
  testId: string;
  over: boolean;
  destructive?: boolean;
  /** The sheet's column count (the New item code column adds one). */
  span: number;
  children: React.ReactNode;
}) {
  return (
    <DropBody
      id={id}
      enabled
      data-testid={testId}
      data-over={over ? 'true' : undefined}
      className={cn(over && '[&>tr>td]:bg-primary/10')}
    >
      <TableRow className="border-0 hover:bg-transparent">
        <TableCell
          colSpan={span}
          className={cn(
            'h-9 border-b border-dashed border-muted-foreground/50 bg-muted/30 ps-3.5 text-start text-xs',
            destructive ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {children}
        </TableCell>
      </TableRow>
    </DropBody>
  );
}

/** Focus a sheet cell: the input or button it is, or holds; a typed value is selected. */
export function focusCell(cell: Element | null): boolean {
  if (!cell) return false;
  const el = (
    cell.matches('input, button, textarea')
      ? cell
      : cell.querySelector('input, button, textarea, [role="combobox"]')
  ) as HTMLElement | null;
  if (!el) return false;
  el.focus();
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) el.select();
  return document.activeElement === el;
}

const NO_ROWS: IncomingRow[] = [];
const NO_LINES: SplitLine[] = [];

/** Every other line's split sitting on each line, in sheet order (variant B rows, AC-G2). */
function incomingRowsByLine(lines: SplitLine[]): Map<string, IncomingRow[]> {
  const out = new Map<string, IncomingRow[]>();
  for (const origin of lines) {
    origin.splits.forEach((split, index) => {
      if (split.isCancel || !split.sitsOnLineId) return;
      if (split.sitsOnLineId === origin.lineId) return;
      const list = out.get(split.sitsOnLineId) ?? [];
      list.push({ origin, split, n: index + 1 });
      out.set(split.sitsOnLineId, list);
    });
  }
  return out;
}

export function LineSplitSheet({
  lines,
  allLines,
  savedLines,
  soNumber,
  soDate,
  openLineIds,
  drag,
  overTarget,
  flashLineId,
  handlers,
  readOnly = false,
  canDrag = true,
}: {
  /** The lines on screen (search and filter applied), in sheet order. */
  lines: SplitLine[];
  /** Every line, in sheet order ("+N from line M"). */
  allLines: SplitLine[];
  /** The plan as loaded, to tell which lines the draft has changed. */
  savedLines: SplitLine[];
  soNumber: string;
  soDate: string;
  openLineIds: ReadonlySet<string>;
  drag: SheetDrag | null;
  overTarget: string | null;
  flashLineId: string | null;
  handlers: SheetHandlers;
  /**
   * OI-SPLIT-VIEW (UAC E1, E2): the split popups' read-only sheet. Same columns (less the grip,
   * Balance and remove), same blocks, words and extra row; values as text, no grip, "N left",
   * "+ Split", remove, click-to-edit cell or keyboard editing. The handlers are never called.
   */
  readOnly?: boolean;
  /**
   * OI-SPLIT-CONFIRM-POLISH (owner, 21 Oct 2026): false on the guided Confirm's page: no grip
   * column and a plain "N left", so nothing there can be dragged. The board gear keeps it.
   */
  canDrag?: boolean;
}) {
  const lineById = React.useMemo(
    () => new Map(allLines.map((line) => [line.lineId, line])),
    [allLines],
  );

  /**
   * Excel keys in the cells (UAC A5, A10): Ctrl/Cmd+Enter adds a split under the line,
   * Ctrl/Cmd+Backspace removes the row; Enter or Down goes to the same column one row down,
   * Shift+Enter or Up one row up. A grip or chip is the drag's own (Space picks up).
   */
  const onKeyDown = (event: React.KeyboardEvent<HTMLTableElement>) => {
    if (drag) return;
    const target = event.target as HTMLElement;
    if (target.closest('[data-drag-handle]')) return;
    // A split drawn under the line it sits on still belongs to its own line (AC-G2).
    const lineId =
      target.closest<HTMLElement>('tr[data-origin-line-id]')?.dataset
        .originLineId ??
      target.closest<HTMLElement>('tbody[data-line-id]')?.dataset.lineId;
    const line = lineId ? lineById.get(lineId) : undefined;
    if (!line) return;
    const splitId =
      target.closest<HTMLElement>('tr[data-split-id]')?.dataset.splitId;
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key === 'Enter') {
      if (isAddedLine(line) || line.deliveredInFull) return;
      event.preventDefault();
      handlers.add(line);
      return;
    }
    if (mod && event.key === 'Backspace') {
      if (!splitId) return;
      event.preventDefault();
      handlers.remove(line, splitId);
      return;
    }
    if (mod || event.altKey) return;
    const here = target.closest<HTMLElement>('[data-nav-col]');
    const col = here?.dataset.navCol;
    if (!here || !col) return;
    const down =
      (event.key === 'Enter' && !event.shiftKey) || event.key === 'ArrowDown';
    const up =
      (event.key === 'Enter' && event.shiftKey) || event.key === 'ArrowUp';
    if (!down && !up) return;
    // Enter presses a button: an unsplit line's value cell opens.
    if (event.key === 'Enter' && target.tagName === 'BUTTON') return;
    const table = event.currentTarget;
    const cells = Array.from(
      table.querySelectorAll<HTMLElement>(`[data-nav-col="${col}"]`),
    );
    const next = cells[cells.indexOf(here) + (down ? 1 : -1)];
    if (!next) return;
    event.preventDefault();
    focusCell(next);
  };
  const incomingRows = React.useMemo(() => incomingRowsByLine(allLines), [allLines]);
  const staleExtra = React.useMemo(() => {
    const sig = (line: SplitLine, rows: IncomingRow[]) =>
      JSON.stringify([
        line.splits,
        rows.map((row) => [row.origin.lineId, row.split]),
      ]);
    const savedIncoming = incomingRowsByLine(savedLines);
    const saved = new Map(
      savedLines.map((line) => [
        line.lineId,
        sig(line, savedIncoming.get(line.lineId) ?? NO_ROWS),
      ]),
    );
    const stale = new Set<string>();
    for (const line of allLines) {
      if (saved.get(line.lineId) !== sig(line, incomingRows.get(line.lineId) ?? NO_ROWS))
        stale.add(line.lineId);
    }
    return stale;
  }, [allLines, savedLines, incomingRows]);
  const multiLocation = React.useMemo(
    () => new Set(allLines.map((line) => line.location)).size > 1,
    [allLines],
  );
  const newItemColumn = React.useMemo(
    () => allLines.some((line) => Boolean(line.wasItemCode)),
    [allLines],
  );
  const columns = newItemColumn
    ? readOnly
      ? READ_ONLY_COLUMNS_NEW_ITEM
      : canDrag
        ? COLUMNS_NEW_ITEM
        : NO_DRAG_COLUMNS_NEW_ITEM
    : readOnly
      ? READ_ONLY_COLUMNS
      : canDrag
        ? COLUMNS
        : NO_DRAG_COLUMNS;
  // OI-SPLIT-CONFIRM-POLISH: columns resize by dragging a header's edge, through TanStack's
  // column sizing and the DataGrid's own handle (`components/ui/data-grid-table.tsx`
  // `DataGridTableHeadRowCellResize`, the pattern every list page uses). Only widths are
  // tracked here: the body rows stay this sheet's own merged blocks.
  const sizingColumns = React.useMemo<ColumnDef<SplitLine>[]>(
    () =>
      columns.map((column) => ({
        id: column.key,
        size: column.width ?? REMARK_MIN_WIDTH,
        minSize: MIN_COLUMN_WIDTH,
        enableResizing: !FIXED_COLUMNS.has(column.key),
      })),
    [columns],
  );
  const sizing = useReactTable<SplitLine>({
    data: NO_LINES,
    columns: sizingColumns,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });
  const headers = sizing.getHeaderGroups()[0]?.headers ?? [];
  // Once a column is dragged the sheet is at least as wide as its columns, so a wider column
  // never squeezes REMARK below its minimum; a phone leaves out the columns it hides.
  const resized = Object.keys(sizing.getState().columnSizing).length > 0;
  const total = sizing.getTotalSize();
  const phoneTotal =
    total -
    headers
      .filter((header, index) => columns[index]?.className === DESKTOP_ONLY)
      .reduce((sum, header) => sum + header.getSize(), 0);
  const lastOfDragGroup = drag
    ? lines.reduce(
        (last, line, index) =>
          groupKeyOf(line) === drag.groupKey ? index : last,
        -1,
      )
    : -1;

  return (
    <Table
      aria-label="Split delivery sheet"
      data-split-sheet=""
      data-read-only={readOnly ? 'true' : undefined}
      onKeyDown={readOnly ? undefined : onKeyDown}
      style={
        resized
          ? ({
              '--sheet-min': `${total}px`,
              '--sheet-min-phone': `${phoneTotal}px`,
            } as React.CSSProperties)
          : undefined
      }
      className={cn(
        'table-fixed border-separate border-spacing-0 text-xs',
        resized
          ? 'min-w-(--sheet-min) max-md:min-w-(--sheet-min-phone)'
          : // The New item code column (112px) widens the sheet rather than squeeze REMARK.
            newItemColumn
            ? readOnly
              ? 'min-w-[1142px] max-md:min-w-[962px]'
              : 'min-w-[1292px] max-md:min-w-[1112px]'
            : readOnly
              ? 'min-w-[1030px] max-md:min-w-[850px]'
              : 'min-w-[1180px] max-md:min-w-[1000px]',
      )}
    >
      <TableHeader className="[&_tr]:border-0">
        <TableRow className="border-0 hover:bg-transparent">
          {columns.map((column, index) => {
            const header = headers[index];
            // REMARK has no width of its own: it takes the rest.
            const width = column.width === undefined ? undefined : header?.getSize();
            return (
            <TableHead
              key={column.key}
              aria-label={column.aria}
              style={{ width }}
              className={cn(
                'sticky top-0 z-[2] h-auto border-b border-e border-border px-1.5 py-2 text-center text-2xs font-semibold uppercase leading-tight tracking-wide whitespace-normal text-foreground/70',
                column.change ? 'bg-muted' : 'bg-background',
                column.className,
                column.key === 'grip' || column.key === 'item'
                  ? 'max-md:z-[3]'
                  : null,
              )}
            >
              {column.label}
              {header?.column.getCanResize() ? (
                <DataGridTableHeadRowCellResize header={header} />
              ) : null}
            </TableHead>
            );
          })}
        </TableRow>
      </TableHeader>
      {lines.map((line, index) => {
        const key = groupKeyOf(line);
        const prev = lines[index - 1];
        const inDrag = drag !== null;
        const sameGroup = inDrag && drag.groupKey === key;
        const isSource = inDrag && drag.source.lineId === line.lineId;
        return (
          <React.Fragment key={line.lineId}>
            <LineBlock
              line={line}
              readOnly={readOnly}
              canDrag={canDrag}
              incomingRows={incomingRows.get(line.lineId) ?? NO_ROWS}
              extraStale={staleExtra.has(line.lineId)}
              soNumber={soNumber}
              soDate={soDate}
              multiLocation={multiLocation}
              newItemColumn={newItemColumn}
              open={openLineIds.has(line.lineId)}
              itemTop={!prev || prev.itemCode !== line.itemCode}
              flash={flashLineId === line.lineId}
              dimmed={inDrag && !sameGroup}
              target={sameGroup && !isSource && !line.deliveredInFull}
              source={isSource}
              over={overTarget === lineDropId(line.lineId)}
              handlers={handlers}
            />
            {index === lastOfDragGroup ? (
              <>
                <DropRow
                  id={DROP_NEW}
                  testId="drop-new-date"
                  over={overTarget === DROP_NEW}
                  span={columns.length}
                >
                  <CirclePlus
                    aria-hidden
                    className="me-1.5 inline size-3.5 align-[-2px]"
                  />
                  New date
                </DropRow>
                <DropRow
                  id={DROP_CANCEL}
                  testId="drop-cancel"
                  over={overTarget === DROP_CANCEL}
                  span={columns.length}
                  destructive
                >
                  Cancel this qty
                </DropRow>
              </>
            ) : null}
          </React.Fragment>
        );
      })}
      {lines.length === 0 ? (
        <TableBody>
          <TableRow className="border-0 hover:bg-transparent">
            <TableCell
              colSpan={columns.length}
              className="py-10 text-center text-sm text-muted-foreground"
            >
              No lines match
            </TableCell>
          </TableRow>
        </TableBody>
      ) : null}
    </Table>
  );
}
