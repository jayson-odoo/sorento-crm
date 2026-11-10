'use client';

import * as React from 'react';
import {
  type CellContext,
  type ColumnDef,
  type VisibilityState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { ChevronDown, Columns3, MoreHorizontal, Plus, StickyNote, Trash2, Undo2 } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { RichDescription } from '@/components/common/RichDescription';
import { richOneLine, richPlainText, toEditorHtml } from '@/lib/dealer-kit/rich-text';
import { toast } from '@/lib/toast';
import { useDeferredDeleteSeconds } from '@/hooks/useDeferredDeleteSeconds';
import { DEFAULT_DEFERRED_DELETE_SECONDS } from '@/services/deferredWindowService';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridScroller } from '@/components/ui/data-grid-table';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  DataGridTableDndRowHandle,
  DataGridTableDndRows,
} from '@/components/ui/data-grid-table-dnd-rows';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import type {
  QuotationFeedbackRow,
  QuotationLine,
  StagedQuotationLine,
} from '../../_shared/types/project.types';
import {
  addCol as addMatrixCol,
  addHeader as addMatrixHeader,
  appendCopy as appendMatrixCopy,
  cellsUnder,
  hasColumns,
  leafKeys,
  parsePaste,
  removeKey,
  summary,
  usedKeys,
  type MatrixHeader,
} from '../../_shared/lib/quotationMatrix';
import {
  MATRIX_LABEL_FOOTER,
  MatrixAmountFooterLines,
  MatrixGridProvider,
  buildMatrixColumns,
  type MatrixGridContextValue,
  type PendingRemoval,
} from './QuotationMatrixColumns';
import {
  formatMyrExact,
  isDecimalString,
  multiplyMoney,
} from '../../_shared/lib/money';
import {
  useProductSetLineRef,
  useQuotationLineImages,
} from '../../_shared/hooks/useProjects';
import { formatMyr } from './QuotationsPanel';
import {
  PICKED_CODE_KEY,
  cellsPatch,
  draftCells,
  emptyDraft,
  INLINE_CHECKED,
  isInlineChecked,
  isUntouched,
  lineErrors,
  totalFromDrafts,
  trimAmount,
  type LineDraft,
} from './quotationLineDraft';
import {
  QuotationLineFileCell,
  resolveLineFile,
  type LineFileKind,
  type LineFileShown,
} from './QuotationLineFileCell';
import { QuotationStockChip, SetStockChip } from './QuotationStockChip';
import { SET_OPTION_PREFIX, isSetOption } from '@/app/(protected)/scm/components/productOrSetPicker';
import { LineFlags, MinimumPriceFlag } from './QuotationLineFlags';

/** One line of the grid: the staged (or stored) line, and its true position in the scope. */
interface GridRow {
  key: string;
  /** Position in the WHOLE scope, so a search hides rows without renumbering the rest. */
  index: number;
  staged: StagedQuotationLine;
}

type MenuAction = 'below' | 'section' | 'remove';

/**
 * Everything a cell needs beyond its own row, handed down by context rather than closed over.
 *
 * The columns are a module constant on purpose: a column whose cell function is re-created on a
 * render is a different component to React, so every input in it would remount (and lose the
 * caret) on every keystroke. Context changes re-render the cells; they never remount them.
 */
interface GridContextValue {
  editing: boolean;
  quotationId: string | null;
  seriesId?: string | null;
  fetchProducts: (query: string) => Promise<SearchableSelectOption[]>;
  resolveProduct: (
    line: QuotationLine | null,
    draft: LineDraft,
  ) => SearchableSelectOption | undefined;
  uomOptions: SearchableSelectOption[];
  uomError: unknown;
  onUomRetry: () => void;
  brandOptions: SearchableSelectOption[];
  total: string | null;
  update: (key: string, patch: LineDraft) => void;
  selectProduct: (key: string, option: SearchableSelectOption | null) => void;
  toggleRemoved: (key: string) => void;
  act: (key: string, action: MenuAction) => void;
  bandOpen: Set<string>;
  closeEmptyBand: (key: string) => void;
  openPreview: (kind: LineFileKind, shown: LineFileShown) => void;
  /** The row's name in every label (`describeLine`). */
  labelOf: (row: GridRow) => string;
  /** Rows whose description was left at least once: an empty one is marked from then on. */
  visited: Set<string>;
  markVisited: (key: string) => void;
  /** Open customer feedback on the whole item (a dot by its number, mock frame 5). */
  itemNotes: (row: GridRow) => QuotationFeedbackRow[];
}

/** The scope's column headers (PS-QUOTE-MATRIX), and the header editor while it is editable. */
export interface QuotationLinesMatrix {
  /** `[]` is today's single Qty column. */
  columns: MatrixHeader[];
  /** Present on an editable version in an edit session: every header change, whole. */
  onChange?: (next: MatrixHeader[]) => void | Promise<boolean | void>;
  /** A column write is on its way. */
  saving?: boolean;
  /** The document's other scopes, for Copy columns from. */
  copySources?: { label: string; columns: MatrixHeader[] }[];
  /** True while a removal counts down: the page's Save waits for it (its cells would 422). */
  onRemovalPending?: (pending: boolean) => void;
}

/**
 * How long a header or column removal counts down before it is written when System Settings has
 * not answered: the D7 hard-delete window. The live value is `deferred_delete_seconds`.
 */
export const COLUMN_REMOVAL_MS = DEFAULT_DEFERRED_DELETE_SECONDS * 1000;

const GridContext = React.createContext<GridContextValue | null>(null);

function useGrid(): GridContextValue {
  const value = React.useContext(GridContext);
  if (!value)
    throw new Error('QuotationLinesGrid cell rendered outside the grid');
  return value;
}

/**
 * How a row is named in labels: the stored code, else its stored description; a line never saved
 * goes by the product picked on it, so its name does not change when it is moved; else its
 * position.
 */
export function describeLine(
  line: QuotationLine | null,
  index: number,
  pickedCode?: string | null,
): string {
  if (line) return line.product_code ?? (richOneLine(line.description) || null) ?? `line ${index + 1}`;
  return pickedCode || `line ${index + 1}`;
}

/**
 * The stored line, but only while it still describes the row on screen: a product changed in this
 * session has no photo, drawing or candidates resolved for it until Save.
 */
function resolvedLine(row: GridRow): QuotationLine | null {
  const { line, draft } = row.staged;
  if (!line) return null;
  return (line.product_id ?? '') === (draft.product_id ?? '') &&
    (line.product_set_id ?? '') === (draft.product_set_id ?? '')
    ? line
    : null;
}

const PICK_FIELD: Record<
  LineFileKind,
  'image_attachment_id' | 'drawing_attachment_id'
> = {
  photo: 'image_attachment_id',
  drawing: 'drawing_attachment_id',
};

/**
 * The stored line a photo or drawing cell may draw from. Not once the draft has cleared a pick the
 * line had stored (a product change clears both, and changing back does not restore them): the
 * server's cell answered for that pick, so showing it would claim a picture the save will not send.
 */
function fileLine(row: GridRow, kind: LineFileKind): QuotationLine | null {
  const line = resolvedLine(row);
  const field = PICK_FIELD[kind];
  if (!line) return null;
  return line[field] && !(row.staged.draft[field] ?? '') ? null : line;
}

// ------------------------------------------------------------------------------ cells

function ItemCell({ row }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const notes = grid.itemNotes(row.original);
  return (
    <span className="block text-sm font-medium tabular-nums">
      {row.original.index + 1}
      {notes.length > 0 && (
        <span
          role="img"
          aria-label="Customer feedback"
          data-testid="line-feedback-dot"
          title={notes.map((note) => note.note || 'Customer feedback').join('\n')}
          className="ms-0.5 inline-block size-1.5 rounded-full bg-warning align-middle"
        />
      )}
    </span>
  );
}

function FileCell({ row, kind }: { row: GridRow; kind: LineFileKind }) {
  const grid = useGrid();
  const field = PICK_FIELD[kind];
  const { staged } = row;
  const stored = fileLine(row, kind);
  // No stored answer for this product (a new line, or a product picked in this session): ask for
  // the product's own cells, the same answer a saved line with no picks gets.
  const productId = staged.draft.product_id ?? '';
  const live = useQuotationLineImages(!stored && productId ? productId : null);
  const line = React.useMemo<QuotationLine | null>(() => {
    if (stored) return stored;
    if (!productId || !live.data) return null;
    return {
      ...(staged.line ?? {
        id: row.key,
        version_id: '',
        is_non_standard: false,
        is_below_floor: false,
      }),
      product_id: productId,
      product_code:
        grid.resolveProduct(staged.line, staged.draft)?.label ?? null,
      image_attachment_id: null,
      drawing_attachment_id: null,
      product_image: live.data.product_image,
      technical_drawing: live.data.technical_drawing,
      unit_price: staged.draft.unit_price ?? '',
      quantity: staged.draft.quantity ?? '',
      line_total: '0',
      sort_order: row.index,
    };
  }, [
    grid,
    live.data,
    productId,
    row.index,
    row.key,
    staged.draft,
    staged.line,
    stored,
  ]);
  return (
    <QuotationLineFileCell
      kind={kind}
      line={line}
      label={grid.labelOf(row)}
      pickedId={staged.draft[field] ?? ''}
      editable={grid.editing && !staged.removed}
      canEscalate={stored !== null}
      onPick={(attachmentId) => grid.update(row.key, { [field]: attachmentId })}
      onPreview={(shown) => grid.openPreview(kind, shown)}
    />
  );
}

function PhotoCell({ row }: CellContext<GridRow, unknown>) {
  return <FileCell row={row.original} kind="photo" />;
}

function DrawingCell({ row }: CellContext<GridRow, unknown>) {
  return <FileCell row={row.original} kind="drawing" />;
}

/** A labelled SearchableSelect in a cell: the label is what names it to a screen reader. */
function CellSelect({
  label,
  ...props
}: { label: string } & React.ComponentProps<typeof SearchableSelect>) {
  const id = React.useId();
  return (
    <>
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <SearchableSelect id={id} size="sm" truncateTriggerLabel {...props} />
    </>
  );
}

function SetBadge() {
  return (
    <Badge variant="secondary" appearance="light" size="sm" className="shrink-0">
      Set
    </Badge>
  );
}

/**
 * A picker option is its code alone, wrapping rather than cut short. In Sorento the product code
 * IS the name, so a name beside it printed the code twice (owner, 29 Oct: "just show product code
 * only"). A set's Set badge shows on the picked value, not in the list.
 */
function renderLineOption(option: SearchableSelectOption): React.ReactNode {
  return <span className="block min-w-0 break-words">{option.label}</span>;
}

/** A set line's stock pill: the parts frozen on the line, else the picked set's own parts. */
function SetStock({ row, quantity }: { row: GridRow; quantity: string }) {
  const grid = useGrid();
  const { staged } = row;
  const setId = staged.draft.product_set_id ?? '';
  const stored =
    staged.line?.product_set_id === setId ? (staged.line?.set_parts ?? []) : [];
  const ref = useProductSetLineRef(stored.length === 0 ? setId : null);
  const parts = stored.length > 0 ? stored : (ref.data?.parts ?? []);
  return (
    <SetStockChip
      parts={parts.filter((part): part is typeof part & { product_id: string } => Boolean(part.product_id))}
      quantity={quantity}
      label={grid.labelOf(row)}
    />
  );
}

function ProductCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const label = grid.labelOf(row);
  const editable = grid.editing && !staged.removed;

  // Marked once the row has been touched or reached, never on a row nobody has been to yet.
  const productError =
    isUntouched(staged.draft) && !grid.visited.has(row.key)
      ? undefined
      : lineErrors(staged.draft).product;
  const productErrorId = `${row.key}-product-error`;
  return (
    <div className="min-w-0 space-y-1">
      {editable ? (
        <CellSelect
          label={`Product on ${label}`}
          clearable
          value={
            staged.draft.product_set_id
              ? `${SET_OPTION_PREFIX}${staged.draft.product_set_id}`
              : (staged.draft.product_id ?? '')
          }
          // The pick and its fill are one write, made in `onOptionChange`.
          onChange={() => undefined}
          onOptionChange={(option) => grid.selectProduct(row.key, option)}
          fetchOptions={grid.fetchProducts}
          selectedOption={grid.resolveProduct(staged.line, staged.draft)}
          renderOption={renderLineOption}
          placeholder="Pick a product"
          aria-invalid={productError ? true : undefined}
          aria-describedby={productError ? productErrorId : undefined}
          emptyMessage="No matches"
        />
      ) : (
        <span className="flex min-w-0 items-center gap-1.5">
          <span
            className="block truncate text-sm font-medium"
            title={staged.line?.product_code ?? undefined}
          >
            {staged.draft.product_id || staged.draft.product_set_id
              ? (staged.line?.product_code ?? '-')
              : ''}
          </span>
          {staged.draft.product_set_id ? <SetBadge /> : null}
        </span>
      )}
      {editable && staged.draft.product_set_id ? <SetBadge /> : null}
      {editable && productError && (
        <p id={productErrorId} className="whitespace-normal break-words text-xs text-destructive">
          {productError}
        </p>
      )}
      <LineFlags
        quotationId={grid.quotationId}
        seriesId={grid.seriesId}
        line={staged.line}
        draft={staged.draft}
      />
      {staged.removed && (
        <Badge variant="outline" className="text-2xs">
          Removed on save
        </Badge>
      )}
    </div>
  );
}

/**
 * What the shared editor hands back, as a description: an editor holding no text at all is an
 * empty description, so the catalogue default applies on save, as it did for an emptied textarea.
 */
export function descriptionFromEditor(html: string): string {
  return richPlainText(html).trim() === '' ? '' : html;
}

/**
 * The line description (QUOTE-DESC-RICHTEXT): the styled text in the cell, the shared rich text
 * editor (full toolbar, as the price tag description) in a popover anchored to it, since the
 * toolbar does not fit the column. A plain description shows and prints exactly as typed.
 */
function DescriptionCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const value = staged.draft.description ?? '';
  const labelId = React.useId();

  if (!grid.editing || staged.removed) {
    return <RichDescription value={value} className="text-xs" />;
  }

  const label = grid.labelOf(row);
  return (
    <Popover onOpenChange={(open) => (open ? undefined : grid.markVisited(row.key))}>
      <PopoverTrigger asChild>
        {/* A div, not a <button>: the styled text holds block elements, which a button may not. */}
        <div
          role="button"
          tabIndex={0}
          aria-label={`Description on ${label}`}
          title="Edit description"
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              event.currentTarget.click();
            }
          }}
          className="block min-h-8 w-full min-w-0 cursor-text rounded-md border border-input bg-background px-2 py-1.5 text-left hover:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {value.trim() ? (
            <RichDescription value={value} className="text-xs" />
          ) : (
            <span className="text-xs text-muted-foreground">Type what the customer reads</span>
          )}
        </div>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          align="start"
          collisionPadding={8}
          className="w-[min(28rem,calc(100vw-2rem))] p-2"
        >
          <span id={labelId} className="sr-only">
            {`Description text on ${label}`}
          </span>
          <RichTextEditor
            aria-labelledby={labelId}
            value={toEditorHtml(value)}
            onChange={(html) =>
              grid.update(row.key, { description: descriptionFromEditor(html) })
            }
            placeholder="Type what the customer reads"
            minHeight={96}
          />
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

function BrandCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const brand = staged.draft.brand_snapshot ?? '';

  if (!grid.editing || staged.removed) {
    return (
      <span className="block truncate text-sm" title={brand || undefined}>
        {brand || '-'}
      </span>
    );
  }

  return (
    <CellSelect
      label={`Brand on ${grid.labelOf(row)}`}
      clearable
      value={brand}
      onChange={(next) => grid.update(row.key, { brand_snapshot: next })}
      options={grid.brandOptions}
      // A brand typed before the list existed still shows as itself.
      selectedOption={brand ? { value: brand, label: brand } : undefined}
      placeholder="Brand"
      emptyMessage="No matches"
    />
  );
}

/** The line's stock pill for `quantity`: the set's parts, or the product's own stock. */
function LineStockChip({ row, quantity }: { row: GridRow; quantity: string }) {
  const grid = useGrid();
  const { staged } = row;
  const uom = staged.draft.uom ?? '';
  const productId = staged.draft.product_id ?? '';
  const setId = staged.draft.product_set_id ?? '';
  return setId ? (
    <SetStock row={row} quantity={quantity} />
  ) : productId ? (
    <QuotationStockChip
      productId={productId}
      quantity={quantity}
      uom={uom}
      label={grid.labelOf(row)}
    />
  ) : null;
}

function QtyCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const label = grid.labelOf(row);
  const quantity = staged.draft.quantity ?? '';
  const chip = <LineStockChip row={row} quantity={quantity} />;

  if (!grid.editing || staged.removed) {
    return (
      <div className="flex flex-col items-end gap-1">
        <span className="text-sm tabular-nums">
          {quantity ? trimAmount(quantity) : '-'}
        </span>
        {chip}
      </div>
    );
  }

  const invalid = quantity.trim() !== '' && !isDecimalString(quantity);
  return (
    <div className="flex min-w-0 flex-col items-end gap-1">
      <Input
        variant="sm"
        value={quantity}
        inputMode="decimal"
        aria-label={`Qty on ${label}`}
        aria-invalid={invalid || undefined}
        title={invalid ? 'Must be a number' : undefined}
        className="w-full px-1.5 text-end tabular-nums"
        onChange={(event) =>
          grid.update(row.key, { quantity: event.target.value })
        }
      />
      {chip}
    </div>
  );
}

/** The unit, in a column of its own beside Qty (owner hand test, point 5). */
function UomCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const uom = staged.draft.uom ?? '';

  if (!grid.editing || staged.removed) {
    return (
      <span className="block truncate text-sm" title={uom || undefined}>
        {uom || '-'}
      </span>
    );
  }

  return (
    <CellSelect
      label={`UOM on ${grid.labelOf(row)}`}
      clearable
      value={uom}
      onChange={(next) => grid.update(row.key, { uom: next })}
      options={grid.uomOptions}
      loadError={grid.uomError}
      onRetry={grid.onUomRetry}
      selectedOption={grid.uomOptions.find((option) => option.value === uom)}
      placeholder="UOM"
      triggerClassName="px-1.5"
      emptyMessage="No matches"
    />
  );
}

function RateCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const price = staged.draft.unit_price ?? '';
  // The draft's list price first: a product picked a moment ago shows its own at once.
  const listPrice = staged.draft.list_price || staged.line?.list_price;
  const list = listPrice ? (
    <span className="mt-0.5 block text-end text-xs text-muted-foreground">
      {`List ${formatMyr(listPrice)}`}
    </span>
  ) : null;
  // Under the price it judges (owner meeting, 29 Oct), not in the Product cell.
  const minimum = (
    <MinimumPriceFlag
      quotationId={grid.quotationId}
      seriesId={grid.seriesId}
      line={staged.line}
      draft={staged.draft}
    />
  );

  if (!grid.editing || staged.removed) {
    return (
      <div className="text-end">
        <span className="block text-sm tabular-nums">
          {price ? formatMyr(price) : '-'}
        </span>
        {list}
        {minimum}
      </div>
    );
  }

  const invalid = price.trim() !== '' && !isDecimalString(price);
  return (
    <div className="min-w-0">
      <Input
        variant="sm"
        value={price}
        inputMode="decimal"
        placeholder="0.00"
        aria-label={`Unit price on ${grid.labelOf(row)}`}
        aria-invalid={invalid || undefined}
        title={invalid ? 'Must be a number' : undefined}
        className="w-full text-end tabular-nums"
        onChange={(event) =>
          grid.update(row.key, { unit_price: event.target.value })
        }
      />
      {list}
      {minimum}
    </div>
  );
}

function TotalCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const rateOnly = isInlineChecked(staged.draft.is_rate_only);

  return (
    <div className="flex flex-col items-end gap-1">
      {/* Off the draft, so it moves while a quantity is typed. A rate-only line prints the
          words: blank reads as "we forgot" and RM 0.00 as "free". */}
      {rateOnly ? (
        <Badge variant="secondary" appearance="light">
          rate only
        </Badge>
      ) : (
        <span className="text-xs font-medium tabular-nums">
          {formatMyrExact(
            multiplyMoney(staged.draft.quantity, staged.draft.unit_price) ??
              '0',
          )}
        </span>
      )}
      {grid.editing && !staged.removed && (
        <label className="flex items-center gap-1 text-2xs whitespace-nowrap text-muted-foreground">
          <Checkbox
            size="sm"
            aria-label={`Rate only on ${grid.labelOf(row)}`}
            checked={rateOnly}
            onCheckedChange={(next) =>
              grid.update(row.key, {
                is_rate_only: next === true ? INLINE_CHECKED : '',
              })
            }
          />
          Rate only
        </label>
      )}
    </div>
  );
}

/** The scope total under the money column, off every live draft except removed lines. */
function TotalFooter() {
  const grid = useGrid();
  return (
    // 12px so a seven-figure scope total fits the column without clipping.
    <span className="block text-end text-xs tabular-nums">
      {grid.total === null ? '-' : formatMyrExact(grid.total)}
    </span>
  );
}

/** The Amount column's footer on a grid scope: the scope total on the Total (RM) line. */
function MatrixAmountFooter() {
  const grid = useGrid();
  return <MatrixAmountFooterLines total={grid.total} />;
}

function ActionsCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const label = grid.labelOf(row);
  const [open, setOpen] = React.useState(false);
  /** Set by an action that puts the caret somewhere itself, so the menu does not take it back. */
  const keepFocus = React.useRef(false);

  if (!grid.editing) return null;

  if (staged.removed) {
    return (
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        aria-label={`Restore ${label}`}
        onClick={() => grid.toggleRemoved(row.key)}
      >
        <Undo2 className="size-3.5 text-primary" />
      </Button>
    );
  }

  const run = (action: MenuAction) => {
    keepFocus.current = action === 'section' || action === 'below';
    grid.act(row.key, action);
  };

  return (
    <div className="flex flex-col items-center gap-0.5">
      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label={`Line actions on ${label}`}
            title="Line actions"
            // Opens on click (and from the keyboard, which Radix handles): a pointerdown open
            // followed by the click's own toggle would close it again.
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => setOpen(true)}
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          onCloseAutoFocus={(event) => {
            if (keepFocus.current) event.preventDefault();
            keepFocus.current = false;
          }}
        >
          <DropdownMenuItem onSelect={() => run('below')}>
            Insert a line below
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => run('section')}>
            Insert a section above
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => run('remove')}
          >
            Remove line
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <NotesButton row={row} />
      <Button
        type="button"
        mode="icon"
        variant="ghost"
        size="sm"
        aria-label={`Remove ${label}`}
        title="Remove"
        onClick={() => grid.toggleRemoved(row.key)}
      >
        <Trash2 className="size-3.5 text-destructive" />
      </Button>
    </div>
  );
}

/** The line's note: an icon on the row (filled when a note exists) opening a small popover. */
function NotesButton({ row }: { row: GridRow }) {
  const grid = useGrid();
  const { staged } = row;
  const label = grid.labelOf(row);
  const note = staged.draft.notes ?? '';
  const has = note.trim() !== '';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          aria-label={`Notes on ${label}`}
          title="Notes"
          data-has-note={has ? 'true' : 'false'}
        >
          <StickyNote
            className={`size-3.5 ${has ? 'fill-primary/30 text-primary' : 'text-muted-foreground'}`}
          />
        </Button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent align="end" collisionPadding={8} className="w-[min(20rem,calc(100vw-2rem))] p-3">
          <Textarea
            variant="sm"
            rows={3}
            value={note}
            placeholder="Why this price, what was agreed, what it replaces"
            aria-label={`Note text on ${label}`}
            className="field-sizing-content min-h-16 resize-none"
            onChange={(event) => grid.update(row.key, { notes: event.target.value })}
          />
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}

/** A section heading, drawn as a full-width row above the line that carries it (AC-QLG03). */
function SectionBar({ row }: { row: GridRow }) {
  const grid = useGrid();
  const { staged } = row;
  const value = staged.draft.band_label ?? '';
  if (!grid.editing || staged.removed) {
    return (
      <span
        className="block truncate text-sm font-semibold text-foreground uppercase"
        title={value}
      >
        {value}
      </span>
    );
  }
  return (
    // The whole bar answers a right-click (Rename, Remove section), not only its input.
    <div data-section-key={row.key} className="w-full">
      <Input
        variant="sm"
        value={value}
        data-band-key={row.key}
        aria-label={`Section heading on ${grid.labelOf(row)}`}
        title={value}
        placeholder="e.g. BILL NO 3 PAGE 15/4, OPTIONAL ITEMS"
        maxLength={150}
        className="max-w-md font-semibold"
        onChange={(event) =>
          grid.update(row.key, { band_label: event.target.value })
        }
        onBlur={() => grid.closeEmptyBand(row.key)}
      />
    </div>
  );
}

function ReorderHeader() {
  return <span className="sr-only">Reorder</span>;
}

function HandleCell({ row }: CellContext<GridRow, unknown>) {
  return <DataGridTableDndRowHandle rowId={row.original.key} />;
}

function ActionsHeader() {
  return <span className="sr-only">Row actions</span>;
}

const NARROW = 'px-1.5';
const TIGHT = 'px-1';
const FLUSH = 'px-0';

/**
 * The columns, per the approved mock (section 1) and the owner's hand test (UOM beside Qty):
 * the defaults sum to 908px, 852px in view mode, where the 28px handle and the 28px row menu are
 * hidden. The handle and the row menu only exist while editing (column visibility), so the
 * column order a user saves holds in both views.
 */
const COLUMNS: ColumnDef<GridRow>[] = [
  {
    id: 'drag_handle',
    header: ReorderHeader,
    cell: HandleCell,
    size: 28,
    minSize: 28,
    enableResizing: false,
    enableHiding: false,
    meta: {
      headerTitle: 'Reorder',
      draggable: false,
      headerClassName: FLUSH,
      cellClassName: FLUSH,
    },
  },
  {
    id: 'item_no',
    header: '#',
    cell: ItemCell,
    size: 24,
    minSize: 24,
    enableHiding: false,
    meta: {
      headerTitle: '#',
      headerClassName: TIGHT,
      cellClassName: `${TIGHT} align-top`,
    },
  },
  // The reader's columns carry an accessor so the Columns menu lists them (it offers only
  // columns with one); the cells read the row themselves.
  {
    id: 'photo',
    accessorFn: (row) => row.staged.draft.image_attachment_id,
    header: 'Photo',
    cell: PhotoCell,
    size: 56,
    minSize: 56,
    meta: {
      headerTitle: 'Photo',
      headerClassName: TIGHT,
      cellClassName: `${TIGHT} align-top`,
    },
  },
  {
    id: 'drawing',
    accessorFn: (row) => row.staged.draft.drawing_attachment_id,
    header: 'Drawing',
    cell: DrawingCell,
    size: 56,
    minSize: 56,
    meta: {
      headerTitle: 'Drawing',
      headerClassName: TIGHT,
      cellClassName: `${TIGHT} align-top`,
    },
  },
  {
    id: 'product',
    accessorFn: (row) => row.staged.draft.product_id,
    header: 'Product',
    cell: ProductCell,
    size: 104,
    minSize: 88,
    meta: { headerTitle: 'Product', cellClassName: 'align-top' },
  },
  {
    id: 'description',
    accessorFn: (row) => row.staged.draft.description,
    header: 'Description',
    cell: DescriptionCell,
    size: 184,
    minSize: 140,
    meta: {
      headerTitle: 'Description',
      cellClassName: 'align-top whitespace-normal',
    },
  },
  {
    id: 'brand',
    accessorFn: (row) => row.staged.draft.brand_snapshot,
    header: 'Brand',
    cell: BrandCell,
    size: 84,
    minSize: 64,
    meta: { headerTitle: 'Brand', cellClassName: 'align-top' },
  },
  {
    id: 'qty',
    accessorFn: (row) => row.staged.draft.quantity,
    header: 'Qty',
    cell: QtyCell,
    size: 60,
    minSize: 52,
    meta: {
      headerTitle: 'Qty',
      headerClassName: `${NARROW} text-end`,
      cellClassName: `${NARROW} align-top`,
    },
  },
  {
    id: 'uom',
    accessorFn: (row) => row.staged.draft.uom,
    header: 'UOM',
    cell: UomCell,
    size: 72,
    minSize: 60,
    meta: {
      headerTitle: 'UOM',
      headerClassName: NARROW,
      cellClassName: `${NARROW} align-top`,
    },
  },
  {
    id: 'rate',
    accessorFn: (row) => row.staged.draft.unit_price,
    header: 'Rate (RM)',
    cell: RateCell,
    // Wide enough for the "Minimum price RM x" pill under the price on two lines.
    size: 112,
    minSize: 76,
    meta: {
      headerTitle: 'Rate (RM)',
      headerClassName: 'text-end',
      cellClassName: `${NARROW} align-top`,
    },
  },
  {
    id: 'total',
    accessorFn: (row) => row.staged.draft.is_rate_only,
    header: 'Total (RM)',
    cell: TotalCell,
    footer: TotalFooter,
    size: 112,
    minSize: 96,
    meta: {
      headerTitle: 'Total (RM)',
      headerClassName: 'text-end',
      cellClassName: `${NARROW} align-top text-end`,
    },
  },
  {
    id: 'row_actions',
    header: ActionsHeader,
    cell: ActionsCell,
    size: 28,
    minSize: 28,
    enableResizing: false,
    enableHiding: false,
    meta: {
      headerTitle: 'Row actions',
      draggable: false,
      headerClassName: FLUSH,
      cellClassName: `${FLUSH} align-top`,
    },
  },
];

/**
 * The columns for a scope WITH column headers (PS-QUOTE-MATRIX, mock v3 frame 1): every column
 * above stays where it is except Qty, whose place goes to the quantity columns after Rate; Total
 * becomes Amount, and the description column carries the two footer labels.
 */
function matrixColumns(headers: MatrixHeader[], editable: boolean): ColumnDef<GridRow>[] {
  const quantity = buildMatrixColumns(headers, editable) as ColumnDef<GridRow>[];
  return COLUMNS.flatMap((column) => {
    switch (column.id) {
      case 'qty':
        return [];
      case 'description':
        return [{ ...column, footer: MATRIX_LABEL_FOOTER }];
      case 'rate':
        return [column, ...quantity];
      case 'total':
        return [
          {
            ...column,
            header: 'Amount (RM)',
            footer: MatrixAmountFooter,
            meta: { ...column.meta, headerTitle: 'Amount (RM)' },
          },
        ];
      default:
        return [column];
    }
  });
}

// ------------------------------------------------------------------------------- grid

export interface QuotationLinesGridProps {
  /** The lines in display order: the staged set while editing, the server's rows otherwise. */
  lines: StagedQuotationLine[];
  editing: boolean;
  quotationId: string | null;
  /** The series the scope is quoted from: what a draft line is judged against before a save. */
  seriesId?: string | null;
  /** Live search: rows that fail it are hidden, never renumbered or left out of the total. */
  rowFilter?: (line: StagedQuotationLine) => boolean;
  emptyHint: string;
  filterEmptyHint: string;
  fetchProducts: GridContextValue['fetchProducts'];
  resolveProduct: GridContextValue['resolveProduct'];
  /** The code of a product picked in this session, or null when it is not known here. */
  productCodeOf: (productId: string) => string | null;
  /** What picking a product decides for the rest of its line (null for a cleared pick). */
  fillFromProduct: (option: SearchableSelectOption) => LineDraft;
  /** The rest of a line's fields once a SET is picked (loads the set's parts). */
  fillFromSet?: (setId: string) => Promise<LineDraft>;
  uomOptions: SearchableSelectOption[];
  uomError: unknown;
  onUomRetry: () => void;
  brandOptions: SearchableSelectOption[];
  /** The search control, drawn in the grid's own toolbar beside Columns. */
  toolbar?: React.ReactNode;
  /** Every edit, addition and reorder, as the whole staged set. Edit mode only. */
  onStage?: (lines: StagedQuotationLine[]) => void;
  onToggleRemoved?: (key: string) => void;
  /** The scope's column headers and their editor (PS-QUOTE-MATRIX). Absent = no columns. */
  matrix?: QuotationLinesMatrix;
  /**
   * OPEN customer feedback on this version's lines (PS-QUOTE-MATRIX R20): an amber corner on a
   * cell, a dot by an item's number. Matched on the stored line id the notes name.
   */
  feedback?: QuotationFeedbackRow[];
}

/**
 * The quotation's lines as the app's DataGrid (AC-QLG01 to AC-QLG04): rows drag by a handle,
 * columns resize and reorder and are remembered per user, a section heading is a full-width row
 * that moves with its line, and Line details open as an expanded row.
 *
 * It writes nothing: in an edit session every change goes up as the whole staged set, and the
 * document's one Save is what reaches the server.
 */
export function QuotationLinesGrid({
  lines,
  editing,
  quotationId,
  seriesId,
  rowFilter,
  emptyHint,
  filterEmptyHint,
  fetchProducts,
  resolveProduct,
  productCodeOf,
  fillFromProduct,
  fillFromSet,
  uomOptions,
  uomError,
  onUomRetry,
  brandOptions,
  onStage,
  onToggleRemoved,
  toolbar,
  matrix,
  feedback,
}: QuotationLinesGridProps) {
  /**
   * The header as last edited here, ahead of the server: a header or column just added is on
   * screen (focused, its name selected) the moment it is asked for, not when the write answers,
   * so typing that starts at once is not lost (fix round 3, M2a). Dropped when the server's
   * columns arrive, and rolled back when the write fails.
   */
  const [optimistic, setOptimistic] = React.useState<MatrixHeader[] | null>(null);
  const serverColumns = matrix?.columns;
  React.useEffect(() => setOptimistic(null), [serverColumns]);
  const headers = React.useMemo(() => optimistic ?? serverColumns ?? [], [optimistic, serverColumns]);
  const isMatrix = hasColumns(headers);
  const columnsEditable = editing && Boolean(matrix?.onChange);
  const [bandOpen, setBandOpen] = React.useState<Set<string>>(() => new Set());
  const [preview, setPreview] = React.useState<{
    items: AttachmentPreviewItem[];
    index: number;
  } | null>(null);
  const [visited, setVisited] = React.useState<Set<string>>(() => new Set());
  const markVisited = React.useCallback(
    (key: string) =>
      setVisited((previous) =>
        previous.has(key) ? previous : new Set(previous).add(key),
      ),
    [],
  );
  const instanceKey = React.useId();
  const nextNewId = React.useRef(0);

  /**
   * The newest set, ahead of the next render: a product pick is two writes in one event (the
   * pick and its fill), and each has to build on the other rather than on the props both saw.
   */
  const linesRef = React.useRef(lines);
  linesRef.current = lines;

  const commit = React.useCallback(
    (next: StagedQuotationLine[]) => {
      linesRef.current = next;
      onStage?.(next);
    },
    [onStage],
  );

  const update = React.useCallback(
    (key: string, patch: LineDraft) =>
      commit(
        linesRef.current.map((line) =>
          line.key === key
            ? { ...line, draft: { ...line.draft, ...patch } }
            : line,
        ),
      ),
    [commit],
  );

  const selectProduct = React.useCallback(
    (key: string, option: SearchableSelectOption | null) => {
      const held = linesRef.current.find((line) => line.key === key);
      if (!held) return;
      // A different product's (or set's) photo or drawing cannot be this one's, so a change
      // clears both.
      const heldValue = held.draft.product_set_id
        ? `${SET_OPTION_PREFIX}${held.draft.product_set_id}`
        : (held.draft.product_id ?? '');
      const clearPicks: LineDraft =
        (option?.value ?? '') !== heldValue
          ? { image_attachment_id: '', drawing_attachment_id: '' }
          : {};
      if (!option) {
        update(key, {
          product_id: '',
          product_set_id: '',
          [PICKED_CODE_KEY]: '',
          ...(held.draft.product_set_id ? { complete_set: '' } : {}),
          ...clearPicks,
        });
        return;
      }
      if (isSetOption(option.value)) {
        const setId = option.value.slice(SET_OPTION_PREFIX.length);
        update(key, {
          product_id: '',
          product_set_id: setId,
          // The option's label IS the code (sets and products alike).
          [PICKED_CODE_KEY]: option.label,
          uom: 'SET',
          ...clearPicks,
        });
        // The parts, brand, price and Complete set need the set's detail; applied only if the
        // row still names this set when it arrives.
        void fillFromSet?.(setId)
          .then((filled) => {
            const now = linesRef.current.find((line) => line.key === key);
            if (now?.draft.product_set_id !== setId) return;
            // A typed brand is never overwritten by the set's.
            const { brand_snapshot: brand, ...rest } = filled;
            update(key, (now.draft.brand_snapshot ?? '').trim() ? rest : { ...rest, brand_snapshot: brand ?? '' });
          })
          .catch(() => toast.error('Could not load that set'));
        return;
      }
      update(key, {
        product_id: option.value,
        product_set_id: '',
        [PICKED_CODE_KEY]: option.label,
        // Off a set, its parts text no longer describes the line.
        ...(held.draft.product_set_id ? { complete_set: '' } : {}),
        ...fillFromProduct(option),
        ...clearPicks,
      });
    },
    [fillFromProduct, fillFromSet, update],
  );

  const focusSoon = React.useCallback((selector: string) => {
    window.setTimeout(() => {
      document.querySelector<HTMLElement>(selector)?.focus();
    }, 0);
  }, []);

  const newLine = React.useCallback((): StagedQuotationLine => {
    nextNewId.current += 1;
    return {
      id: null,
      key: `new:${instanceKey}:${nextNewId.current}`,
      line: null,
      // A grid scope's new line starts with no cells (quantity 0), not the plain default of 1.
      draft: isMatrix ? { ...emptyDraft(), ...cellsPatch({}) } : emptyDraft(),
      removed: false,
    };
  }, [instanceKey, isMatrix]);

  const openBand = React.useCallback(
    (key: string) => {
      setBandOpen((previous) => new Set(previous).add(key));
      // Keys are line ids or `new:<id>:<n>`, so a quoted attribute value needs no escaping.
      focusSoon(`[data-band-key="${key}"]`);
    },
    [focusSoon],
  );

  const closeEmptyBand = React.useCallback((key: string) => {
    const held = linesRef.current.find((line) => line.key === key);
    if (held && (held.draft.band_label ?? '').trim() !== '') return;
    setBandOpen((previous) => {
      if (!previous.has(key)) return previous;
      const next = new Set(previous);
      next.delete(key);
      return next;
    });
  }, []);

  const addLine = React.useCallback(
    (withSection: boolean) => {
      const added = newLine();
      commit([...linesRef.current, added]);
      if (withSection) openBand(added.key);
    },
    [commit, newLine, openBand],
  );

  const act = React.useCallback(
    (key: string, action: MenuAction) => {
      const current = linesRef.current;
      const index = current.findIndex((line) => line.key === key);
      if (index < 0) return;
      switch (action) {
        case 'below': {
          const added = newLine();
          commit([
            ...current.slice(0, index + 1),
            added,
            ...current.slice(index + 1),
          ]);
          return;
        }
        case 'section':
          openBand(key);
          return;
        case 'remove':
          onToggleRemoved?.(key);
          return;
      }
    },
    [commit, newLine, onToggleRemoved, openBand],
  );

  const handleRowDragEnd = React.useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const current = linesRef.current;
      const from = current.findIndex((line) => line.key === String(active.id));
      const to = current.findIndex((line) => line.key === String(over.id));
      if (from < 0 || to < 0) return;
      commit(arrayMove(current, from, to));
    },
    [commit],
  );

  const allRows = React.useMemo<GridRow[]>(
    () => lines.map((staged, index) => ({ key: staged.key, index, staged })),
    [lines],
  );
  const visibleRows = React.useMemo(
    () =>
      rowFilter ? allRows.filter((row) => rowFilter(row.staged)) : allRows,
    [allRows, rowFilter],
  );
  // Out of the money the moment a line is staged for removal; never out of it for a search.
  const total = React.useMemo(
    () =>
      totalFromDrafts(
        lines.filter((line) => !line.removed).map((line) => line.draft),
      ),
    [lines],
  );

  /** Each viewer's gallery: every line that HAS that picture, in table order. */
  const galleries = React.useMemo(() => {
    const build = (
      kind: LineFileKind,
    ): (AttachmentPreviewItem & { attachmentId: string })[] =>
      allRows.flatMap((row) => {
        const line = fileLine(row, kind);
        const field = PICK_FIELD[kind];
        const shown = resolveLineFile(
          kind,
          line,
          row.staged.draft[field] ?? '',
        );
        if (!shown) return [];
        const code = line?.product_code ?? 'Product';
        return [
          {
            id: `${row.key}:${shown.attachmentId}`,
            attachmentId: shown.attachmentId,
            name: shown.filename ?? `${code} ${kind}`,
            url: shown.previewUrl,
            downloadUrl: `/api/v1/resource-management/attachments/${shown.attachmentId}/download`,
          },
        ];
      });
    return { photo: build('photo'), drawing: build('drawing') };
  }, [allRows]);

  const openPreview = React.useCallback(
    (kind: LineFileKind, shown: LineFileShown) => {
      const gallery = galleries[kind];
      const index = gallery.findIndex(
        (item) => item.attachmentId === shown.attachmentId,
      );
      if (index >= 0) {
        setPreview({ items: gallery, index });
        return;
      }
      // A line not saved yet is not in the gallery (its picture is not stored anywhere): its
      // own picture opens on its own.
      setPreview({
        items: [
          {
            id: shown.attachmentId,
            name: shown.filename ?? kind,
            url: shown.previewUrl,
            downloadUrl: `/api/v1/resource-management/attachments/${shown.attachmentId}/download`,
          },
        ],
        index: 0,
      });
    },
    [galleries],
  );

  const labelOf = React.useCallback(
    (row: GridRow) => {
      const setId = row.staged.draft.product_set_id ?? '';
      const productId = setId
        ? `${SET_OPTION_PREFIX}${setId}`
        : (row.staged.draft.product_id ?? '');
      return describeLine(
        row.staged.line,
        row.index,
        !row.staged.line && productId
          ? (productCodeOf(productId) ?? (row.staged.draft[PICKED_CODE_KEY] || null))
          : null,
      );
    },
    [productCodeOf],
  );

  /**
   * Open feedback by the stored line it names: whole-item notes (and notes on a column no longer
   * there) by line, cell notes by line and cell. Matched on the stored line only.
   */
  const leafSet = React.useMemo(() => new Set(leafKeys(headers)), [headers]);
  const notes = React.useMemo(() => {
    const items = new Map<string, QuotationFeedbackRow[]>();
    const cells = new Map<string, QuotationFeedbackRow[]>();
    (feedback ?? []).forEach((row) => {
      if (row.handled_at) return;
      const onCell = row.cell_key && leafSet.has(row.cell_key);
      const map = onCell ? cells : items;
      const key = onCell ? `${row.line_id}:${row.cell_key}` : row.line_id;
      map.set(key, [...(map.get(key) ?? []), row]);
    });
    return { items, cells };
  }, [feedback, leafSet]);
  const itemNotes = React.useCallback(
    (row: GridRow) => (row.staged.line ? (notes.items.get(row.staged.line.id) ?? []) : []),
    [notes],
  );
  const cellNotes = React.useCallback(
    (row: GridRow, leafKey: string) =>
      row.staged.line ? (notes.cells.get(`${row.staged.line.id}:${leafKey}`) ?? []) : [],
    [notes],
  );

  const context = React.useMemo<GridContextValue>(
    () => ({
      editing,
      quotationId,
      seriesId,
      fetchProducts,
      resolveProduct,
      uomOptions,
      uomError,
      onUomRetry,
      brandOptions,
      total,
      update,
      selectProduct,
      toggleRemoved: (key) => onToggleRemoved?.(key),
      act,
      bandOpen,
      closeEmptyBand,
      openPreview,
      visited,
      markVisited,
      labelOf,
      itemNotes,
    }),
    [
      act,
      bandOpen,
      brandOptions,
      closeEmptyBand,
      editing,
      fetchProducts,
      itemNotes,
      labelOf,
      markVisited,
      onToggleRemoved,
      onUomRetry,
      openPreview,
      quotationId,
      resolveProduct,
      seriesId,
      selectProduct,
      total,
      uomError,
      uomOptions,
      update,
      visited,
    ],
  );

  /** The reader's own column choices (Columns menu, saved per user by the grid). */
  const [columnVisibility, setColumnVisibility] =
    React.useState<VisibilityState>({});

  // ------------------------------------------------------------ grid scope (PS-QUOTE-MATRIX)

  const [pending, setPending] = React.useState<PendingRemoval | null>(null);
  const removalSeconds = useDeferredDeleteSeconds();
  const removalMsRef = React.useRef(removalSeconds * 1000);
  removalMsRef.current = removalSeconds * 1000;
  const [focusKey, setFocusKey] = React.useState<string | null>(null);
  const headersRef = React.useRef(headers);
  headersRef.current = headers;
  const onMatrixChange = matrix?.onChange;
  const change = React.useCallback(
    (next: MatrixHeader[]) => {
      if (!onMatrixChange) return;
      headersRef.current = next;
      setOptimistic(next);
      void Promise.resolve(onMatrixChange(next)).then(
        // The write already said why it failed (a toast); the header goes back to the server's.
        (ok) => {
          if (ok === false) setOptimistic(null);
        },
        () => setOptimistic(null),
      );
    },
    [onMatrixChange],
  );
  /** Adds an item and asks for its label box to take the caret once it is drawn. */
  const changeAndFocus = React.useCallback(
    (next: MatrixHeader[]) => {
      const before = usedKeys(headersRef.current);
      const added = Array.from(usedKeys(next)).find((key) => !before.has(key)) ?? null;
      setFocusKey(added);
      change(next);
    },
    [change],
  );
  const addCol = React.useCallback(
    (headerKey: string) => {
      const header = headersRef.current.find((row) => row.key === headerKey);
      changeAndFocus(
        addMatrixCol(headersRef.current, headerKey, `Column ${(header?.cols.length ?? 0) + 1}`),
      );
    },
    [changeAndFocus],
  );
  const addHeader = React.useCallback(
    () =>
      changeAndFocus(
        addMatrixHeader(headersRef.current, `Header ${headersRef.current.length + 1}`),
      ),
    [changeAndFocus],
  );
  const startRemoval = React.useCallback((key: string) => {
    const all = headersRef.current.flatMap((header) => [
      { key: header.key, label: header.label },
      ...header.cols.map((col) => ({ key: col.key, label: col.label })),
    ]);
    const item = all.find((row) => row.key === key);
    if (!item) return;
    setPending({
      key,
      label: item.label,
      commitAt: Date.now() + removalMsRef.current,
      lines: cellsUnder(
        headersRef.current,
        key,
        linesRef.current.filter((line) => !line.removed).map((line) => draftCells(line.draft)),
      ),
    });
  }, []);
  // The countdown commits on its own clock; Undo clears it first. One removal at a time, so two
  // writes never race each other with stale columns.
  const pendingRef = React.useRef(pending);
  pendingRef.current = pending;
  // The last handler the edit session gave: once it ends the grid has none, and the parked
  // removal still has to reach the version it was started on.
  const changeRef = React.useRef(onMatrixChange);
  if (onMatrixChange) changeRef.current = onMatrixChange;
  /** Writes the parked removal now, once. Safe to call when nothing is parked. */
  const commitPending = React.useCallback(() => {
    const held = pendingRef.current;
    if (!held) return;
    pendingRef.current = null;
    setPending(null);
    changeRef.current?.(removeKey(headersRef.current, held.key));
  }, []);
  React.useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(commitPending, Math.max(0, pending.commitAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [commitPending, pending]);
  // Leaving the edit session (Save, Cancel, a scope or tab switch) never drops a removal the user
  // let run: it commits at once rather than vanishing with the countdown, which has no handler
  // outside edit mode. Undo is the only way back, and it had its window.
  React.useEffect(() => {
    if (!columnsEditable) commitPending();
  }, [columnsEditable, commitPending]);
  const onRemovalPending = matrix?.onRemovalPending;
  const onRemovalPendingRef = React.useRef(onRemovalPending);
  onRemovalPendingRef.current = onRemovalPending;
  const isRemovalPending = pending !== null;
  React.useEffect(() => {
    onRemovalPending?.(isRemovalPending);
  }, [isRemovalPending, onRemovalPending]);
  React.useEffect(
    () => () => {
      commitPending();
      // Gone mid-countdown: the removal is now a write (the editor tracks that), not a countdown.
      onRemovalPendingRef.current?.(false);
    },
    [commitPending],
  );

  const updateCell = React.useCallback(
    (rowKey: string, leafKey: string, value: string) => {
      const held = linesRef.current.find((line) => line.key === rowKey);
      if (!held) return;
      const cells = { ...(draftCells(held.draft) ?? {}) };
      if (value.trim() === '') delete cells[leafKey];
      else cells[leafKey] = value;
      update(rowKey, cellsPatch(cells));
    },
    [update],
  );

  /** A block from a spreadsheet, right and down from the cell it lands in (R14). */
  const visibleRowsRef = React.useRef(visibleRows);
  visibleRowsRef.current = visibleRows;
  const pasteAt = React.useCallback(
    (rowKey: string, leafKey: string, text: string) => {
      const keys = leafKeys(headersRef.current);
      const rows = visibleRowsRef.current;
      const result = parsePaste(
        text,
        keys.indexOf(leafKey),
        rows.findIndex((row) => row.key === rowKey),
      );
      if (!result.ok) {
        toast.error(result.error);
        return;
      }
      const byRow = new Map<string, Record<string, string>>();
      result.cells.forEach((cell) => {
        const row = rows[cell.rowIndex];
        const key = keys[cell.leafIndex];
        // Paste never creates rows or columns: what falls outside the grid is dropped.
        if (!row || !key || row.staged.removed) return;
        byRow.set(row.key, { ...(byRow.get(row.key) ?? {}), [key]: cell.value });
      });
      commit(
        linesRef.current.map((line) => {
          const pasted = byRow.get(line.key);
          if (!pasted) return line;
          const cells = { ...(draftCells(line.draft) ?? {}) };
          Object.entries(pasted).forEach(([key, value]) => {
            if (value === '') delete cells[key];
            else cells[key] = value;
          });
          return { ...line, draft: { ...line.draft, ...cellsPatch(cells) } };
        }),
      );
    },
    [commit],
  );

  const matrixFooter = React.useMemo(
    () =>
      summary(
        headers,
        lines
          .filter((line) => !line.removed)
          .map((line) => ({
            qty_cells: draftCells(line.draft),
            unit_price: line.draft.unit_price,
            is_rate_only: isInlineChecked(line.draft.is_rate_only),
          })),
      ).footer,
    [headers, lines],
  );

  const matrixContext = React.useMemo<MatrixGridContextValue>(
    () => ({
      headers,
      editing,
      editable: columnsEditable,
      saving: Boolean(matrix?.saving),
      footer: matrixFooter,
      change,
      addCol,
      addHeader,
      pending,
      startRemoval,
      undoRemoval: () => setPending(null),
      focusKey,
      clearFocusKey: () => setFocusKey(null),
      updateCell,
      pasteAt,
      labelOf,
      cellNotes,
      stockChip: (row, quantity) => <LineStockChip row={row} quantity={quantity} />,
    }),
    [
      addCol,
      addHeader,
      cellNotes,
      change,
      columnsEditable,
      editing,
      focusKey,
      headers,
      labelOf,
      matrix?.saving,
      matrixFooter,
      pasteAt,
      pending,
      startRemoval,
      updateCell,
    ],
  );

  const columns = React.useMemo(
    () => (isMatrix ? matrixColumns(headers, columnsEditable) : COLUMNS),
    [columnsEditable, headers, isMatrix],
  );
  const copySources = matrix?.copySources ?? [];

  const table = useReactTable({
    columns,
    data: visibleRows,
    getRowId: (row) => row.key,
    getCoreRowModel: getCoreRowModel(),
    state: {
      // The handle and the menu are edit-only; hidden rather than removed, so a saved column
      // order holds in both views. They cannot be hidden by the reader either.
      columnVisibility: {
        ...columnVisibility,
        drag_handle: editing,
        row_actions: editing,
      },
    },
    onColumnVisibilityChange: setColumnVisibility,
    enableSorting: false,
    columnResizeMode: 'onChange',
  });

  /**
   * What a right-click is on: a section bar, or a line row. Read off the DOM the event came from,
   * so one menu serves every row (owner hand test, points 2 and 3).
   */
  const [menuTarget, setMenuTarget] = React.useState<{
    kind: 'line' | 'section';
    key: string;
  } | null>(null);
  /**
   * Null outside the rows and bars, and over an editable control inside one (the heading, the
   * description, Qty): there the browser's own menu shows, for copy, paste and spelling.
   */
  const targetOf = (element: Element | null) => {
    if (
      element?.closest(
        'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
      )
    )
      return null;
    const bar = element?.closest<HTMLElement>('[data-section-key]');
    if (bar?.dataset.sectionKey)
      return { kind: 'section' as const, key: bar.dataset.sectionKey };
    const tr = element?.closest<HTMLElement>('tr[data-line-key]');
    if (tr?.dataset.lineKey)
      return { kind: 'line' as const, key: tr.dataset.lineKey };
    return null;
  };
  /** Set by an action that puts the caret somewhere itself, so the menu does not take it back. */
  const keepFocusAfterMenu = React.useRef(false);
  const menuLine = menuTarget
    ? (lines.find((line) => line.key === menuTarget.key) ?? null)
    : null;

  const renderSection = React.useCallback(
    (row: GridRow) => {
      const label = (row.staged.draft.band_label ?? '').trim();
      return label || (editing && bandOpen.has(row.key)) ? (
        <SectionBar row={row} />
      ) : null;
    },
    [bandOpen, editing],
  );

  const galleryItems = preview?.items ?? [];

  const renameSection = (key: string) => {
    keepFocusAfterMenu.current = true;
    window.setTimeout(() => {
      document.querySelector<HTMLElement>(`[data-band-key="${key}"]`)?.focus();
    }, 0);
  };
  const removeSection = (key: string) => {
    update(key, { band_label: '' });
    setBandOpen((previous) => {
      if (!previous.has(key)) return previous;
      const next = new Set(previous);
      next.delete(key);
      return next;
    });
  };

  return (
    <GridContext.Provider value={context}>
     <MatrixGridProvider value={matrixContext}>
      <div className="min-w-0 space-y-2">
        <DataGrid
          table={table}
          recordCount={visibleRows.length}
          isLoading={false}
          // Rows render under the default layout while the saved one loads, rather than as
          // skeletons: an editor must never hide the lines somebody is about to type into.
          loadingMode="spinner"
          // A grid scope's columns are DATA (its own headers), so nothing is saved for it: a stored
          // order would be re-applied against whichever headers exist (see DataGrid's opt-out).
          listingKey={isMatrix ? null : 'projects.projects.view::quotation-lines'}
          tableLayout={{ width: 'fixed', columnsResizable: true, dense: true }}
          tableClassNames={{ headerRow: 'text-xs' }}
          emptyMessage={lines.length === 0 ? emptyHint : filterEmptyHint}
          renderGroupHeader={renderSection}
          rowClassName={(row: GridRow) =>
            row.staged.removed
              ? 'text-muted-foreground line-through opacity-70'
              : undefined
          }
          rowAttributes={(row: GridRow) => ({ 'data-line-key': row.key })}
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {toolbar}
            <div className="flex flex-wrap items-center gap-2 sm:ms-auto">
              {columnsEditable && copySources.length > 0 && (
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      disabled={Boolean(matrix?.saving) || pending !== null}
                    >
                      Copy columns from
                      <ChevronDown className="size-4" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    {copySources.map((source) => (
                      <DropdownMenuItem
                        key={source.label}
                        disabled={!hasColumns(source.columns)}
                        onSelect={() =>
                          change(appendMatrixCopy(headersRef.current, source.columns))
                        }
                      >
                        <span className="min-w-0 truncate" title={source.label}>
                          {hasColumns(source.columns) ? source.label : `${source.label} (none)`}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
            </div>
          </div>
          <ContextMenu modal={false}>
            <ContextMenuTrigger asChild disabled={!editing}>
              <div
                className="min-w-0 overflow-hidden rounded-lg border border-border"
                // Capture phase, ahead of the menu's own handler on this same element: a
                // right-click with nothing of ours under it stops here, unprevented, so the
                // menu never opens and the browser shows its own.
                onContextMenuCapture={(event) => {
                  const target = targetOf(event.target as Element);
                  if (!target) {
                    event.stopPropagation();
                    return;
                  }
                  setMenuTarget(target);
                }}
              >
                <DataGridScroller>
                  <DataGridTableDndRows
                    handleDragEnd={handleRowDragEnd}
                    dataIds={visibleRows.map((row) => row.key)}
                    // A grid scope's two header rows are its column headers, edited in place;
                    // the product columns keep their order there rather than dragging.
                    columnsDraggable={!isMatrix}
                  />
                </DataGridScroller>
                {editing && (
                  <div className="flex flex-wrap items-center gap-1 border-t border-border px-2 py-1.5">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-primary hover:text-primary"
                      onClick={() => addLine(false)}
                    >
                      <Plus className="size-4" aria-hidden />
                      Add a line
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-primary hover:text-primary"
                      onClick={() => addLine(true)}
                    >
                      <Plus className="size-4" aria-hidden />
                      Add a section
                    </Button>
                    {/* How a grid starts: the first column header (R11, R12). Once there is
                        one, + Column header sits at the end of the header row instead. */}
                    {columnsEditable && !isMatrix && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-primary hover:text-primary"
                        disabled={Boolean(matrix?.saving)}
                        onClick={addHeader}
                      >
                        <Plus className="size-4" aria-hidden />
                        Column header
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </ContextMenuTrigger>
            <ContextMenuContent
              className="w-52"
              onCloseAutoFocus={(event) => {
                if (keepFocusAfterMenu.current) event.preventDefault();
                keepFocusAfterMenu.current = false;
              }}
            >
              {menuTarget?.kind === 'section' ? (
                <>
                  <ContextMenuItem
                    onSelect={() => renameSection(menuTarget.key)}
                  >
                    Rename
                  </ContextMenuItem>
                  <ContextMenuItem
                    variant="destructive"
                    onSelect={() => removeSection(menuTarget.key)}
                  >
                    Remove section
                  </ContextMenuItem>
                </>
              ) : menuTarget ? (
                <>
                  <ContextMenuItem
                    disabled={Boolean(menuLine?.removed)}
                    onSelect={() => {
                      keepFocusAfterMenu.current = true;
                      act(menuTarget.key, 'below');
                    }}
                  >
                    Insert a line below
                  </ContextMenuItem>
                  <ContextMenuItem
                    disabled={Boolean(menuLine?.removed)}
                    onSelect={() => {
                      keepFocusAfterMenu.current = true;
                      act(menuTarget.key, 'section');
                    }}
                  >
                    Insert a section above
                  </ContextMenuItem>
                  <ContextMenuItem
                    variant={menuLine?.removed ? 'default' : 'destructive'}
                    onSelect={() => act(menuTarget.key, 'remove')}
                  >
                    {menuLine?.removed ? 'Restore line' : 'Remove line'}
                  </ContextMenuItem>
                </>
              ) : null}
            </ContextMenuContent>
          </ContextMenu>
        </DataGrid>

        {/* The same viewer Resource Management uses. Mounted only while open. */}
        {preview && galleryItems.length > 0 && (
          <AttachmentPreviewModal
            open
            onOpenChange={(next) => {
              if (!next) setPreview(null);
            }}
            items={galleryItems}
            startIndex={preview.index}
          />
        )}
      </div>
     </MatrixGridProvider>
    </GridContext.Provider>
  );
}
