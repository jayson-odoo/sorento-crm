'use client';

import * as React from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import { Check, CirclePlus, GripVertical, Plus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DatePicker, parseDateInput } from '@/components/ui/date-picker';
import { Input } from '@/components/ui/input';
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
import { cn } from '@/lib/utils';
import {
  changeOf,
  formatSplitDate,
  gapOf,
  groupKeyOf,
  lineShort,
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
}

type DataAttributes = { [key: `data-${string}`]: string | undefined };

const DESKTOP_ONLY = 'max-md:hidden';
const GRIP_STICKY = 'max-md:sticky max-md:left-0';
const ITEM_STICKY = 'max-md:sticky max-md:left-[28px]';

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
  { key: 'line', label: 'Line', width: 44, className: DESKTOP_ONLY },
  { key: 'soDate', label: 'SO date', width: 80, className: DESKTOP_ONLY },
  { key: 'soNo', label: 'S/O no', width: 76, className: DESKTOP_ONLY },
  { key: 'item', label: 'Item code', width: 112, className: ITEM_STICKY },
  { key: 'location', label: 'Location', width: 64, className: DESKTOP_ONLY },
  { key: 'qty', label: 'Qty', width: 52 },
  { key: 'newQty', label: 'New qty', width: 56 },
  { key: 'date', label: 'Delivery date', width: 96 },
  { key: 'newDate', label: 'New date', width: 96 },
  { key: 'changeQty', label: 'Change quantity', width: 80, change: true },
  // DD/MM/YYYY in full beside the calendar button and the widest pill (ADVANCE).
  { key: 'changeDate', label: 'Change date', width: 236, change: true },
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
const READ_ONLY_ITEM_STICKY = 'max-md:sticky max-md:left-0';
const READ_ONLY_COLUMNS = COLUMNS.filter(
  (column) => !READ_ONLY_DROPPED.has(column.key),
).map((column) =>
  column.key === 'item' ? { ...column, className: READ_ONLY_ITEM_STICKY } : column,
);

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
 * An unsplit line's CHANGE QUANTITY / CHANGE DATE cell (UAC A4): its own base qty or date as a
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

/**
 * REMARK cell: the typed remark, or the server's generated one shown muted over the empty
 * input (AC-G5). Typing replaces it; clearing brings it back.
 */
function RemarkCell({
  value,
  generated,
  label,
  onValue,
  onBlur,
}: {
  value: string;
  generated: string;
  label: string;
  onValue: (remark: string) => void;
  onBlur: () => void;
}) {
  const showGenerated = !value && Boolean(generated);
  return (
    <div className="relative">
      <Input
        variant="sm"
        data-nav-col="remark"
        aria-label={label}
        value={value}
        title={value || generated || undefined}
        onChange={(event) => onValue(event.target.value)}
        onBlur={onBlur}
      />
      {showGenerated ? (
        <span
          data-remark-generated="true"
          aria-hidden
          className="pointer-events-none absolute inset-y-0 start-2 end-2 flex items-center truncate text-xs text-muted-foreground"
        >
          {generated}
        </span>
      ) : null}
    </div>
  );
}

/** A REMARK as the read-only sheet prints it: the typed remark, else the generated one muted. */
function RemarkText({ value, generated }: { value: string; generated: string }) {
  const text = value || generated;
  return (
    <span
      className={cn('block truncate ps-2 text-start', !value && 'text-muted-foreground')}
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
  incomingRows: IncomingRow[];
  /** The draft changed this line's splits or the splits dropped on it: AutoCount's extra is stale. */
  extraStale: boolean;
  soNumber: string;
  soDate: string;
  /** More than one location on the SO: the phone shows it under the item code. */
  multiLocation: boolean;
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
  incomingRows,
  extraStale,
  soNumber,
  soDate,
  multiLocation,
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
  // Read-only rows: a line AutoCount added (it only receives) or delivered in full (UAC A3).
  const delivered = Boolean(line.deliveredInFull);
  const added = isAddedLine(line);
  const locked = added || delivered;
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
  const lineSpan = ownRows > 1 ? ownRows : undefined;
  const gap = gapOf(line);
  const top = itemTop ? 'border-t-2 border-t-muted-foreground/40' : '';
  const baseCell = cn(BASE_CELL, top, flash && 'jump-flash');

  const baseCells = (
    <>
      <TableCell
        rowSpan={lineSpan}
        className={cn(baseCell, DESKTOP_ONLY, 'tabular-nums')}
      >
        {no}
      </TableCell>
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
        className={cn(BASE_CELL, top, ITEM_STICKY, 'max-md:z-[1]')}
      >
        <span className="font-semibold">{line.itemCode}</span>
        <span className="block text-2xs text-muted-foreground md:hidden">
          {multiLocation
            ? `${lineShort(line)} · ${line.location}`
            : lineShort(line)}
        </span>
      </TableCell>
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
  // The grip and remove columns are the edit sheet's; the read-only sheet has neither.
  const emptyGrip = sheetReadOnly ? null : (
    <TableCell data-pinned="" className={gripCell} />
  );
  const emptyRemove = sheetReadOnly ? null : <TableCell className={changeCell} />;

  let body: React.ReactNode;
  if (delivered) {
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
  } else if (added) {
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
  } else if (remain && sheetReadOnly) {
    const only = splits[0];
    body = (
      <TableRow className="border-0 hover:bg-transparent">
        {baseCells}
        <TableCell className={cn(changeCell, 'tabular-nums')}>{line.baseQty}</TableCell>
        <TableCell className={changeCell}>{formatSplitDate(line.baseDate) || '-'}</TableCell>
        <TableCell className={changeCell}>
          <RemarkText
            value={only?.remark ?? ''}
            generated={line.remarkGenerated ?? ''}
          />
        </TableCell>
      </TableRow>
    );
  } else if (remain) {
    const only = splits[0];
    body = (
      <TableRow className="border-0 hover:bg-transparent">
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
          <RemarkCell
            label={`Remark, line ${no}`}
            value={only?.remark ?? ''}
            generated={line.remarkGenerated ?? ''}
            onValue={(remark) => only && handlers.remark(line, only.id, remark)}
            onBlur={handlers.fieldBlur}
          />
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
      splitRow(line, split, allOwn.indexOf(split) + 1, index === 0, false),
    );
  }

  /**
   * One split row. `origin` is the line the split belongs to (its labels, handlers and drag
   * name it); `incomingRow` = drawn under the line it sits on, with its own muted LINE cell.
   */
  function splitRow(
    origin: SplitLine,
    split: SplitDraft,
    n: number,
    first: boolean,
    incomingRow: boolean,
  ) {
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
          {incomingRow ? (
            <TableCell
              className={cn(cell, DESKTOP_ONLY, 'tabular-nums text-muted-foreground')}
            >
              {originNo}
            </TableCell>
          ) : null}
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
        {first ? baseCells : null}
        {incomingRow ? (
          <TableCell
            className={cn(cell, DESKTOP_ONLY, 'tabular-nums text-muted-foreground')}
          >
            {originNo}
          </TableCell>
        ) : null}
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
            splitRow(origin, split, n, false, true),
          )}
      {extraQty ? (
        <TableRow
          data-extra-row=""
          className="border-0 hover:bg-transparent"
        >
          {sheetReadOnly ? null : (
            <TableCell data-pinned="" className={cn(CELL, GRIP_STICKY, 'max-md:z-[1] px-0')} />
          )}
          <TableCell className={cn(CELL, DESKTOP_ONLY)} />
          <TableCell className={cn(CELL, 'tabular-nums font-semibold')}>
            {extraQty}
          </TableCell>
          <TableCell className={cn(CELL, 'tabular-nums')}>{extraDate}</TableCell>
          <TableCell className={cn(CELL, 'text-start text-muted-foreground')}>
            <span className="block truncate ps-2" title={line.extraRemark ?? undefined}>
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
  children,
}: {
  id: string;
  testId: string;
  over: boolean;
  destructive?: boolean;
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
          colSpan={COLUMNS.length}
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
    cell.matches('input, button')
      ? cell
      : cell.querySelector('input, button, [role="combobox"]')
  ) as HTMLElement | null;
  if (!el) return false;
  el.focus();
  if (el instanceof HTMLInputElement) el.select();
  return document.activeElement === el;
}

const NO_ROWS: IncomingRow[] = [];

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
  const columns = readOnly ? READ_ONLY_COLUMNS : COLUMNS;
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
      className={cn(
        'table-fixed border-separate border-spacing-0 text-xs',
        readOnly
          ? 'min-w-[1030px] max-md:min-w-[850px]'
          : 'min-w-[1180px] max-md:min-w-[1000px]',
      )}
    >
      <TableHeader className="[&_tr]:border-0">
        <TableRow className="border-0 hover:bg-transparent">
          {columns.map((column) => (
            <TableHead
              key={column.key}
              aria-label={column.aria}
              style={{ width: column.width }}
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
            </TableHead>
          ))}
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
              incomingRows={incomingRows.get(line.lineId) ?? NO_ROWS}
              extraStale={staleExtra.has(line.lineId)}
              soNumber={soNumber}
              soDate={soDate}
              multiLocation={multiLocation}
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
