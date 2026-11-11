'use client';

import * as React from 'react';
import {
  type CellContext,
  type ColumnDef,
  type VisibilityState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { mergeColumnOrderWithLeafColumns } from '@/lib/listing-column-preferences/mergeColumnOrder';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { ChevronDown, Columns3, MoreHorizontal, Plus, Redo2, StickyNote, Trash2, Undo2 } from 'lucide-react';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import type { Editor } from '@tiptap/react';
import { Selection } from '@tiptap/pm/state';
import { docPosAtTextOffset, textOffsetAtPoint } from './quotationDescriptionCaret';
import { RichDescription } from '@/components/common/RichDescription';
import { richOneLine, richPlainText, toEditorHtml } from '@/lib/dealer-kit/rich-text';
import { toast } from '@/lib/toast';
import { useDeferredDeleteSeconds } from '@/hooks/useDeferredDeleteSeconds';
import { useUndoHistory } from '@/hooks/useUndoHistory';
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
  duplicateHeader as duplicateMatrixHeader,
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
  ADD_FIRST_HEADER_COLUMN,
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
  isSectionDraft,
  isUntouched,
  lineErrors,
  sectionDraft,
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
  /**
   * The item number: lines only, heading rows take none (PROPOSAL-FORM-COLLAPSE). Optional so a
   * matrix cell's row (`MatrixGridRow`) still reads as a grid row.
   */
  number?: number | null;
  staged: StagedQuotationLine;
}

type MenuAction = 'below' | 'section' | 'remove' | 'duplicate';

/**
 * How an edit lands in the Undo history: `auto` folds a run of keystrokes into one field of one
 * row into a single step; `new` is always its own step (a product pick); `merge` joins the step
 * before it (the fill a set pick loads a moment later).
 */
type EditStep = 'auto' | 'new' | 'merge';

/** A text field owns its own Cmd/Ctrl+Z (the price tag designer's rule): the grid's waits. */
function isTextField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== 'function') return false;
  if (el.isContentEditable || el.closest('[contenteditable="true"]')) return true;
  if (el.tagName === 'TEXTAREA') return true;
  if (el.tagName !== 'INPUT') return false;
  const type = (el as HTMLInputElement).type;
  return !['checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'range', 'color'].includes(type);
}

/**
 * The product picker on a row takes the caret (Duplicate line). Found by its label, whose text is
 * "Product on ...", so it does not depend on the column order a user has saved.
 */
function focusProductPicker(key: string) {
  const row = document.querySelector<HTMLElement>(`tr[data-line-key="${key}"]`);
  const label = Array.from(row?.querySelectorAll<HTMLLabelElement>('label') ?? []).find((node) =>
    (node.textContent ?? '').startsWith('Product on '),
  );
  const target = label?.htmlFor ? document.getElementById(label.htmlFor) : null;
  target?.focus();
}

/** Runs once the menu has closed: the copy's product picker takes the caret. */
function focusDuplicated(key: string | null): (() => void) | null {
  return key ? () => focusProductPicker(key) : null;
}

/** Keys are line ids or `new:<id>:<n>`, so a quoted attribute value needs no escaping. */
function focusHeadingInput(key: string) {
  document.querySelector<HTMLElement>(`[data-band-key="${key}"]`)?.focus();
}

/**
 * Where focus goes as a grid menu closes: an action that puts the caret somewhere keeps it there,
 * and the box it is for (a new heading, a renamed one, a duplicated header) takes it NOW, never
 * earlier (INSERT-SECTION-FIX). While the menu plays its exit animation the pointer leaving the
 * clicked item makes Radix focus the menu itself, which would take the caret back, and an empty
 * heading that loses it goes.
 */
function settleMenuFocus(
  event: Event,
  keepFocus: React.RefObject<boolean>,
  focusAfterClose: React.RefObject<(() => void) | null>,
) {
  if (keepFocus.current) event.preventDefault();
  keepFocus.current = false;
  const focus = focusAfterClose.current;
  focusAfterClose.current = null;
  focus?.();
}

/** Runs once the menu has closed: the new heading's box takes the caret. */
function focusAddedHeading(key: string | null): (() => void) | null {
  return key ? () => focusHeadingInput(key) : null;
}

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
  update: (key: string, patch: LineDraft, step?: EditStep) => void;
  selectProduct: (key: string, option: SearchableSelectOption | null) => void;
  toggleRemoved: (key: string) => void;
  /**
   * Returns the key of the row the action added (a heading, or a duplicated line), for the menu
   * to focus once it has closed.
   */
  act: (key: string, action: MenuAction) => string | null;
  /** Drops a heading row left without a name (blurred empty). */
  closeEmptyBand: (key: string) => void;
  /** The name a heading row's box goes by: the line under it, else the end of the table. */
  headingLabelOf: (row: GridRow) => string;
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
      {row.original.number ?? ''}
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
 *
 * One step to type (owner hand test, 10 Nov): the click on the cell opens the editor with its caret
 * at the character clicked; Tab into the cell, Enter or Space opens it with the caret at the end.
 */
function DescriptionCell({ row: tableRow }: CellContext<GridRow, unknown>) {
  const grid = useGrid();
  const row = tableRow.original;
  const { staged } = row;
  const value = staged.draft.description ?? '';
  const labelId = React.useId();
  const [open, setOpen] = React.useState(false);
  /** Where the caret goes when the editor arrives: a text offset, or null for the end. */
  const caretAt = React.useRef<number | null>(null);
  /** A pointer is pressing the cell: its click, not the focus it causes, opens the editor. */
  const pressing = React.useRef(false);
  /**
   * Focus coming back to the cell as the editor closes must not open it again. Held until that
   * focus arrives (the close animation hands it back late, crew re-pass on 6b7c3dac) or until the
   * person moves on: a focus or a press anywhere else.
   */
  const justClosed = React.useRef(false);
  const cellRef = React.useRef<HTMLDivElement | null>(null);
  const releaseGuard = React.useRef<(() => void) | null>(null);
  React.useEffect(() => () => releaseGuard.current?.(), []);
  /** The editor while it is open, so a second click on the cell moves its caret. */
  const editorRef = React.useRef<Editor | null>(null);

  // Stable, so the editor's ready effect runs once per mount rather than on every keystroke.
  const placeCaret = React.useCallback((editor: Editor) => {
    editorRef.current = editor;
    const offset = caretAt.current;
    const at =
      offset === null
        ? Selection.atEnd(editor.state.doc).from
        : docPosAtTextOffset(editor.state.doc, offset);
    editor.commands.focus(at);
  }, []);
  const openAt = (offset: number | null) => {
    caretAt.current = offset;
    if (open && editorRef.current) placeCaret(editorRef.current);
    else setOpen(true);
  };
  const onOpenChange = (next: boolean) => {
    if (next) return; // Opening is the click / focus / key handlers' job, with the caret placed.
    releaseGuard.current?.();
    justClosed.current = true;
    const elsewhere = (event: Event) => {
      if (cellRef.current && event.target instanceof Node && cellRef.current.contains(event.target)) {
        return;
      }
      release();
    };
    const release = () => {
      justClosed.current = false;
      document.removeEventListener('focusin', elsewhere, true);
      document.removeEventListener('pointerdown', elsewhere, true);
      releaseGuard.current = null;
    };
    document.addEventListener('focusin', elsewhere, true);
    document.addEventListener('pointerdown', elsewhere, true);
    releaseGuard.current = release;
    setOpen(false);
    editorRef.current = null;
    grid.markVisited(row.key);
  };

  if (!grid.editing || staged.removed) {
    return <RichDescription value={value} className="text-xs" />;
  }

  const label = grid.labelOf(row);
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        {/* A div, not a <button>: the styled text holds block elements, which a button may not. */}
        <div
          role="button"
          tabIndex={0}
          aria-label={`Description on ${label}`}
          title="Edit description"
          onPointerDown={() => {
            pressing.current = true;
          }}
          ref={cellRef}
          onFocus={() => {
            if (justClosed.current) {
              // The focus handed back by the close: used up, the next one opens again.
              releaseGuard.current?.();
              return;
            }
            if (pressing.current || open) return;
            openAt(null);
          }}
          onBlur={() => {
            pressing.current = false;
          }}
          onClick={(event) => {
            // The popover's own toggle is not used: it would open with no caret.
            event.preventDefault();
            pressing.current = false;
            openAt(textOffsetAtPoint(event.currentTarget, event.clientX, event.clientY));
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              openAt(null);
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
          // The editor takes the focus itself, at the caret (placeCaret), not the first button.
          onOpenAutoFocus={(event) => event.preventDefault()}
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
            onEditorReady={placeCaret}
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
  /** A heading the action added: it takes the caret once the menu has closed. */
  const focusAfterClose = React.useRef<(() => void) | null>(null);

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
    keepFocus.current = action === 'section' || action === 'below' || action === 'duplicate';
    const added = grid.act(row.key, action);
    focusAfterClose.current =
      action === 'duplicate' ? focusDuplicated(added) : focusAddedHeading(added);
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
          onCloseAutoFocus={(event) => settleMenuFocus(event, keepFocus, focusAfterClose)}
        >
          <DropdownMenuItem onSelect={() => run('below')}>
            Insert a line below
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => run('duplicate')}>
            Duplicate line
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

/**
 * A section heading row (AC-QLG03; PROPOSAL-FORM-COLLAPSE, owner 10 Nov: "a heading shouldnt be
 * tied to line"): one full-width bar of its own, with the line drag handle to move it up and down.
 * Moving or removing a line never moves or drops it.
 */
function SectionRow({ row }: { row: GridRow }) {
  const grid = useGrid();
  const value = row.staged.draft.band_label ?? '';
  if (!grid.editing) {
    return (
      <span
        className="block truncate px-3 py-1 text-sm font-semibold text-foreground uppercase"
        title={value}
      >
        {value}
      </span>
    );
  }
  return (
    // The whole bar answers a right-click (Rename, Remove section), not only its input.
    <div data-section-key={row.key} className="flex w-full items-center gap-1">
      <DataGridTableDndRowHandle rowId={row.key} />
      <Input
        variant="sm"
        value={value}
        data-band-key={row.key}
        aria-label={`Section heading ${grid.headingLabelOf(row)}`}
        title={value}
        placeholder="e.g. BILL NO 3 PAGE 15/4, OPTIONAL ITEMS"
        maxLength={150}
        className="max-w-md font-semibold"
        onChange={(event) => grid.update(row.key, { band_label: event.target.value })}
        onBlur={() => grid.closeEmptyBand(row.key)}
      />
    </div>
  );
}

/** A heading row as it floats while dragged: its label, full width, nothing to type into. */
function SectionPreview({ row }: { row: GridRow }) {
  const value = (row.staged.draft.band_label ?? '').trim();
  return (
    <span
      className="block truncate px-3 py-1 text-sm font-semibold text-foreground uppercase"
      title={value}
    >
      {value || 'Section'}
    </span>
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
/** The hidden anchor the quantity block of a grid scope follows (see its column). */
const QTY_BLOCK = 'qty_block';

/**
 * The reader's order without any column the DOCUMENT owns (ids `mx-*`: its header columns, their
 * + buttons, Total qty). Those always follow the hidden anchor in definition order, so a saved
 * order can never pin them and a header the document moves moves on screen too (review B1).
 */
function readerOrder(order: string[]): string[] {
  return order.filter((id) => !id.startsWith('mx-'));
}

/** Every leaf column id, in definition order. */
function leafIds(columns: ColumnDef<GridRow>[]): string[] {
  return columns.flatMap((column) => {
    const children = (column as { columns?: ColumnDef<GridRow>[] }).columns;
    return children?.length ? leafIds(children) : [String(column.id)];
  });
}

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
    enableHiding: true,
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
  // Where a grid scope's quantity block sits (PROPOSAL-FORM-COLLAPSE, Q3): never drawn, but in
  // the column order on every scope, so the reader's saved layout places the block the same way
  // on each one. The block's own columns are data (per document) and follow it.
  {
    id: QTY_BLOCK,
    header: () => null,
    cell: () => null,
    size: 0,
    minSize: 0,
    enableResizing: false,
    enableHiding: false,
    meta: { headerTitle: 'Quantities', draggable: false },
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
 * A plain scope in an edit session: + Column header right after Total (RM), at the end of the
 * header row where the owner pointed (PROPOSAL-FORM-COLLAPSE, 10 Nov), ahead of the row menu.
 */
function withFirstHeaderColumn(columns: ColumnDef<GridRow>[]): ColumnDef<GridRow>[] {
  return columns.flatMap((column) =>
    column.id === 'total'
      ? [column, ADD_FIRST_HEADER_COLUMN as ColumnDef<GridRow>]
      : [column],
  );
}

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
      case QTY_BLOCK:
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
   * Copies whose product has not been changed yet (Duplicate line): their first pick behaves
   * exactly like a pick on a new line, so the rate is the new product's series price or blank,
   * never the source product's rate carried over.
   */
  const freshCopies = React.useRef(new Set<string>());

  /**
   * The newest set, ahead of the next render: a product pick is two writes in one event (the
   * pick and its fill), and each has to build on the other rather than on the props both saw.
   */
  const linesRef = React.useRef(lines);
  linesRef.current = lines;

  /**
   * Undo / Redo (owner hand test, 11 Nov: "just need to have an undo / redo function, see can
   * reuse our price tag template designer"): the designer's own history, shared
   * (`@/hooks/useUndoHistory`, also behind `useCanvasHistory`), over the staged lines. The grid
   * remounts per edit session, so a session starts with nothing to undo.
   */
  const history = useUndoHistory<StagedQuotationLine[]>(lines);
  /** What the grid last staged, by value: anything else arriving is a change from outside. */
  const [initialStaged] = React.useState(() => JSON.stringify(lines));
  const lastStaged = React.useRef(initialStaged);
  /** The row and fields the last keystroke edited, so a run of them is one step. */
  const lastEdit = React.useRef<{ key: string; fields: string } | null>(null);
  // A change the grid did not make (a column change reshaping the cells, a restored or discarded
  // form draft) replaces the lines underneath the history: Undo would bring back a state the
  // rest of the page no longer matches, so the history starts again from here.
  const historyReset = history.reset;
  React.useEffect(() => {
    const now = JSON.stringify(lines);
    if (now === lastStaged.current) return;
    lastStaged.current = now;
    lastEdit.current = null;
    historyReset(lines);
  }, [historyReset, lines]);

  const stage = React.useCallback(
    (next: StagedQuotationLine[]) => {
      linesRef.current = next;
      lastStaged.current = JSON.stringify(next);
      onStage?.(next);
    },
    [onStage],
  );

  const pushHistory = history.pushState;
  const commit = React.useCallback(
    (next: StagedQuotationLine[], merge = false) => {
      if (!merge) lastEdit.current = null;
      pushHistory(next, { merge });
      stage(next);
    },
    [pushHistory, stage],
  );

  const update = React.useCallback(
    (key: string, patch: LineDraft, step: EditStep = 'auto') => {
      const fields = Object.keys(patch).sort().join(',');
      const merge =
        step === 'merge' ||
        (step === 'auto' &&
          lastEdit.current?.key === key &&
          lastEdit.current.fields === fields);
      const next = linesRef.current.map((line) =>
        line.key === key ? { ...line, draft: { ...line.draft, ...patch } } : line,
      );
      commit(next, merge);
      lastEdit.current = step === 'new' ? null : { key, fields };
    },
    [commit],
  );

  const historyUndo = history.undo;
  const historyRedo = history.redo;
  const undo = React.useCallback(() => {
    const restored = historyUndo();
    if (!restored) return;
    lastEdit.current = null;
    stage(restored);
  }, [historyUndo, stage]);
  const redo = React.useCallback(() => {
    const restored = historyRedo();
    if (!restored) return;
    lastEdit.current = null;
    stage(restored);
  }, [historyRedo, stage]);

  /**
   * Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z and Ctrl+Y, the designer's keys, while editing. Listened for on
   * the document, not the grid's own box: a click on an empty part of the grid leaves focus on
   * the page body (crew pass), and the keys must still reach it. Taken only when the key comes
   * from inside the grid or from the body, never from a control elsewhere on the page, and
   * never from a text field (its own text undo).
   */
  const wrapperRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (!editing) return;
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.defaultPrevented) return;
      const target = event.target as Node | null;
      const onBody = target === document.body || target === document.documentElement;
      if (!onBody && !(target && wrapperRef.current?.contains(target))) return;
      if (isTextField(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === 'z') {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      } else if (key === 'y' && !event.shiftKey) {
        event.preventDefault();
        redo();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [editing, redo, undo]);

  /** Leaving a field ends its Undo step: the next edit of the same field is a step of its own. */
  const endEditStep = React.useCallback(() => {
    lastEdit.current = null;
  }, []);

  /**
   * Remove takes the line out at once (owner, 11 Nov: "when remove line then is remove already,
   * dont need to stage it cause now we always save"); Undo is the way back. A row an older
   * autosaved draft still holds as removed is restored the old way.
   */
  const removeLine = React.useCallback(
    (key: string) => {
      const held = linesRef.current.find((line) => line.key === key);
      if (!held) return;
      if (held.removed) {
        onToggleRemoved?.(key);
        return;
      }
      commit(linesRef.current.filter((line) => line.key !== key));
    },
    [commit, onToggleRemoved],
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
      const changed = (option?.value ?? '') !== heldValue;
      const clearPicks: LineDraft = changed
        ? {
            image_attachment_id: '',
            drawing_attachment_id: '',
            // A copy's first new product starts from a new line's blank rate (the fill below
            // puts the series price on it where the series names one).
            ...(freshCopies.current.has(key) ? { unit_price: '' } : {}),
          }
        : {};
      if (changed) freshCopies.current.delete(key);
      if (!option) {
        update(
          key,
          {
            product_id: '',
            product_set_id: '',
            [PICKED_CODE_KEY]: '',
            ...(held.draft.product_set_id ? { complete_set: '' } : {}),
            ...clearPicks,
          },
          'new',
        );
        return;
      }
      if (isSetOption(option.value)) {
        const setId = option.value.slice(SET_OPTION_PREFIX.length);
        update(
          key,
          {
            product_id: '',
            product_set_id: setId,
            // The option's label IS the code (sets and products alike).
            [PICKED_CODE_KEY]: option.label,
            uom: 'SET',
            ...clearPicks,
          },
          'new',
        );
        // The parts, brand, price and Complete set need the set's detail; applied only if the
        // row still names this set when it arrives.
        void fillFromSet?.(setId)
          .then((filled) => {
            const now = linesRef.current.find((line) => line.key === key);
            if (now?.draft.product_set_id !== setId) return;
            // A typed brand is never overwritten by the set's.
            const { brand_snapshot: brand, ...rest } = filled;
            // Part of the pick: one Undo takes back the set and its fill together.
            update(
              key,
              (now.draft.brand_snapshot ?? '').trim() ? rest : { ...rest, brand_snapshot: brand ?? '' },
              'merge',
            );
          })
          .catch(() => toast.error('Could not load that set'));
        return;
      }
      update(
        key,
        {
          product_id: option.value,
          product_set_id: '',
          [PICKED_CODE_KEY]: option.label,
          // Off a set, its parts text no longer describes the line.
          ...(held.draft.product_set_id ? { complete_set: '' } : {}),
          // Before the fill: a fresh copy's blank rate must not overwrite the series price it puts.
          ...clearPicks,
          ...fillFromProduct(option),
        },
        'new',
      );
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

  /** A heading row, new in this session, with nothing typed yet. */
  const newHeading = React.useCallback((): StagedQuotationLine => {
    nextNewId.current += 1;
    return {
      id: null,
      key: `new:${instanceKey}:${nextNewId.current}`,
      line: null,
      draft: sectionDraft(),
      removed: false,
    };
  }, [instanceKey]);

  const focusHeading = React.useCallback(
    (key: string) => focusSoon(`[data-band-key="${key}"]`),
    [focusSoon],
  );

  /** A heading row blurred with no name is not a heading: it goes, and no line moves. */
  const closeEmptyBand = React.useCallback(
    (key: string) => {
      const held = linesRef.current.find((line) => line.key === key);
      if (!held || !isSectionDraft(held.draft)) return;
      if ((held.draft.band_label ?? '').trim() !== '') return;
      commit(linesRef.current.filter((line) => line.key !== key));
    },
    [commit],
  );

  const addLine = React.useCallback(
    (withSection: boolean) => {
      const added = newLine();
      if (!withSection) {
        commit([...linesRef.current, added]);
        return;
      }
      // Add a section: a heading row of its own, then a line under it to start the section.
      const heading = newHeading();
      commit([...linesRef.current, heading, added]);
      focusHeading(heading.key);
    },
    [commit, focusHeading, newHeading, newLine],
  );

  const act = React.useCallback(
    (key: string, action: MenuAction): string | null => {
      const current = linesRef.current;
      const index = current.findIndex((line) => line.key === key);
      if (index < 0) return null;
      switch (action) {
        case 'below': {
          const added = newLine();
          commit([
            ...current.slice(0, index + 1),
            added,
            ...current.slice(index + 1),
          ]);
          return null;
        }
        case 'section': {
          // Insert a section above: a heading row of its own, before this line. Its box takes the
          // caret from the menu, once that has closed (settleMenuFocus).
          const heading = newHeading();
          commit([...current.slice(0, index), heading, ...current.slice(index)]);
          return heading.key;
        }
        case 'remove':
          removeLine(key);
          return null;
        case 'duplicate': {
          const source = current[index];
          if (source.removed || isSectionDraft(source.draft)) return null;
          nextNewId.current += 1;
          const copy: StagedQuotationLine = {
            id: null,
            key: `new:${instanceKey}:${nextNewId.current}`,
            line: null,
            draft: {
              ...source.draft,
              // A carried heading belongs to the source; the copy sits inside the same section.
              band_label: '',
              // The copy has no stored row to name it, so it carries the code it was copied with.
              [PICKED_CODE_KEY]:
                source.draft[PICKED_CODE_KEY] || (source.line?.product_code ?? ''),
            },
            removed: false,
          };
          freshCopies.current.add(copy.key);
          commit([...current.slice(0, index + 1), copy, ...current.slice(index + 1)]);
          return copy.key;
        }
      }
    },
    [commit, instanceKey, newHeading, newLine, removeLine],
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

  const allRows = React.useMemo<GridRow[]>(() => {
    let counted = 0;
    return lines.map((staged, index) => {
      const heading = isSectionDraft(staged.draft);
      if (!heading) counted += 1;
      return { key: staged.key, index, number: heading ? null : counted, staged };
    });
  }, [lines]);
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
        (row.number ?? row.index + 1) - 1,
        !row.staged.line && productId
          ? (productCodeOf(productId) ?? (row.staged.draft[PICKED_CODE_KEY] || null))
          : null,
      );
    },
    [productCodeOf],
  );

  const headingLabelOf = React.useCallback(
    (row: GridRow) => {
      const below = allRows.slice(row.index + 1).find((next) => !isSectionDraft(next.staged.draft));
      return below ? `above ${labelOf(below)}` : 'at the end';
    },
    [allRows, labelOf],
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
      toggleRemoved: removeLine,
      act,
      closeEmptyBand,
      headingLabelOf,
      openPreview,
      visited,
      markVisited,
      labelOf,
      itemNotes,
    }),
    [
      act,
      brandOptions,
      closeEmptyBand,
      headingLabelOf,
      editing,
      fetchProducts,
      itemNotes,
      labelOf,
      markVisited,
      onUomRetry,
      removeLine,
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
  /** Returns the copy's key; its menu hands the copy the caret once it has closed. */
  const duplicateHeader = React.useCallback(
    (headerKey: string): string | null => {
      const header = headersRef.current.find((row) => row.key === headerKey);
      if (!header) return null;
      const before = usedKeys(headersRef.current);
      const next = duplicateMatrixHeader(headersRef.current, headerKey, `${header.label} (copy)`);
      change(next);
      return Array.from(usedKeys(next)).find((key) => !before.has(key)) ?? null;
    },
    [change],
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
          .filter((line) => !line.removed && !isSectionDraft(line.draft))
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
      duplicateHeader,
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
      duplicateHeader,
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

  /**
   * The reader's column order, held here so it can be completed before TanStack reads it: a
   * column the saved order has never seen (this document's quantity columns, a header just added)
   * goes where it is defined, after its neighbour, not to the far right.
   */
  const [columnOrder, setColumnOrder] = React.useState<string[]>([]);

  const columns = React.useMemo(
    () =>
      isMatrix
        ? matrixColumns(headers, columnsEditable)
        : columnsEditable
          ? withFirstHeaderColumn(COLUMNS)
          : COLUMNS,
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
        [QTY_BLOCK]: false,
      },
      columnOrder: columnOrder.length
        ? mergeColumnOrderWithLeafColumns(columnOrder, leafIds(columns))
        : columnOrder,
    },
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: (updater) =>
      setColumnOrder((previous) =>
        readerOrder(typeof updater === 'function' ? updater(previous) : updater),
      ),
    enableSorting: false,
    columnResizeMode: 'onChange',
  });

  /**
   * What a right-click is on: a section bar, or a line row. Read off the DOM the event came from,
   * so one menu serves every row (owner hand test, points 2 and 3).
   */
  const [menuTarget, setMenuTarget] = React.useState<{
    kind: 'line' | 'section' | 'header';
    key: string;
  } | null>(null);
  /**
   * Null outside the rows and bars, and over an editable control inside one (the heading, the
   * description, Qty): there the browser's own menu shows, for copy, paste and spelling.
   */
  const targetOf = (element: Element | null) => {
    // A column header's whole box, its name included, answers with Duplicate (owner, 10 Nov:
    // right-click rather than an icon). Every other editable control keeps the browser's menu.
    const group = element?.closest<HTMLElement>('[data-matrix-header-key]');
    if (group?.dataset.matrixHeaderKey && columnsEditable)
      return { kind: 'header' as const, key: group.dataset.matrixHeaderKey };
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
  /** Puts the caret where the chosen item asked, once the menu has closed. */
  const focusAfterMenu = React.useRef<(() => void) | null>(null);
  const menuLine = menuTarget
    ? (lines.find((line) => line.key === menuTarget.key) ?? null)
    : null;

  const renderHeadingRow = React.useCallback(
    (row: GridRow, options?: { overlay?: boolean }) =>
      !isSectionDraft(row.staged.draft) ? null : options?.overlay ? (
        // The drag preview: the heading itself, static (owner hand test, 10 Nov 2026).
        <SectionPreview row={row} />
      ) : (
        <SectionRow row={row} />
      ),
    [],
  );

  const galleryItems = preview?.items ?? [];

  const renameSection = (key: string) => {
    keepFocusAfterMenu.current = true;
    focusAfterMenu.current = () => focusHeadingInput(key);
  };
  const removeSection = (key: string) => {
    // The heading row alone: no line moves (PROPOSAL-FORM-COLLAPSE).
    commit(linesRef.current.filter((line) => line.key !== key));
  };

  return (
    <GridContext.Provider value={context}>
     <MatrixGridProvider value={matrixContext}>
      <div ref={wrapperRef} className="min-w-0 space-y-2" onBlur={endEditStep}>
        <DataGrid
          table={table}
          recordCount={visibleRows.length}
          isLoading={false}
          // Rows render under the default layout while the saved one loads, rather than as
          // skeletons: an editor must never hide the lines somebody is about to type into.
          loadingMode="spinner"
          // ONE per-user layout for edit and view, plain and grid scopes alike (PROPOSAL-FORM-
          // COLLAPSE, Q3, owner 10 Nov 2026). A grid scope's own columns are data: they follow
          // the hidden quantity-block anchor, and the merge above places any it has not seen.
          listingKey="projects.projects.view::quotation-lines"
          tableLayout={{ width: 'fixed', columnsResizable: true, dense: true }}
          tableClassNames={{ headerRow: 'text-xs' }}
          emptyMessage={lines.length === 0 ? emptyHint : filterEmptyHint}
          renderFullRow={renderHeadingRow}
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
              {editing && (
                <div className="flex items-center gap-0.5">
                  <Button
                    type="button"
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    aria-label="Undo"
                    title="Undo (Ctrl+Z / Cmd+Z)"
                    disabled={!history.canUndo}
                    onClick={undo}
                  >
                    <Undo2 className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    aria-label="Redo"
                    title="Redo (Shift+Ctrl+Z / Shift+Cmd+Z)"
                    disabled={!history.canRedo}
                    onClick={redo}
                  >
                    <Redo2 className="size-4" />
                  </Button>
                </div>
              )}
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
                    // The fixed columns drag the DataGrid way on every scope (Q3); a grid
                    // scope's own header columns do not (their order is the document's, moved
                    // by their grips), so the block stays together.
                    columnsDraggable
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
                  </div>
                )}
              </div>
            </ContextMenuTrigger>
            <ContextMenuContent
              className="w-52"
              onCloseAutoFocus={(event) =>
                settleMenuFocus(event, keepFocusAfterMenu, focusAfterMenu)
              }
            >
              {menuTarget?.kind === 'header' ? (
                <ContextMenuItem
                  disabled={Boolean(matrix?.saving) || pending !== null}
                  onSelect={() => {
                    keepFocusAfterMenu.current = true;
                    const copy = duplicateHeader(menuTarget.key);
                    focusAfterMenu.current = copy ? () => setFocusKey(copy) : null;
                  }}
                >
                  Duplicate
                </ContextMenuItem>
              ) : menuTarget?.kind === 'section' ? (
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
                      focusAfterMenu.current = focusDuplicated(act(menuTarget.key, 'duplicate'));
                    }}
                  >
                    Duplicate line
                  </ContextMenuItem>
                  <ContextMenuItem
                    disabled={Boolean(menuLine?.removed)}
                    onSelect={() => {
                      keepFocusAfterMenu.current = true;
                      focusAfterMenu.current = focusAddedHeading(act(menuTarget.key, 'section'));
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
