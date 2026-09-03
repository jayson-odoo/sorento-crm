'use client';

import * as React from 'react';
import { CSSProperties, Fragment, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { Checkbox } from '@/components/ui/checkbox';
import { useDataGrid } from '@/components/ui/data-grid';
import { DataGridTableDnd } from '@/components/ui/data-grid-table-dnd';
import { Cell, Column, flexRender, Header, HeaderGroup, Row, Table } from '@tanstack/react-table';
import { cva } from 'class-variance-authority';
import { mergeColumnOrderWithLeafColumns } from '@/lib/listing-column-preferences/mergeColumnOrder';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { toAbsoluteUrl } from '@/lib/helpers';
import { useHorizontalOverflow } from '@/hooks/use-horizontal-overflow';
import { cn } from '@/lib/utils';

/**
 * Appends the list state the grid is showing to a row's detail href.
 *
 * The detail page's pager walks the page the user came FROM, so the URL has to
 * name that page. Param names come from `buildDetailSearch` (the same builder
 * the list GET uses), and anything the caller put in its own query string wins -
 * that is where a filter the list keeps outside TanStack rides along.
 */
function appendListState<TData>(href: string, table: Table<TData>): string {
  // A fragment has to survive, and it sits AFTER the query string - splitting on
  // '?' alone turns `/orders/a1#lines` into a param named `a1#lines`.
  const hashAt = href.indexOf('#');
  const hash = hashAt === -1 ? '' : href.slice(hashAt);
  const [path, ownSearch] = (hashAt === -1 ? href : href.slice(0, hashAt)).split('?');
  const state = table.getState();
  const params = new URLSearchParams(
    buildDetailSearch({
      pageIndex: state.pagination?.pageIndex ?? 0,
      pageSize: state.pagination?.pageSize ?? 50,
      sorting: state.sorting,
      searchQuery: typeof state.globalFilter === 'string' ? state.globalFilter : '',
    }),
  );
  if (ownSearch) {
    for (const [key, value] of new URLSearchParams(ownSearch)) params.set(key, value);
  }
  return `${path}?${params.toString()}${hash}`;
}

const headerCellSpacingVariants = cva('', {
  variants: {
    size: {
      dense: 'px-2.5 h-8',
      default: 'px-4',
    },
  },
  defaultVariants: {
    size: 'default',
  },
});

const bodyCellSpacingVariants = cva('', {
  variants: {
    size: {
      dense: 'px-2.5 py-2',
      // Roomier default row spacing - every CRM list matches the Administrative
      // Users density. `h-[60px]` acts as a row MIN-height in tables (cells are
      // align-middle), so single-line rows get the same breathing room as the
      // avatar rows without inflating the avatar rows themselves.
      default: 'px-4 py-3 h-[60px]',
    },
  },
  defaultVariants: {
    size: 'default',
  },
});

function getPinningStyles<TData>(column: Column<TData>): CSSProperties {
  const isPinned = column.getIsPinned();

  return {
    left: isPinned === 'left' ? `${column.getStart('left')}px` : undefined,
    right: isPinned === 'right' ? `${column.getAfter('right')}px` : undefined,
    position: isPinned ? 'sticky' : 'relative',
    width: column.getSize(),
    // `--z-sticky-content` (css/config.reui.css), not a bare number: a pinned
    // column has to beat the columns scrolling under it, but stay below the
    // app shell's fixed header/sidebar, or the collapsed sidebar's hover
    // flyout renders under a frozen column instead of over it.
    zIndex: isPinned ? 'var(--z-sticky-content)' : 0,
  };
}

function DataGridTableBase({ children }: { children: ReactNode }) {
  const { props, table } = useDataGrid();

  // What stops a `table-fixed w-full` grid from squeezing six columns into a
  // phone: the table is at least as wide as its columns want to be, and the
  // scroller (data-grid-scroller) carries the overflow. Where the columns
  // already fit, `w-full` still wins.
  //
  // The grid has to be the ONLY scrollport on that axis. A list that wrapped it
  // in a Radix `ScrollArea` gave the table a `display: table` ancestor, which
  // shrink-fits: `data-grid-scroller` then measured scrollWidth === clientWidth,
  // never overflowed, and still swallowed the wheel gesture through
  // `overscroll-x-contain` - so 161 lists could not be scrolled sideways at all.
  // Those wrappers are gone; keep it that way.
  //
  // It has to be a DEFINITE length. `min-width: max-content` is meaningless on a
  // `table-layout: fixed` table - fixed layout ignores content by design - and
  // Chrome resolves it to its "infinite" sentinel of 1,000,000px, then the fixed
  // algorithm scales every column up to fill it. Measured on Products at
  // 1280x800: columns summing to 2367px laid out 1,000,000px wide, each column
  // 422x its size, the last header at x=962,282 and nothing but the checkbox on
  // screen. `getTotalSize()` is the sum of the visible leaf column sizes, so it
  // is that same width as a number the browser has nothing to resolve - and it
  // tracks a column the user has resized, or one restored from their saved
  // listing preferences.
  const minWidth = table.getTotalSize();

  return (
    <table
      data-slot="data-grid-table"
      style={minWidth > 0 ? { minWidth: `${minWidth}px` } : undefined}
      className={cn(
        // `tabular-nums` keeps figures aligned down a column.
        'w-full tabular-nums align-middle caption-bottom text-left rtl:text-right text-foreground font-normal text-sm',
        !props.tableLayout?.columnsDraggable && 'border-separate border-spacing-0',
        props.tableLayout?.width === 'fixed' ? 'table-fixed' : 'table-auto',
        props.tableClassNames?.base,
      )}
    >
      {children}
    </table>
  );
}

function DataGridTableHead({ children }: { children: ReactNode }) {
  const { props } = useDataGrid();

  return (
    <thead
      className={cn(
        props.tableClassNames?.header,
        props.tableLayout?.headerSticky && props.tableClassNames?.headerSticky,
      )}
    >
      {children}
    </thead>
  );
}

function DataGridTableHeadRow<TData>({
  children,
  headerGroup,
}: {
  children: ReactNode;
  headerGroup: HeaderGroup<TData>;
}) {
  const { props } = useDataGrid();

  return (
    <tr
      key={headerGroup.id}
      className={cn(
        'bg-muted/40',
        props.tableLayout?.headerBorder && '[&>th]:border-b',
        props.tableLayout?.cellBorder && '[&_>:last-child]:border-e-0',
        props.tableLayout?.stripped && 'bg-transparent',
        props.tableLayout?.headerBackground === false && 'bg-transparent',
        props.tableClassNames?.headerRow,
      )}
    >
      {children}
    </tr>
  );
}

/**
 * A grid with column GROUPS repeats every ungrouped column twice: TanStack puts a
 * placeholder in the group row and the real header in the leaf row underneath, which draws
 * an empty band above most of the header. The workbook the reports grid mirrors merges
 * those cells vertically, so here the PLACEHOLDER carries the header and spans the
 * remaining rows, and `skipMergedLeafHeader` drops the leaf it stands in for.
 *
 * A flat listing has one header row and therefore no placeholders at all, so both helpers
 * are no-ops on every other listing in the app.
 */
function headerRowSpan<TData>(header: Header<TData, unknown>, rowCount: number): number {
  // `header.depth` is 1-based: the first header row is depth 1.
  return header.isPlaceholder ? Math.max(rowCount - (header.depth - 1), 1) : 1;
}

function skipMergedLeafHeader<TData>(header: Header<TData, unknown>, rowCount: number): boolean {
  if (rowCount <= 1) return false; // a flat listing: nothing to merge
  if (header.column.parent) return false; // a grouped column keeps its own cell
  if (header.subHeaders.length > 0 && !header.isPlaceholder) return false; // a real group header
  // What is left is an ungrouped column below the first header row: the placeholder in
  // that first row already carries it, spanning down to here.
  return header.depth > 1;
}

function DataGridTableHeadRowCell<TData>({
  children,
  header,
  dndRef,
  dndStyle,
  dndDragging,
  rowSpan,
}: {
  children: ReactNode;
  header: Header<TData, unknown>;
  dndRef?: React.Ref<HTMLTableCellElement>;
  dndStyle?: CSSProperties;
  /** True while THIS column is the one being dragged (dnd-kit's `isDragging`). */
  dndDragging?: boolean;
  rowSpan?: number;
}) {
  const { props } = useDataGrid();

  const { column } = header;
  const isPinned = column.getIsPinned();
  const isLastLeftPinned = isPinned === 'left' && column.getIsLastColumn('left');
  const isFirstRightPinned = isPinned === 'right' && column.getIsFirstColumn('right');
  const headerCellSpacing = headerCellSpacingVariants({
    size: props.tableLayout?.dense ? 'dense' : 'default',
  });

  return (
    <th
      key={header.id}
      ref={dndRef}
      // 1 for every flat listing, so this is a no-op there. A grid whose columns are
      // grouped (the reports detail grid's "Expected year of delivery" ticks) needs the
      // group header to span its leaves, or the two header rows do not line up.
      colSpan={header.colSpan}
      // 1 on every flat listing. A single-level header in a GROUPED grid spans both header
      // rows instead of leaving an empty cell above itself (see headerRowSpan).
      rowSpan={rowSpan && rowSpan > 1 ? rowSpan : undefined}
      style={{
        ...(props.tableLayout?.width === 'fixed' && {
          width: `${header.getSize()}px`,
        }),
        // Pinning normally wins. Column drag-and-drop is on by default and
        // dnd-kit sets `position: relative` + `zIndex: 0` on every cell; spread
        // after the pinning styles it silently turned a pinned column back into
        // an ordinary one that scrolled away. The drag transform and transition
        // survive - only the stickiness wins.
        //
        // Driven by the pinned state itself, so it follows whatever the list
        // pinned rather than assuming a column.
        //
        // While THIS column is the one being dragged, the order flips: sticky
        // beats dnd-kit's `position: relative`, so the transform had no effect
        // and a pinned column could not be dragged at all.
        ...(dndDragging
          ? { ...(isPinned ? getPinningStyles(column) : null), ...dndStyle }
          : { ...dndStyle, ...(isPinned ? getPinningStyles(column) : null) }),
      }}
      data-pinned={isPinned || undefined}
      data-last-col={isLastLeftPinned ? 'left' : isFirstRightPinned ? 'right' : undefined}
      className={cn(
        'relative h-10 text-left rtl:text-right align-middle font-normal text-accent-foreground [&:has([role=checkbox])]:pe-0',
        headerCellSpacing,
        props.tableLayout?.cellBorder && 'border-e',
        props.tableLayout?.columnsResizable && column.getCanResize() && 'truncate',
        isPinned &&
          '[&:not([data-pinned]):has(+[data-pinned])_div.cursor-col-resize:last-child]:opacity-0 [&[data-last-col=left]_div.cursor-col-resize:last-child]:opacity-0 [&[data-pinned=left][data-last-col=left]]:border-e! [&[data-pinned=right]:last-child_div.cursor-col-resize:last-child]:opacity-0 [&[data-pinned=right][data-last-col=right]]:border-s! [&[data-pinned][data-last-col]]:border-border data-pinned:bg-muted/90 data-pinned:backdrop-blur-xs',
        header.column.columnDef.meta?.headerClassName,
        column.getIndex() === 0 || column.getIndex() === header.headerGroup.headers.length - 1
          ? props.tableClassNames?.edgeCell
          : '',
      )}
    >
      {children}
    </th>
  );
}

function DataGridTableHeadRowCellResize<TData>({ header }: { header: Header<TData, unknown> }) {
  const { column } = header;
  const resizeHandler = header.getResizeHandler();

  return (
    <div
      {...{
        onDoubleClick: () => column.resetSize(),
        onPointerDown: (e: React.PointerEvent) => {
          // Prevent dnd-kit from starting a column drag while the user is resizing.
          e.stopPropagation();
          // Capture the pointer so a fast drag that leaves the 16px handle - or
          // leaves the window - keeps resizing instead of silently stopping.
          (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
        },
        onMouseDown: (e: React.MouseEvent) => {
          e.stopPropagation();
          resizeHandler(e);
        },
        onTouchStart: (e: React.TouchEvent) => {
          e.stopPropagation();
          resizeHandler(e);
        },
        className:
          'absolute top-0 h-full w-4 cursor-col-resize user-select-none touch-none -end-2 z-10 flex justify-center before:absolute before:w-px before:inset-y-0 before:bg-border before:-translate-x-px',
      }}
    />
  );
}

function DataGridTableRowSpacer() {
  return <tbody aria-hidden="true" className="h-2"></tbody>;
}

function DataGridTableBody({ children }: { children: ReactNode }) {
  const { props } = useDataGrid();

  return (
    <tbody
      className={cn(
        '[&_tr:last-child]:border-0',
        props.tableLayout?.rowRounded && '[&_td:first-child]:rounded-s-lg [&_td:last-child]:rounded-e-lg',
        props.tableClassNames?.body,
      )}
    >
      {children}
    </tbody>
  );
}

function DataGridTableBodyRowSkeleton({ children }: { children: ReactNode }) {
  const { table, props } = useDataGrid();

  return (
    <tr
      className={cn(
        'hover:bg-muted/40 data-[state=selected]:bg-muted/50',
        (props.rowHref || props.onRowClick) && 'cursor-pointer',
        !props.tableLayout?.stripped &&
          props.tableLayout?.rowBorder &&
          'border-b border-border [&:not(:last-child)>td]:border-b',
        props.tableLayout?.cellBorder && '[&_>:last-child]:border-e-0',
        props.tableLayout?.stripped && 'odd:bg-muted/90 hover:bg-transparent odd:hover:bg-muted',
        table.options.enableRowSelection && '[&_>:first-child]:relative',
        props.tableClassNames?.bodyRow,
      )}
    >
      {children}
    </tr>
  );
}

function DataGridTableBodyRowSkeletonCell<TData>({ children, column }: { children: ReactNode; column: Column<TData> }) {
  const { props, table } = useDataGrid();
  const bodyCellSpacing = bodyCellSpacingVariants({
    size: props.tableLayout?.dense ? 'dense' : 'default',
  });

  return (
    <td
      className={cn(
        'align-middle',
        bodyCellSpacing,
        props.tableLayout?.cellBorder && 'border-e',
        props.tableLayout?.columnsResizable && column.getCanResize() && 'truncate',
        column.columnDef.meta?.cellClassName,
        props.tableLayout?.columnsPinnable &&
          column.getCanPin() &&
          '[&[data-pinned=left][data-last-col=left]]:border-e! [&[data-pinned=right][data-last-col=right]]:border-s! [&[data-pinned][data-last-col]]:border-border data-pinned:bg-background/90 data-pinned:backdrop-blur-xs"',
        column.getIndex() === 0 || column.getIndex() === table.getVisibleFlatColumns().length - 1
          ? props.tableClassNames?.edgeCell
          : '',
      )}
    >
      {children}
    </td>
  );
}

/**
 * Anything inside a row that owns its own click.
 *
 * A row that opens a record must not also swallow the checkbox, the action
 * button, the inline editor or the menu item sitting in one of its cells. The
 * alternative is every one of those remembering `stopPropagation`, and the one
 * that forgets navigates away in the middle of an action.
 */
const ROW_INTERACTIVE_SELECTOR =
  'a,button,input,select,textarea,label,[role="checkbox"],[role="menuitem"],[role="combobox"]';

/**
 * Click, middle-click and keyboard handling for a row that opens something.
 *
 * Shared by BOTH row branches on purpose. The `rowHref` branch had all of this
 * and the `onRowClick` branch had a bare `onClick` on the `<tr>`, so a Brands
 * row carrying a "View products" link navigated to products AND set the edit
 * lightbox's state on the way out - which is why the row read as doing nothing.
 * The same hole put the row's open action out of reach of the keyboard and left
 * it with no role for assistive tech to announce.
 *
 * `opensUrl` is what separates the two: a row that opens a URL honours the
 * modifiers an anchor honours and can go to a new tab; a row that opens a
 * lightbox has no second tab, so a modified click just opens it here.
 *
 * No `role` on the `<tr>`. S1 put `role="link"` there and it looked right, but
 * an explicit role REPLACES the implicit one, so the row stopped being a `row`
 * to assistive tech and the table lost its grid semantics with it. The
 * fulfilment board's own tests caught it - `getAllByRole('row')` returned
 * nothing. `tabIndex` plus Enter and Space is what S1-06 and D3 actually ask
 * for ("the whole row is the target, keyboard included"), and it costs the
 * table nothing.
 */
function rowOpenProps({
  opensUrl,
  open,
}: {
  opensUrl: boolean;
  open: (newTab: boolean) => void;
}): React.ComponentProps<'tr'> {
  const fromOwnControl = (target: EventTarget | null) =>
    Boolean((target as Element | null)?.closest?.(ROW_INTERACTIVE_SELECTOR));

  return {
    tabIndex: 0,
    onClick: (event) => {
      // The PRIMARY button only. A real middle click fires auxclick alone, but a
      // synthetic dispatch, assistive tech and Firefox autoscroll also deliver a
      // `click` carrying button 1 - and React's onClick does not filter by
      // button. Without this the row opened the record in a new tab from
      // auxclick AND pushed the current tab to the same record from the click,
      // so the user lost the list they were reading. Opening on both would be
      // no better: two tabs. auxclick owns the new tab, click owns this one.
      if (event.button !== 0) return;
      // A control in a cell keeps its own click.
      if (fromOwnControl(event.target)) return;
      // Same modifiers an anchor honours, so the row behaves like the link it claims to be.
      open(opensUrl && (event.metaKey || event.ctrlKey || event.shiftKey));
    },
    onAuxClick: (event) => {
      if (!opensUrl) return;
      if (event.button !== 1) return;
      if (fromOwnControl(event.target)) return;
      event.preventDefault();
      open(true);
    },
    onKeyDown: (event) => {
      // Only the ROW's own keystrokes: Space in a cell's text input types a
      // space, and Space on the selection checkbox ticks the row.
      if (event.target !== event.currentTarget) return;
      if (event.key !== 'Enter' && event.key !== ' ') return;
      // Space scrolls the page otherwise, and Enter would submit a surrounding form.
      event.preventDefault();
      open(opensUrl && (event.metaKey || event.ctrlKey || event.shiftKey));
    },
  };
}

/**
 * The row when the list gave it a record to open.
 *
 * Split out so `useRouter` is only called by a grid that actually navigates -
 * Next throws "expected app router to be mounted" rather than returning null,
 * and a grid whose rows are not links must not require a router to render.
 */
function LinkableBodyRow({
  href,
  rowProps,
  children,
}: {
  href: string;
  rowProps: React.ComponentProps<'tr'>;
  children: ReactNode;
}) {
  const router = useRouter();

  const openRecord = (newTab = false) => {
    if (newTab) {
      // `router.push` applies the deploy base path itself; `window.open` does not,
      // so a sub-path deploy would open a 404 in the new tab.
      window.open(toAbsoluteUrl(href), '_blank', 'noopener,noreferrer');
    } else {
      router.push(href);
    }
  };

  return (
    // `rowOpenProps` BEFORE the dnd listeners `rowProps` carries: a future
    // list that is both draggable and openable would otherwise have its
    // keyboard-drag onKeyDown replaced by this one, silently.
    <tr {...rowOpenProps({ opensUrl: true, open: openRecord })} {...rowProps}>
      {children}
    </tr>
  );
}

function DataGridTableBodyRow<TData>({
  children,
  row,
  dndRef,
  dndStyle,
  dndAttributes,
  dndListeners,
}: {
  children: ReactNode;
  row: Row<TData>;
  dndRef?: React.Ref<HTMLTableRowElement>;
  dndStyle?: CSSProperties;
  dndAttributes?: Record<string, unknown>;
  dndListeners?: Record<string, unknown>;
}) {
  const { props, table } = useDataGrid();

  // The whole row opens the record, from anywhere on it, by mouse or by keyboard.
  // 78 of 193 lists did this and 26 had a detail route with no way to reach it.
  const href = props.rowHref ? appendListState(props.rowHref(row.original), table) : undefined;

  // A record on its way out stays visible and says so, rather than vanishing
  // before the reader can cancel (S6-07).
  const isPending = props.rowPending?.(row.original) ?? false;

  const rowProps: React.ComponentProps<'tr'> = {
    ref: dndRef,
    style: { ...(dndStyle ? dndStyle : null) },
    'data-state': table.options.enableRowSelection && row.getIsSelected() ? 'selected' : undefined,
    'data-pending': isPending ? 'true' : undefined,
    ...(dndAttributes ?? {}),
    ...(dndListeners ?? {}),
    className: cn(
      'hover:bg-muted/40 data-[state=selected]:bg-muted/50',
      isPending && 'opacity-50',
      (href || props.onRowClick) && 'cursor-pointer',
      !props.tableLayout?.stripped &&
        props.tableLayout?.rowBorder &&
        'border-b border-border [&:not(:last-child)>td]:border-b',
      props.tableLayout?.cellBorder && '[&_>:last-child]:border-e-0',
      props.tableLayout?.stripped && 'odd:bg-muted/90 hover:bg-transparent odd:hover:bg-muted',
      table.options.enableRowSelection && '[&_>:first-child]:relative',
      props.tableClassNames?.bodyRow,
    ),
  } as React.ComponentProps<'tr'>;

  if (href) {
    return (
      <LinkableBodyRow href={href} rowProps={rowProps}>
        {children}
      </LinkableBodyRow>
    );
  }

  if (props.onRowClick) {
    // A lightbox, not a URL: there is no second tab to open it in.
    return (
      <tr
        {...rowOpenProps({ opensUrl: false, open: () => props.onRowClick?.(row.original) })}
        {...rowProps}
      >
        {children}
      </tr>
    );
  }

  return <tr {...rowProps}>{children}</tr>;
}

/**
 * A totals row, INSIDE the table, so the number lines up under the column it sums.
 *
 * Rendered only when a column declares `footer` on its definition, so no existing grid gains a
 * stray empty row. A total placed beside the toolbar instead - "1 PO, RM 1,810,640.62" - reads as
 * a chip competing with the buttons, and nothing tells the reader WHICH column it totals; sitting
 * under its own column the number needs no label at all.
 */
/**
 * The footer rows worth drawing.
 *
 * A flat grid has exactly one, so this is `getFooterGroups()` unchanged. A grid with
 * COLUMN GROUPS gets a second, mirror row for the group headers, and no group declares a
 * `footer`, so it would render as an empty bordered strip under the totals.
 */
function footerGroupsWithContent<TData>(table: Table<TData>) {
  return table
    .getFooterGroups()
    .filter((group) => group.headers.some((h) => !h.isPlaceholder && Boolean(h.column.columnDef.footer)));
}

function DataGridTableFoot({ children }: { children: ReactNode }) {
  const { props } = useDataGrid();

  return (
    <tfoot
      className={cn(
        'border-t border-border bg-muted/30 font-semibold',
        props.tableClassNames?.footer,
      )}
    >
      {children}
    </tfoot>
  );
}

function DataGridTableFootRowCell<TData>({
  children,
  header,
}: {
  children: ReactNode;
  header: Header<TData, unknown>;
}) {
  const { props } = useDataGrid();
  const { column } = header;

  const bodyCellSpacing = bodyCellSpacingVariants({
    size: props.tableLayout?.dense ? 'dense' : 'default',
  });

  return (
    <td
      className={cn(
        'align-middle text-sm',
        bodyCellSpacing,
        // A footer carries one number, never an avatar, so it does not need the row min-height.
        'h-auto',
        props.tableLayout?.cellBorder && 'border-e',
        // Inherits the column's own alignment: a right-aligned money column totals right.
        column.columnDef.meta?.cellClassName,
      )}
      style={{
        ...(props.tableLayout?.columnsPinnable && column.getCanPin()
          ? getPinningStyles(column)
          : null),
        width: props.tableLayout?.width === 'fixed' ? `${header.getSize()}px` : undefined,
      }}
    >
      {children}
    </td>
  );
}

function DataGridTableBodyRowExpandded<TData>({ row }: { row: Row<TData> }) {
  const { props, table } = useDataGrid();

  return (
    <tr className={cn(props.tableLayout?.rowBorder && '[&:not(:last-child)>td]:border-b')}>
      <td colSpan={row.getVisibleCells().length}>
        {table
          .getAllColumns()
          .find((column) => column.columnDef.meta?.expandedContent)
          ?.columnDef.meta?.expandedContent?.(row.original)}
      </td>
    </tr>
  );
}

function DataGridTableBodyRowCell<TData>({
  children,
  cell,
  dndRef,
  dndStyle,
  dndDragging,
}: {
  children: ReactNode;
  cell: Cell<TData, unknown>;
  dndRef?: React.Ref<HTMLTableCellElement>;
  dndStyle?: CSSProperties;
  /** True while THIS column is the one being dragged (dnd-kit's `isDragging`). */
  dndDragging?: boolean;
}) {
  const { props } = useDataGrid();

  const { column, row } = cell;
  const isPinned = column.getIsPinned();
  const isLastLeftPinned = isPinned === 'left' && column.getIsLastColumn('left');
  const isFirstRightPinned = isPinned === 'right' && column.getIsFirstColumn('right');
  const bodyCellSpacing = bodyCellSpacingVariants({
    size: props.tableLayout?.dense ? 'dense' : 'default',
  });

  return (
    <td
      key={cell.id}
      ref={dndRef}
      {...(props.tableLayout?.columnsDraggable && !isPinned ? { cell } : {})}
      style={{
        // Pinning last so it beats the drag style, except while this column is
        // the one being dragged - see the head cell.
        ...(dndDragging
          ? { ...(isPinned ? getPinningStyles(column) : null), ...dndStyle }
          : { ...dndStyle, ...(isPinned ? getPinningStyles(column) : null) }),
      }}
      data-pinned={isPinned || undefined}
      data-last-col={isLastLeftPinned ? 'left' : isFirstRightPinned ? 'right' : undefined}
      className={cn(
        'align-middle',
        bodyCellSpacing,
        props.tableLayout?.cellBorder && 'border-e',
        props.tableLayout?.columnsResizable && column.getCanResize() && 'truncate',
        cell.column.columnDef.meta?.cellClassName,
        isPinned &&
          '[&[data-pinned=left][data-last-col=left]]:border-e! [&[data-pinned=right][data-last-col=right]]:border-s! [&[data-pinned][data-last-col]]:border-border data-pinned:bg-background/90 data-pinned:backdrop-blur-xs"',
        column.getIndex() === 0 || column.getIndex() === row.getVisibleCells().length - 1
          ? props.tableClassNames?.edgeCell
          : '',
      )}
    >
      {children}
    </td>
  );
}

function DataGridTableEmpty() {
  const { table, props } = useDataGrid();
  const totalColumns = table.getAllColumns().length;

  return (
    <tr>
      {/*
        The cell spans every column, so on a listing wider than its scroll container
        a CENTRED message is centred on the TABLE, not on what the user can see: at
        1280px the stock-inquiries grid is 2459px wide and its "No data available"
        landed ~600px past the right edge, so an empty result read as a blank band.
        That is worst exactly where it matters most - a sticky filter that matches
        nothing is otherwise indistinguishable from data loss.

        The message is start-aligned and sticky instead, so it sits under the first
        column at any table width and follows the horizontal scroll. `px-4` is the
        default cell padding, so it lines up with the first column's content rather
        than hugging the border.
      */}
      <td colSpan={totalColumns} className="p-0 text-muted-foreground">
        <div
          data-slot="data-grid-empty"
          className="sticky start-0 flex w-fit flex-col items-start gap-3 px-4 py-6 text-start"
        >
          <span>{props.emptyMessage || 'No data available'}</span>
          {props.emptyAction}
        </div>
      </td>
    </tr>
  );
}

function DataGridTableLoader() {
  const { props } = useDataGrid();

  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
      <div className="text-muted-foreground bg-card  flex items-center gap-2 px-4 py-2 font-medium leading-none text-sm border shadow-xs rounded-md">
        <svg
          className="animate-spin -ml-1 h-5 w-5 text-muted-foreground"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          ></path>
        </svg>
        {props.loadingMessage || 'Loading...'}
      </div>
    </div>
  );
}

function DataGridTableRowSelect<TData>({ row, size }: { row: Row<TData>; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <div
      className="inline-flex"
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div
        className={cn('hidden absolute top-0 bottom-0 start-0 w-[2px] bg-primary', row.getIsSelected() && 'block')}
      ></div>
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
        size={size ?? 'sm'}
        className="align-[inherit]"
      />
    </div>
  );
}

function DataGridTableRowSelectAll({ size }: { size?: 'sm' | 'md' | 'lg' }) {
  const { table, recordCount, isLoading } = useDataGrid();

  return (
    <Checkbox
      checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')}
      disabled={isLoading || recordCount === 0}
      onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
      aria-label="Select all"
      size={size}
      className="align-[inherit]"
    />
  );
}

/**
 * A drag, with a column GROUP's members kept contiguous.
 *
 * TanStack draws a group header once per RUN of its members, so a foreign column dropped
 * into the middle of a group renders that header twice - and the split order is then saved
 * as the user's own preference. Two rules keep the group whole: a column from outside lands
 * at the group's nearest EDGE, and a member cannot be dragged out of its group (the group
 * is one choice, the same reason a saved view names the group and not its columns).
 *
 * `groups` is empty on every flat listing, where this is a plain `arrayMove` as before.
 */
export function moveColumnKeepingGroups(
  order: string[],
  activeId: string,
  overId: string,
  groups: string[][],
): string[] {
  const oldIndex = order.indexOf(activeId);
  const overIndex = order.indexOf(overId);
  if (oldIndex === -1 || overIndex === -1 || activeId === overId) return order;

  const groupOf = (id: string) => groups.find((members) => members.includes(id));
  const activeGroup = groupOf(activeId);
  const overGroup = groupOf(overId);

  if (activeGroup) {
    // Inside its own group it reorders; anywhere else the drop is a no-op.
    return overGroup === activeGroup ? arrayMove(order, oldIndex, overIndex) : order;
  }

  if (overGroup) {
    const without = order.filter((id) => id !== activeId);
    const indexes = overGroup.map((id) => without.indexOf(id)).filter((index) => index >= 0);
    if (!indexes.length) return arrayMove(order, oldIndex, overIndex);
    const first = Math.min(...indexes);
    const last = Math.max(...indexes);
    const dropped = without.indexOf(overId);
    const insertAt = dropped - first <= last - dropped ? first : last + 1;
    return [...without.slice(0, insertAt), activeId, ...without.slice(insertAt)];
  }

  return arrayMove(order, oldIndex, overIndex);
}

/**
 * The grid's own horizontal scroll container.
 *
 * Without one, a `table-fixed w-full` grid squeezed its columns into whatever
 * width it was given - Stock showed one column at 375, Categories crushed six -
 * or, where it did overflow, pushed the whole PAGE sideways. The scrollbar is
 * the only affordance a mouse user gets, so a right-edge fade marks that there
 * is more to see and disappears once the end is reached.
 *
 * `min-w-0` on both divs is what makes the scroller scroll at all. `CardTable`
 * is a `grid`, `Card` is a `flex` column, and an item of either has
 * `min-width: auto` by default, which resolves to its MIN-CONTENT width. The
 * table asks for `min-width: 2178px`, so the item refused to be narrower than
 * that and the track blew out with it: measured on Orders at 1280, the scroller
 * reported clientWidth 2178 === scrollWidth 2178, i.e. "nothing to scroll",
 * inside a 950px card. `min-width: 0` lets the item take the width it is given
 * and the overflow lands where it belongs.
 */
function DataGridScroller({ children }: { children: ReactNode }) {
  const { ref, isFading } = useHorizontalOverflow<HTMLDivElement>();

  return (
    <div className="relative min-w-0">
      <div
        ref={ref}
        data-slot="data-grid-scroller"
        data-fade={isFading}
        className="min-w-0 overflow-x-auto overscroll-x-contain"
      >
        {children}
      </div>
      {isFading && (
        <div
          aria-hidden="true"
          data-slot="data-grid-fade"
          className="pointer-events-none absolute inset-y-0 end-0 w-8 bg-gradient-to-l from-background to-transparent"
        />
      )}
    </div>
  );
}

function DataGridTable<TData>() {
  const { table, isLoading, props } = useDataGrid();
  const pagination = table.getState().pagination;
  // A phone does NOT pin the identifier column. S1 pinned it under `sm` so the
  // row stayed labelled while the grid scrolled sideways; the user tried it and
  // found a column that refuses to move with the rest weirder than losing sight
  // of the name (ruling 2026-08-30). The whole row scrolls as one. Explicit
  // pinning still works for the lists that ask for it.

  if (props.tableLayout?.columnsDraggable) {
    const handleDragEnd = (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over) return;

      const columnOrderState = table.getState().columnOrder as string[] | undefined;
      const leafIds = table.getAllLeafColumns().map((c) => c.id);
      const rawOrder =
        Array.isArray(columnOrderState) && columnOrderState.length > 0 ? columnOrderState : leafIds;
      const effectiveOrder = mergeColumnOrderWithLeafColumns(rawOrder, leafIds);
      if (!Array.isArray(effectiveOrder) || effectiveOrder.length === 0) return;

      const groups = table
        .getAllColumns()
        .filter((column) => column.columns?.length)
        .map((column) => column.getLeafColumns().map((leaf) => leaf.id));

      const next = moveColumnKeepingGroups(
        effectiveOrder,
        String(active.id),
        String(over.id),
        groups,
      );
      if (next === effectiveOrder) return;
      table.setColumnOrder(next);
    };

    return (
      <DataGridScroller>
        <DataGridTableDnd<TData> handleDragEnd={handleDragEnd} />
      </DataGridScroller>
    );
  }

  return (
    <DataGridScroller>
      <DataGridTableBase>
        <DataGridTableHead>
          {table.getHeaderGroups().map((headerGroup: HeaderGroup<TData>, index) => {
            const rowCount = table.getHeaderGroups().length;
            return (
              <DataGridTableHeadRow headerGroup={headerGroup} key={index}>
                {headerGroup.headers
                  .filter((header) => !skipMergedLeafHeader(header, rowCount))
                  .map((header, index) => {
                    const { column } = header;

                    return (
                      <DataGridTableHeadRowCell
                        header={header}
                        key={index}
                        rowSpan={headerRowSpan(header, rowCount)}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {props.tableLayout?.columnsResizable && column.getCanResize() && (
                          <DataGridTableHeadRowCellResize header={header} />
                        )}
                      </DataGridTableHeadRowCell>
                    );
                  })}
              </DataGridTableHeadRow>
            );
          })}
        </DataGridTableHead>

        {(props.tableLayout?.stripped || !props.tableLayout?.rowBorder) && <DataGridTableRowSpacer />}

        <DataGridTableBody>
          {props.loadingMode === 'skeleton' && isLoading && pagination?.pageSize ? (
            Array.from({ length: pagination.pageSize }).map((_, rowIndex) => (
              <DataGridTableBodyRowSkeleton key={rowIndex}>
                {/* LEAF columns: the flat list includes a group PARENT, which is not a
                    cell, so every skeleton row came out one td wider than the table. */}
                {table.getVisibleLeafColumns().map((column, colIndex) => {
                  return (
                    <DataGridTableBodyRowSkeletonCell column={column} key={colIndex}>
                      {column.columnDef.meta?.skeleton}
                    </DataGridTableBodyRowSkeletonCell>
                  );
                })}
              </DataGridTableBodyRowSkeleton>
            ))
          ) : table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row: Row<TData>, index) => {
              // Optional grouping. `renderGroupHeader` returns a label when this
              // row starts a new group, or null otherwise - so a grid that does
              // not opt in behaves exactly as before.
              //
              // The caller decides what a group is; the grid only draws the
              // divider. Group members must already be contiguous (order them
              // server-side), or a group will appear more than once.
              const groupHeader = props.renderGroupHeader?.(
                row.original as TData,
                index === 0 ? null : (table.getRowModel().rows[index - 1].original as TData),
              );
              return (
                <Fragment key={row.id}>
                  {groupHeader != null && (
                    <tr
                      className="bg-muted/50"
                      data-testid="data-grid-group-header"
                      data-group-label={typeof groupHeader === 'string' ? groupHeader : undefined}
                    >
                      <td
                        colSpan={row.getVisibleCells().length}
                        className="px-4 py-2 text-xs font-medium text-muted-foreground"
                      >
                        {groupHeader}
                      </td>
                    </tr>
                  )}
                  <DataGridTableBodyRow row={row} key={index}>
                    {row.getVisibleCells().map((cell: Cell<TData, unknown>, colIndex) => {
                      return (
                        <DataGridTableBodyRowCell cell={cell} key={colIndex}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </DataGridTableBodyRowCell>
                      );
                    })}
                  </DataGridTableBodyRow>
                  {row.getIsExpanded() && <DataGridTableBodyRowExpandded row={row} />}
                </Fragment>
              );
            })
          ) : (
            <DataGridTableEmpty />
          )}
        </DataGridTableBody>

        {table.getVisibleFlatColumns().some((column) => Boolean(column.columnDef.footer)) && (
          <DataGridTableFoot>
            {footerGroupsWithContent(table).map((footerGroup) => (
              <tr key={footerGroup.id}>
                {footerGroup.headers.map((header) => (
                  <DataGridTableFootRowCell key={header.id} header={header}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.footer, header.getContext())}
                  </DataGridTableFootRowCell>
                ))}
              </tr>
            ))}
          </DataGridTableFoot>
        )}
      </DataGridTableBase>
    </DataGridScroller>
  );
}

export {
  footerGroupsWithContent,
  DataGridScroller,
  headerRowSpan,
  skipMergedLeafHeader,
  DataGridTable,
  DataGridTableBase,
  DataGridTableBody,
  DataGridTableBodyRow,
  DataGridTableBodyRowCell,
  DataGridTableBodyRowExpandded,
  DataGridTableBodyRowSkeleton,
  DataGridTableBodyRowSkeletonCell,
  DataGridTableEmpty,
  DataGridTableFoot,
  DataGridTableFootRowCell,
  DataGridTableHead,
  DataGridTableHeadRow,
  DataGridTableHeadRowCell,
  DataGridTableHeadRowCellResize,
  DataGridTableLoader,
  DataGridTableRowSelect,
  DataGridTableRowSelectAll,
  DataGridTableRowSpacer,
};
