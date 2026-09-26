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
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridScroller, DataGridTable } from '@/components/ui/data-grid-table';
import {
  DataGridTableDndRowHandle,
  DataGridTableDndRows,
} from '@/components/ui/data-grid-table-dnd-rows';
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
 * Reassembles the set explosion so a set reads as a set. The regroup dialog's, now: the lines
 * table draws every line as one plain row (owner hand test, PR #1264 note 1).
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
  /** The line number a zero-priced set part is priced on, or null. */
  partOf: number | null;
}

/**
 * The section's own heading, shared by the read and the edit.
 *
 * Declared once and rendered by both branches below, so the two views cannot drift apart: the
 * read view is what teaches somebody where the lines section is. One line: the Need attention
 * / All lines filter when anything needs attention, otherwise the line count.
 */
function LinesSectionHeader({
  lineCount,
  leading,
}: {
  lineCount: number;
  /** Stands where the count stands: the Need attention / All lines filter, when it applies. */
  leading?: React.ReactNode;
}) {
  return (
    <CardHeader className="block">
      <div className="min-w-0">
        {leading ?? (
          <p className="text-xs text-muted-foreground">
            {`${lineCount.toLocaleString()} line${lineCount === 1 ? '' : 's'}`}
          </p>
        )}
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
  /**
   * Set while the screen's edit session is open. The section keeps its Card, its heading and
   * its counts; only the table inside it becomes a spreadsheet. See `SalesOrderLinesEditor`
   * for why an editor cannot be the DataGrid.
   */
  editing?: SalesOrderLinesEditing | null;
  /** The order's reference, for the editor's row labels. */
  reference?: string;
  /**
   * A drag handle on every row, and a drop saves at once: no mode to press into first
   * (owner hand test, PR #1264 note 2). The rows are always the flat `line_no` order, so a
   * drop position and a display position are the same thing.
   */
  reorder?: SalesOrderLinesReorder;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const reorderable = Boolean(reorder?.enabled);

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
      standalone.push({ key: `finding:${item.key}`, line: null, items: [item], partOf: null });
    });
    return { itemsByLine: byLine, standaloneRows: standalone };
  }, [items, lines]);

  /**
   * Every line, one plain row each, in `line_no` order (owner hand test, PR #1264 note 1). A
   * set is no longer a heading row over an indented tree: a zero-priced part says, in its own
   * price cell, which line it is priced on - the server states that pairing (`parent_line_id`)
   * rather than this table guessing it.
   */
  const lineRows = React.useMemo<DisplayRow[]>(() => {
    const numberOf = new Map(lines.map((line) => [line.id, line.line_no]));
    return [...lines]
      .sort((a, b) => a.line_no - b.line_no)
      .map((line) => ({
        key: line.id,
        line,
        items: itemsByLine.get(line.id) ?? [],
        partOf:
          line.is_companion && line.parent_line_id
            ? (numberOf.get(line.parent_line_id) ?? null)
            : null,
      }));
  }, [itemsByLine, lines]);

  const attentionRows = React.useMemo<DisplayRow[]>(
    () =>
      [...standaloneRows, ...lineRows].filter((row) => row.items.some(needsAttention)),
    [lineRows, standaloneRows],
  );
  const [attentionOnly, setAttentionOnly] = React.useState(defaultNeedsAttention);
  // Nothing left to act on is not a filter worth keeping: the table falls back to every line.
  const showingAttention = attentionOnly && attentionRows.length > 0;
  React.useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [showingAttention]);

  const rows = React.useMemo<DisplayRow[]>(
    () => (showingAttention ? attentionRows : [...standaloneRows, ...lineRows]),
    [attentionRows, lineRows, showingAttention, standaloneRows],
  );

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
          <span className={`tabular-nums ${row.original.line ? '' : 'text-muted-foreground'}`}>
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
            <span className="block truncate font-medium" title={code}>
              {code}
            </span>
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
          if (row.original.partOf !== null) {
            const text = `Part of #${row.original.partOf}`;
            return (
              <span className="block truncate text-muted-foreground" title={text}>
                {text}
              </span>
            );
          }
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
    ],
    [],
  );

  // The handle leads the row whenever the order may be reordered: no toggle to press first.
  const tableColumns = React.useMemo<ColumnDef<DisplayRow>[]>(
    () =>
      reorderable
        ? [
            {
              id: 'drag_handle',
              header: () => <span className="sr-only">Reorder</span>,
              // A finding-only row is not a line and has no place in the order to move.
              cell: ({ row }) =>
                row.original.line ? <DataGridTableDndRowHandle rowId={row.original.key} /> : null,
              size: 44,
              minSize: 44,
              enableResizing: false,
              meta: { headerTitle: 'Reorder', skeleton: <Skeleton className="size-7" /> },
            },
            ...columns,
          ]
        : columns,
    [columns, reorderable],
  );

  const table = useReactTable({
    columns: tableColumns,
    data: rows,
    pageCount: Math.ceil(rows.length / pagination.pageSize) || 0,
    getRowId: (row) => row.key,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  /**
   * A drop saves straight away (PR #1264 note 2). The move is made on the WHOLE order's line
   * ids, not the rows on screen, so a drop inside the Need attention filter or on a later page
   * still sends every line, in its new sequence.
   */
  const handleRowDragEnd = React.useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || !reorder || active.id === over.id) return;
      const ids = lineRows.map((row) => row.key);
      const oldIndex = ids.indexOf(String(active.id));
      const newIndex = ids.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return;
      reorder.onReorder(arrayMove(ids, oldIndex, newIndex));
    },
    [lineRows, reorder],
  );

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
      <div>
        <Card>
          <LinesSectionHeader lineCount={lines.length} />
          {/* `min-w-0` on BOTH boxes, and it is load-bearing rather than tidiness: the editor
              scrolls a wide line table inside its own gutter, and a flex/grid ancestor that
              forgets it lets the table's intrinsic width become the page's, so the whole
              screen scrolls sideways at 375px. */}
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
        {`All lines (${lines.length + standaloneRows.length})`}
      </ToggleGroupItem>
    </ToggleGroup>
  );

  return (
    <div className="min-w-0">
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={false}
        listingKey="projects.projects.view::project-sales-order-lines"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <LinesSectionHeader
            lineCount={lines.length}
            leading={attentionRows.length > 0 ? attentionToggle : undefined}
          />

          <CardTable className="min-w-0">
            {rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold">This draft has no lines</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Rebuild it from the purchase order and its delivery schedule.
                </p>
              </div>
            ) : reorderable ? (
              // The grid's own scroller, not a Radix ScrollArea: that wrapper shrink-fits the
              // table and kills the sideways scroll (S1-05, the S6 hand test's item 1).
              <DataGridScroller>
                <DataGridTableDndRows
                  handleDragEnd={handleRowDragEnd}
                  dataIds={table.getRowModel().rows.map((row) => row.id)}
                />
              </DataGridScroller>
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
