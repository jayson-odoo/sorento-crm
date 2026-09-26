'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type { DragEndEvent } from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { Check, ChevronDown, ChevronRight, CornerDownRight, GripVertical, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DataGridTableDndRowHandle,
  DataGridTableDndRows,
} from '@/components/ui/data-grid-table-dnd-rows';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { formatDateInMalaysia } from '@/lib/helpers';
import type {
  ProjectSalesOrderFinding,
  ProjectSalesOrderLine,
} from '../../_shared/types/projectSalesOrder.types';
import { buildFlagItems, needsAttention, type FlagItem } from '../../_shared/lib/findings';
import { SalesOrderFlagCell } from './SalesOrderFlagCell';
import { formatMoney, formatQty, formatUnitPrice, isZeroMoney } from './SalesOrderMoney';
import {
  SalesOrderLinesEditor,
  type SalesOrderLinesEditing,
} from './SalesOrderLinesEditor';

export interface ExplodedLineGroup {
  key: string;
  /** The PO line these lines were exploded from, when the backend told us. */
  sourcePoLineNo: number | null;
  parent: ProjectSalesOrderLine;
  companions: ProjectSalesOrderLine[];
}

/**
 * Reassembles the set explosion so a set reads as a set.
 *
 * 52 PO lines become 99 sales order lines because the PO speaks in SETS and the sales order
 * speaks in components: one priced parent plus zero-priced companions. The contract carries
 * `source_po_line_no` and the prices but no explicit parent pointer, so the parent is taken
 * to be the first priced line of each `source_po_line_no` group and everything else in that
 * group hangs under it. Lines with no source PO line stand alone rather than being lumped
 * into one fake set.
 */
export function groupExplodedLines(lines: ProjectSalesOrderLine[]): ExplodedLineGroup[] {
  const ordered = [...lines].sort((a, b) => a.line_no - b.line_no);
  const groups: ExplodedLineGroup[] = [];
  const bySource = new Map<string, ExplodedLineGroup>();

  ordered.forEach((line) => {
    const source = line.source_po_line_no;
    if (source === null || source === undefined) {
      groups.push({ key: `line:${line.id}`, sourcePoLineNo: null, parent: line, companions: [] });
      return;
    }
    const key = `po:${source}`;
    const existing = bySource.get(key);
    if (!existing) {
      const group: ExplodedLineGroup = {
        key,
        sourcePoLineNo: source,
        parent: line,
        companions: [],
      };
      bySource.set(key, group);
      groups.push(group);
      return;
    }
    // A priced line arriving after a zero-priced one takes the parent slot; the displaced
    // line becomes a companion in its original position.
    if (isZeroMoney(existing.parent.unit_price) && !isZeroMoney(line.unit_price)) {
      existing.companions.unshift(existing.parent);
      existing.parent = line;
    } else {
      existing.companions.push(line);
    }
  });

  return groups;
}

interface DisplayRow {
  key: string;
  /** Null on a finding-only row: a finding naming no line of this order (S7-3). */
  line: ProjectSalesOrderLine | null;
  items: FlagItem[];
  groupKey: string;
  isCompanion: boolean;
  companionCount: number;
  sourcePoLineNo: number | null;
}

/**
 * The section's own heading, shared by the read and the edit.
 *
 * Declared once and rendered by both branches below, so the two views cannot drift apart: the
 * read view is what teaches somebody where the lines section is, and an edit that redrew its
 * heading, its count or its "Show all lines" control would make every edit start with
 * re-finding them.
 */
function LinesSectionHeader({
  lineCount,
  explodedSets,
  focused,
  onClearFocus,
  leading,
  trailing,
}: {
  lineCount: number;
  explodedSets: number;
  focused: boolean;
  onClearFocus?: () => void;
  /** Stands where the count stands: the Need attention / All lines filter, when it applies. */
  leading?: React.ReactNode;
  /** An extra header action beside "Show all lines" - the reorder toggle, for instance. */
  trailing?: React.ReactNode;
}) {
  return (
    <CardHeader className="block space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          {leading ?? (
          <p className="text-xs text-muted-foreground">
            {`${lineCount.toLocaleString()} line${lineCount === 1 ? '' : 's'}${
              explodedSets > 0
                ? `, ${explodedSets} set${explodedSets === 1 ? '' : 's'} exploded`
                : ''
            }`}
          </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {focused && (
            <Button type="button" variant="outline" size="sm" onClick={onClearFocus}>
              <X className="size-4" aria-hidden />
              Show all lines
            </Button>
          )}
          {trailing}
        </div>
      </div>
    </CardHeader>
  );
}

/** What a row is about: its product, or for a finding-only row the code the finding names. */
function rowSubject(row: DisplayRow): string {
  if (row.line) return row.line.product_code || 'Not resolved';
  const detail = row.items[0]?.members[0]?.finding.detail_json ?? {};
  const code = detail.product_code ?? detail.customer_code_raw;
  return typeof code === 'string' && code ? code : '-';
}

function Dash() {
  return <span className="text-muted-foreground">-</span>;
}

export interface SalesOrderLinesReorder {
  /** Only a draft's lines may move; the caller decides from the order's own status. */
  enabled: boolean;
  onReorder: (lineIds: string[]) => void;
}

export function SalesOrderLinesTable({
  lines,
  findings = [],
  flagItems,
  canDismiss = null,
  onDismiss,
  defaultNeedsAttention = false,
  focusLineId = null,
  onClearFocus,
  editing,
  reference,
  reorder,
}: {
  lines: ProjectSalesOrderLine[];
  findings?: ProjectSalesOrderFinding[];
  /**
   * Every Flag item the page shows, the order's own findings and the schedule's (S7-3).
   * Absent, it is built from `findings` alone.
   */
  flagItems?: FlagItem[];
  /** Null while nothing may be dismissed from this table. */
  canDismiss?: ((item: FlagItem) => boolean) | null;
  onDismiss?: (item: FlagItem) => void;
  /** Open on "Need attention" while anything needs it (owner lesson (c)). */
  defaultNeedsAttention?: boolean;
  focusLineId?: string | null;
  onClearFocus?: () => void;
  /**
   * Set while the screen's edit session is open. The section keeps its Card, its heading and
   * its counts; only the table inside it becomes a spreadsheet. See `SalesOrderLinesEditor`
   * for why an editor cannot be the DataGrid.
   */
  editing?: SalesOrderLinesEditing | null;
  /** The order's reference, for the editor's row labels. */
  reference?: string;
  /**
   * A drag handle per row, saved immediately on drop. Offered as a FLAT list ordered by
   * `line_no`, not the grouped read below: a set's components are clustered by their shared
   * `source_po_line_no`, so a row dropped mid-table would visually snap back to its own
   * cluster no matter where it landed - the flat view is what makes drag position and
   * display position the same thing. The existing "From PO line" column stays as the row's
   * context, standing in for a chip.
   */
  reorder?: SalesOrderLinesReorder;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({});
  const containerRef = React.useRef<HTMLDivElement>(null);
  // Opt-in: the grouped read stays the default (it is what a finding's "Show line N" narrows,
  // and what a set collapses), and reordering swaps to the flat view only while pressed on.
  const [reordering, setReordering] = React.useState(false);
  const reorderAvailable = Boolean(reorder?.enabled);
  React.useEffect(() => {
    if (!reorderAvailable) setReordering(false);
  }, [reorderAvailable]);

  const groups = React.useMemo(() => groupExplodedLines(lines), [lines]);

  const items = React.useMemo(
    () => flagItems ?? buildFlagItems(findings, []),
    [findings, flagItems],
  );

  /** A line's items, and the items naming no line on this order, each a row of its own. */
  const { itemsByLine, standaloneRows } = React.useMemo(() => {
    const lineIds = new Set(lines.map((line) => line.id));
    const byLine = new Map<string, FlagItem[]>();
    const standalone: DisplayRow[] = [];
    items.forEach((item) => {
      if (item.lineId && lineIds.has(item.lineId)) {
        byLine.set(item.lineId, [...(byLine.get(item.lineId) ?? []), item]);
        return;
      }
      standalone.push({
        key: `finding:${item.key}`,
        line: null,
        items: [item],
        groupKey: `finding:${item.key}`,
        isCompanion: false,
        companionCount: 0,
        sourcePoLineNo: null,
      });
    });
    return { itemsByLine: byLine, standaloneRows: standalone };
  }, [items, lines]);

  const attentionRows = React.useMemo<DisplayRow[]>(
    () => [
      ...standaloneRows.filter((row) => row.items.some(needsAttention)),
      ...[...lines]
        .sort((a, b) => a.line_no - b.line_no)
        .map((line) => ({
          key: line.id,
          line,
          items: itemsByLine.get(line.id) ?? [],
          groupKey: line.id,
          isCompanion: false,
          companionCount: 0,
          sourcePoLineNo: line.source_po_line_no ?? null,
        }))
        .filter((row) => row.items.some(needsAttention)),
    ],
    [itemsByLine, lines, standaloneRows],
  );
  const [attentionOnly, setAttentionOnly] = React.useState(defaultNeedsAttention);
  // Nothing left to act on is not a filter worth keeping: the table falls back to every line.
  const showingAttention = attentionOnly && attentionRows.length > 0;
  React.useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [showingAttention]);

  const focusedGroupKey = React.useMemo(() => {
    if (!focusLineId) return null;
    const group = groups.find(
      (entry) =>
        entry.parent.id === focusLineId ||
        entry.companions.some((companion) => companion.id === focusLineId),
    );
    return group?.key ?? null;
  }, [focusLineId, groups]);

  // jsdom implements no scrollIntoView, hence the optional call.
  React.useEffect(() => {
    if (focusedGroupKey) containerRef.current?.scrollIntoView?.({ block: 'start' });
  }, [focusedGroupKey]);

  const visibleGroups = React.useMemo(
    () => (focusedGroupKey ? groups.filter((group) => group.key === focusedGroupKey) : groups),
    [focusedGroupKey, groups],
  );

  const rows = React.useMemo<DisplayRow[]>(() => {
    if (showingAttention && !focusedGroupKey) return attentionRows;
    const out: DisplayRow[] = focusedGroupKey ? [] : [...standaloneRows];
    visibleGroups.forEach((group) => {
      out.push({
        key: group.parent.id,
        line: group.parent,
        items: itemsByLine.get(group.parent.id) ?? [],
        groupKey: group.key,
        isCompanion: false,
        companionCount: group.companions.length,
        sourcePoLineNo: group.sourcePoLineNo,
      });
      if (collapsed[group.key]) return;
      group.companions.forEach((companion) => {
        out.push({
          key: companion.id,
          line: companion,
          items: itemsByLine.get(companion.id) ?? [],
          groupKey: group.key,
          isCompanion: true,
          companionCount: group.companions.length,
          sourcePoLineNo: group.sourcePoLineNo,
        });
      });
    });
    return out;
  }, [
    attentionRows,
    collapsed,
    focusedGroupKey,
    itemsByLine,
    showingAttention,
    standaloneRows,
    visibleGroups,
  ]);

  // Read through a ref so the columns keep their identity: TanStack renders a cell function
  // as a component, so a new `canDismiss` each parent render would remount every Flag cell
  // and close an open popover under the reader.
  const dismissRef = React.useRef({ canDismiss, onDismiss });
  dismissRef.current = { canDismiss, onDismiss };

  const columns = React.useMemo<ColumnDef<DisplayRow>[]>(
    () => [
      {
        id: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => (
          <span
            className={`tabular-nums ${row.original.isCompanion || !row.original.line ? 'text-muted-foreground' : ''}`}
          >
            {row.original.line?.line_no ?? '-'}
          </span>
        ),
        size: 70,
        minSize: 56,
        meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        id: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const code = rowSubject(row.original);
          return (
            <div className={`flex min-w-0 items-center gap-1 ${row.original.isCompanion ? 'pl-4' : ''}`}>
              {row.original.isCompanion && (
                <CornerDownRight
                  className="size-3.5 shrink-0 text-muted-foreground"
                  aria-label="Companion of the line above"
                />
              )}
              <span
                className={`truncate ${row.original.isCompanion ? 'text-muted-foreground' : 'font-medium'}`}
                title={code}
              >
                {code}
              </span>
            </div>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        // Beside the product rather than at the far end, so it is on the first screen at
        // 1280 and the first swipe at 375 (S7-3).
        id: 'flag',
        header: ({ column }) => <DataGridColumnHeader title="Flag" column={column} />,
        cell: ({ row }) => (
          <SalesOrderFlagCell
            items={row.original.items}
            label={row.original.line ? `line ${row.original.line.line_no}` : rowSubject(row.original)}
            canDismiss={dismissRef.current.canDismiss}
            onDismiss={(item) => dismissRef.current.onDismiss?.(item)}
          />
        ),
        size: 190,
        minSize: 120,
        meta: { headerTitle: 'Flag', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          // A finding-only row has no line to describe; the finding's own sentence stands in.
          const text = row.original.line
            ? row.original.line.description || '-'
            : row.original.items[0]?.members[0]?.finding.detail || '-';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 320,
        minSize: 160,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) =>
          row.original.line ? (
            <span className="block truncate tabular-nums" title={row.original.line.qty}>
              {formatQty(row.original.line.qty)}
            </span>
          ) : (
            <Dash />
          ),
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'uom',
        header: ({ column }) => <DataGridColumnHeader title="UOM" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground">
            {row.original.line?.uom || '-'}
          </span>
        ),
        size: 80,
        minSize: 60,
        meta: { headerTitle: 'UOM', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'unit_price',
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => {
          const line = row.original.line;
          if (!line) return <Dash />;
          return (
            <span
              className={`block truncate tabular-nums ${
                isZeroMoney(line.unit_price) ? 'text-muted-foreground' : ''
              }`}
              title={line.unit_price}
            >
              {formatUnitPrice(line.unit_price)}
            </span>
          );
        },
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Unit price', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'amount',
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        cell: ({ row }) => {
          if (!row.original.line) return <Dash />;
          const value = formatMoney(row.original.line.amount);
          return (
            <span className="block truncate tabular-nums" title={value}>
              {value}
            </span>
          );
        },
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Amount', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery" column={column} />,
        cell: ({ row }) => {
          const line = row.original.line;
          if (!line) return <Dash />;
          return line.delivery_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(line.delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">No date</span>
          );
        },
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Delivery', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'phase_label',
        header: ({ column }) => <DataGridColumnHeader title="Area" column={column} />,
        cell: ({ row }) => {
          if (!row.original.line) return <Dash />;
          const text = row.original.line.phase_label || 'Unlabeled area';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        meta: { headerTitle: 'Area', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'source_po_line_no',
        header: ({ column }) => <DataGridColumnHeader title="From PO line" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground tabular-nums">
            {row.original.sourcePoLineNo ?? '-'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'From PO line', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'stock_location',
        header: ({ column }) => <DataGridColumnHeader title="Stock location" column={column} />,
        cell: ({ row }) => {
          const text = row.original.line?.stock_location || '-';
          return (
            <span className="block truncate text-muted-foreground" title={text}>
              {text}
            </span>
          );
        },
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Stock location', skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(rows.length / pagination.pageSize) || 0,
    getRowId: (row) => row.key,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  // Reorder mode's own flat rows, in the order the draft currently holds them - not grouped,
  // and not paged: "drop anywhere in the table" means every line has to be on screen and a
  // drop position has to mean what it looks like.
  const flatRows = React.useMemo<DisplayRow[]>(
    () =>
      [...lines]
        .sort((a, b) => a.line_no - b.line_no)
        .map((line) => ({
          key: line.id,
          line,
          items: itemsByLine.get(line.id) ?? [],
          groupKey: line.id,
          isCompanion: false,
          companionCount: 0,
          sourcePoLineNo: line.source_po_line_no ?? null,
        })),
    [itemsByLine, lines],
  );

  const dragHandleColumn = React.useMemo<ColumnDef<DisplayRow>>(
    () => ({
      id: 'drag_handle',
      header: () => <span className="sr-only">Reorder</span>,
      cell: ({ row }) => <DataGridTableDndRowHandle rowId={row.original.key} />,
      size: 44,
      minSize: 44,
      meta: { headerTitle: 'Reorder', skeleton: <Skeleton className="size-7" /> },
    }),
    [],
  );
  const dragColumns = React.useMemo(
    () => [dragHandleColumn, ...columns],
    [columns, dragHandleColumn],
  );

  const dragTable = useReactTable({
    columns: dragColumns,
    data: flatRows,
    getRowId: (row) => row.key,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  const handleRowDragEnd = React.useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || !reorder || active.id === over.id) return;
      const ids = flatRows.map((row) => row.key);
      const oldIndex = ids.indexOf(String(active.id));
      const newIndex = ids.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return;
      reorder.onReorder(arrayMove(ids, oldIndex, newIndex));
    },
    [flatRows, reorder],
  );

  const explodedSets = groups.filter((group) => group.companions.length > 0).length;

  /**
   * A set gets a header row above its priced parent; a line that exploded into nothing does
   * not, or every row on a 99 line order would carry a divider.
   */
  const renderSetHeader = (row: DisplayRow, previous: DisplayRow | null): React.ReactNode => {
    if (row.isCompanion || row.companionCount === 0) return null;
    if (previous && previous.groupKey === row.groupKey) return null;
    const isCollapsed = Boolean(collapsed[row.groupKey]);
    return (
      <button
        type="button"
        className="flex items-center gap-1.5 text-left"
        aria-expanded={!isCollapsed}
        onClick={() =>
          setCollapsed((current) => ({ ...current, [row.groupKey]: !current[row.groupKey] }))
        }
      >
        {isCollapsed ? (
          <ChevronRight className="size-3.5" aria-hidden />
        ) : (
          <ChevronDown className="size-3.5" aria-hidden />
        )}
        {`Set from PO line ${row.sourcePoLineNo ?? '-'}: ${row.companionCount + 1} components`}
      </button>
    );
  };

  /**
   * The edit, in the same section as the read: same Card, same heading, same counts, and the
   * columns in the same order (`SalesOrderLinesEditor` declares them, and a test asserts the
   * two header lists agree). Only the table inside becomes a spreadsheet.
   *
   * Returned before the DataGrid rather than nested inside it, because the grid holds skeleton
   * rows until the column-preferences query settles and would flash them over an editor that
   * has nothing to fetch.
   */
  if (editing) {
    return (
      <div ref={containerRef}>
        <Card>
          <LinesSectionHeader
            lineCount={lines.length}
            explodedSets={explodedSets}
            focused={Boolean(focusedGroupKey)}
            onClearFocus={onClearFocus}
          />
          {/* `min-w-0` on BOTH boxes, and it is load-bearing rather than tidiness: the editor
              scrolls a wide line table inside its own gutter, and a flex/grid ancestor that
              forgets it lets the table's intrinsic width (about 1,700px) become the page's, so
              the whole screen scrolls sideways at 375px. Measured: 1709px against a 375px
              viewport before this was added, 375px after. */}
          <CardTable className="min-w-0">
            <div className="min-w-0 px-4 pb-4">
              <SalesOrderLinesEditor
                lines={lines}
                findings={findings}
                flagItems={items}
                editing={editing}
                reference={reference}
              />
            </div>
          </CardTable>
        </Card>
      </div>
    );
  }

  // Owner lesson (c): "Need attention" first, "All lines" beside it, each with its count.
  const attentionToggle = (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={showingAttention ? 'attention' : 'all'}
      onValueChange={(next) => next && setAttentionOnly(next === 'attention')}
    >
      <ToggleGroupItem value="attention" className="px-3">
        {`Need attention (${attentionRows.length})`}
      </ToggleGroupItem>
      <ToggleGroupItem value="all" className="px-3">
        {`All lines (${lines.length})`}
      </ToggleGroupItem>
    </ToggleGroup>
  );

  const reorderToggle = reorderAvailable ? (
    <Button
      type="button"
      variant={reordering ? 'primary' : 'outline'}
      size="sm"
      onClick={() => setReordering((current) => !current)}
    >
      {reordering ? (
        <>
          <Check className="size-4" aria-hidden />
          Done reordering
        </>
      ) : (
        <>
          <GripVertical className="size-4" aria-hidden />
          Reorder lines
        </>
      )}
    </Button>
  ) : null;

  /**
   * Reorder mode: the same section, but flat and draggable, pressed on from the toggle
   * above. Not the grouped read below - see `reorder`'s own doc comment for why a set's
   * cluster and a free drag cannot share a view - and not paginated, because a drop target
   * has to be reachable on screen.
   */
  if (reordering) {
    return (
      <div ref={containerRef}>
        <DataGrid
          table={dragTable}
          recordCount={flatRows.length}
          isLoading={false}
          listingKey="projects.projects.view::project-sales-order-lines"
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <Card>
            <LinesSectionHeader
              lineCount={lines.length}
              explodedSets={explodedSets}
              focused={false}
              trailing={reorderToggle}
            />

            <CardTable>
              {lines.length === 0 ? (
                <div className="px-6 py-10 text-center">
                  <h3 className="text-sm font-semibold">This draft has no lines</h3>
                  <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                    Rebuild it from the purchase order and its delivery schedule.
                  </p>
                </div>
              ) : (
                <ScrollArea>
                  <DataGridTableDndRows
                    handleDragEnd={handleRowDragEnd}
                    dataIds={flatRows.map((row) => row.key)}
                  />
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              )}
            </CardTable>
          </Card>
        </DataGrid>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="min-w-0">
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={false}
        listingKey="projects.projects.view::project-sales-order-lines"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        renderGroupHeader={renderSetHeader}
      >
        <Card>
          <LinesSectionHeader
            lineCount={lines.length}
            explodedSets={explodedSets}
            focused={Boolean(focusedGroupKey)}
            onClearFocus={onClearFocus}
            leading={attentionRows.length > 0 ? attentionToggle : undefined}
            trailing={reorderToggle}
          />

          <CardTable className="min-w-0">
            {lines.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">This draft has no lines</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Rebuild it from the purchase order and its delivery schedule.
                </p>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          {rows.length > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>
    </div>
  );
}
