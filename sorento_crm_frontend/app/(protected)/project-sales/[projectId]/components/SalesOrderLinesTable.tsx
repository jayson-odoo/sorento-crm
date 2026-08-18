'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, CornerDownRight, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import type {
  ProjectSalesOrderFinding,
  ProjectSalesOrderLine,
} from '../../_shared/types/projectSalesOrder.types';
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
  line: ProjectSalesOrderLine;
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
}: {
  lineCount: number;
  explodedSets: number;
  focused: boolean;
  onClearFocus?: () => void;
}) {
  return (
    <CardHeader className="block space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <p className="text-sm font-medium">Lines</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {`${lineCount.toLocaleString()} line${lineCount === 1 ? '' : 's'}${
              explodedSets > 0
                ? `, ${explodedSets} set${explodedSets === 1 ? '' : 's'} exploded`
                : ''
            }`}
          </p>
        </div>
        {focused && (
          <Button type="button" variant="outline" size="sm" onClick={onClearFocus}>
            <X className="size-4" aria-hidden />
            Show all lines
          </Button>
        )}
      </div>
    </CardHeader>
  );
}

export function SalesOrderLinesTable({
  lines,
  findings = [],
  focusLineId = null,
  onClearFocus,
  editing,
  reference,
}: {
  lines: ProjectSalesOrderLine[];
  findings?: ProjectSalesOrderFinding[];
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
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({});
  const containerRef = React.useRef<HTMLDivElement>(null);

  const groups = React.useMemo(() => groupExplodedLines(lines), [lines]);

  const findingsByLine = React.useMemo(() => {
    const map = new Map<string, ProjectSalesOrderFinding[]>();
    findings.forEach((finding) => {
      if (!finding.line_id) return;
      map.set(finding.line_id, [...(map.get(finding.line_id) ?? []), finding]);
    });
    return map;
  }, [findings]);

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
    const out: DisplayRow[] = [];
    visibleGroups.forEach((group) => {
      out.push({
        line: group.parent,
        groupKey: group.key,
        isCompanion: false,
        companionCount: group.companions.length,
        sourcePoLineNo: group.sourcePoLineNo,
      });
      if (collapsed[group.key]) return;
      group.companions.forEach((companion) => {
        out.push({
          line: companion,
          groupKey: group.key,
          isCompanion: true,
          companionCount: group.companions.length,
          sourcePoLineNo: group.sourcePoLineNo,
        });
      });
    });
    return out;
  }, [collapsed, visibleGroups]);

  const columns = React.useMemo<ColumnDef<DisplayRow>[]>(
    () => [
      {
        id: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => (
          <span
            className={`tabular-nums ${row.original.isCompanion ? 'text-muted-foreground' : ''}`}
          >
            {row.original.line.line_no}
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
          const code = row.original.line.product_code || 'Not resolved';
          const flagged = findingsByLine.get(row.original.line.id) ?? [];
          // `acknowledged_at` is the backend's own gate; the name is a display field that
          // goes null when the acknowledger no longer resolves.
          const blocking = flagged.some(
            (finding) => finding.severity === 'hard' && !finding.acknowledged_at,
          );
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
              {blocking && (
                <Badge variant="destructive" appearance="light" size="sm" className="shrink-0">
                  Blocking
                </Badge>
              )}
            </div>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const text = row.original.line.description || '—';
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
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.line.qty}>
            {formatQty(row.original.line.qty)}
          </span>
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
            {row.original.line.uom || '—'}
          </span>
        ),
        size: 80,
        minSize: 60,
        meta: { headerTitle: 'UOM', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'unit_price',
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => (
          <span
            className={`block truncate tabular-nums ${
              isZeroMoney(row.original.line.unit_price) ? 'text-muted-foreground' : ''
            }`}
            title={row.original.line.unit_price}
          >
            {formatUnitPrice(row.original.line.unit_price)}
          </span>
        ),
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Unit price', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'amount',
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        cell: ({ row }) => {
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
        cell: ({ row }) =>
          row.original.line.delivery_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.line.delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">No date</span>
          ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Delivery', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'phase_label',
        header: ({ column }) => <DataGridColumnHeader title="Phase" column={column} />,
        cell: ({ row }) => {
          const text = row.original.line.phase_label || 'Unlabeled phase';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        meta: { headerTitle: 'Phase', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'source_po_line_no',
        header: ({ column }) => <DataGridColumnHeader title="From PO line" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground tabular-nums">
            {row.original.sourcePoLineNo ?? '—'}
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
          const text = row.original.line.stock_location || '-';
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
    [findingsByLine],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(rows.length / pagination.pageSize) || 0,
    getRowId: (row) => row.line.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

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
        {`Set from PO line ${row.sourcePoLineNo ?? '—'}: ${row.companionCount + 1} components`}
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
                editing={editing}
                reference={reference}
              />
            </div>
          </CardTable>
        </Card>
      </div>
    );
  }

  return (
    <div ref={containerRef}>
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
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
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
