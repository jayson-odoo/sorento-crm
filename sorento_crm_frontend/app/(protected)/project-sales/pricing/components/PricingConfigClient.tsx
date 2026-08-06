'use client';

import * as React from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Boxes, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  usePriceFloorMutations,
  usePriceFloors,
  useProjectSeries,
  useSeriesMutations,
} from '../../_shared/hooks/useProjects';
import type { PriceFloorRule, ProjectSeries } from '../../_shared/types/project.types';
// Shared, because the product Pricing tab and the category editor open the same dialog
// with a target already chosen. One dialog, one set of copy.
import { PriceFloorDialog } from '../../_shared/components/PriceFloorDialog';
import { describeFloorRule } from '../../_shared/lib/priceFloor';
import { SeriesDialog } from './SeriesDialog';

const LEVEL_LABELS: Record<string, string> = {
  product: 'Product',
  category: 'Category',
  system: 'Company default',
};

/**
 * The two policies that decide whether a quoted line raises an alert.
 *
 * They live on one screen because they answer the same question from two sides: the
 * SERIES says what we are supposed to be selling on this scope, and the FLOOR says how
 * cheap it is allowed to go. Splitting them would hide that a scope can be perfectly
 * on-series and still under-priced.
 *
 * Each is a standard list with its own toolbar, not a card panel with floating icons, so
 * an admin reads them the same way they read every other screen. The empty states are
 * unchanged: each one names the CONSEQUENCE of the policy not existing, which is the only
 * reason an admin would set it.
 *
 * Neither is retroactive. Both are copied onto a line when it is priced (AC-E7), so
 * editing a policy here never rewrites a quotation the customer already holds.
 */
export function PricingConfigClient() {
  const series = useProjectSeries(true);
  const floors = usePriceFloors();
  const seriesMutations = useSeriesMutations();
  const floorMutations = usePriceFloorMutations();

  const [seriesDialog, setSeriesDialog] = React.useState<{
    series: ProjectSeries | null;
  } | null>(null);
  const [floorDialog, setFloorDialog] = React.useState<{
    rule: PriceFloorRule | null;
  } | null>(null);
  const [deletingSeries, setDeletingSeries] = React.useState<ProjectSeries | null>(null);
  const [deletingFloor, setDeletingFloor] = React.useState<PriceFloorRule | null>(null);

  const seriesRows = React.useMemo(() => series.data ?? [], [series.data]);
  const floorRows = React.useMemo(() => floors.data ?? [], [floors.data]);

  // Stable identities: both grids build their columns in a `useMemo` keyed on these.
  const addSeries = React.useCallback(() => setSeriesDialog({ series: null }), []);
  const editSeries = React.useCallback(
    (row: ProjectSeries) => setSeriesDialog({ series: row }),
    [],
  );
  const addFloor = React.useCallback(() => setFloorDialog({ rule: null }), []);
  const editFloor = React.useCallback(
    (rule: PriceFloorRule) => setFloorDialog({ rule }),
    [],
  );

  return (
    <div className="space-y-5">
      <header className="min-w-0 break-words">
        <h1 className="text-xl font-semibold">Pricing policy</h1>
        <p className="text-sm text-muted-foreground">
          What each scope is supposed to be quoted from, and how low its price may go.
        </p>
      </header>

      <SeriesGrid
        rows={seriesRows}
        isLoading={series.isLoading}
        isFetching={series.isFetching}
        onRefresh={() => void series.refetch()}
        onAdd={addSeries}
        onEdit={editSeries}
        onDelete={setDeletingSeries}
      />

      <PriceFloorsGrid
        rows={floorRows}
        isLoading={floors.isLoading}
        isFetching={floors.isFetching}
        onRefresh={() => void floors.refetch()}
        onAdd={addFloor}
        onEdit={editFloor}
        onDelete={setDeletingFloor}
      />

      {seriesDialog && (
        <SeriesDialog
          series={seriesDialog.series}
          onDone={() => setSeriesDialog(null)}
        />
      )}

      {floorDialog && (
        <PriceFloorDialog rule={floorDialog.rule} onDone={() => setFloorDialog(null)} />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deletingSeries)}
        onOpenChange={(next) => !next && setDeletingSeries(null)}
        title="Confirm delete"
        description={
          deletingSeries
            ? `Delete the series "${deletingSeries.name}"? This action cannot be undone. A series still used by a quotation cannot be deleted, so deactivate it instead.`
            : ''
        }
        onDelete={async () => {
          if (!deletingSeries) return;
          await seriesMutations.remove.mutateAsync(deletingSeries.id);
        }}
        onSuccess={() => setDeletingSeries(null)}
        successMessage="Series deleted"
      />

      <ConfirmDeleteDialog
        open={Boolean(deletingFloor)}
        onOpenChange={(next) => !next && setDeletingFloor(null)}
        title="Confirm delete"
        description={
          deletingFloor
            ? `Delete the ${(LEVEL_LABELS[deletingFloor.level] ?? deletingFloor.level).toLowerCase()} floor for "${deletingFloor.product_code ?? deletingFloor.category_name ?? 'everything else'}"? This action cannot be undone. Lines already priced keep the floor that applied to them.`
            : ''
        }
        onDelete={async () => {
          if (!deletingFloor) return;
          await floorMutations.remove.mutateAsync(deletingFloor.id);
        }}
        onSuccess={() => setDeletingFloor(null)}
        successMessage="Price floor removed"
      />
    </div>
  );
}

function SeriesGrid({
  rows,
  isLoading,
  isFetching,
  onRefresh,
  onAdd,
  onEdit,
  onDelete,
}: {
  rows: ProjectSeries[];
  isLoading: boolean;
  isFetching: boolean;
  onRefresh: () => void;
  onAdd: () => void;
  onEdit: (row: ProjectSeries) => void;
  onDelete: (row: ProjectSeries) => void;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'name', desc: false }]);

  const columns = React.useMemo<ColumnDef<ProjectSeries>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Series" column={column} />,
        size: 240,
        meta: { headerTitle: 'Series', skeleton: <Skeleton className="h-4 w-36" /> },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'brand_name',
        accessorFn: (row) => row.brand_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        size: 150,
        meta: { headerTitle: 'Brand', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.brand_name ? (
            <Badge variant="secondary" className="truncate" title={row.original.brand_name}>
              {row.original.brand_name}
            </Badge>
          ) : (
            <span className="text-muted-foreground">Any brand</span>
          ),
      },
      {
        id: 'coverage',
        // Two different numbers, both needed: the picks are what the admin chose, the
        // covered count is what a line is actually judged against.
        accessorFn: (row) => row.covered_category_count,
        header: ({ column }) => <DataGridColumnHeader title="Coverage" column={column} />,
        size: 200,
        meta: { headerTitle: 'Coverage', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => {
          const text = `${row.original.category_ids.length} nominated, ${row.original.covered_category_count} covered`;
          return (
            <span className="flex min-w-0 items-center gap-1" title={text}>
              <Boxes className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{text}</span>
            </span>
          );
        },
      },
      {
        id: 'category_names',
        accessorFn: (row) => row.category_names.join(', '),
        header: ({ column }) => <DataGridColumnHeader title="Categories" column={column} />,
        size: 240,
        enableSorting: false,
        meta: { headerTitle: 'Categories', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) =>
          row.original.category_names.length > 0 ? (
            <span
              className="block truncate"
              title={row.original.category_names.join(', ')}
            >
              {row.original.category_names.join(', ')}
            </span>
          ) : (
            <span className="text-muted-foreground">None nominated</span>
          ),
      },
      {
        accessorKey: 'quotation_count',
        header: ({ column }) => <DataGridColumnHeader title="Used by" column={column} />,
        size: 170,
        meta: { headerTitle: 'Used by', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) =>
          row.original.quotation_count > 0 ? (
            <span className="block truncate">
              {`Used by ${row.original.quotation_count} quotation${row.original.quotation_count === 1 ? '' : 's'}`}
            </span>
          ) : (
            <span className="text-muted-foreground">Not quoted yet</span>
          ),
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 110,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="outline">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 110,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) => (
          <RowActions
            editLabel={`Edit ${row.original.name}`}
            deleteLabel={`Delete ${row.original.name}`}
            onEdit={() => onEdit(row.original)}
            onDelete={() => onDelete(row.original)}
          />
        ),
      },
    ],
    [onEdit, onDelete],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      listingKey="projects.types.view::series"
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        <div className="px-6 py-10 text-center">
          <p className="text-sm font-semibold">No series yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Without one, a quotation cannot say what counts as standard, and no line is
            ever flagged as off-series.
          </p>
          <Button type="button" className="mt-4" onClick={onAdd}>
            <Plus className="size-4" aria-hidden />
            Add the first series
          </Button>
        </div>
      }
    >
      <Card>
        <CardHeader className="block pt-5">
          <CardTitle className="text-sm">Series</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            A series is the set of categories a scope is meant to be quoted from.
            Nominating a parent category covers everything under it.
          </p>
          <DataGridListToolbar
            table={table}
            exportConfig={{ filename: 'project_series_export.xlsx' }}
            onRefresh={onRefresh}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button type="button" size="sm" onClick={onAdd}>
                <Plus className="size-4" aria-hidden />
                Add series
              </Button>
            }
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

function PriceFloorsGrid({
  rows,
  isLoading,
  isFetching,
  onRefresh,
  onAdd,
  onEdit,
  onDelete,
}: {
  rows: PriceFloorRule[];
  isLoading: boolean;
  isFetching: boolean;
  onRefresh: () => void;
  onAdd: () => void;
  onEdit: (rule: PriceFloorRule) => void;
  onDelete: (rule: PriceFloorRule) => void;
}) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const columns = React.useMemo<ColumnDef<PriceFloorRule>[]>(
    () => [
      {
        accessorKey: 'level',
        header: ({ column }) => <DataGridColumnHeader title="Level" column={column} />,
        size: 160,
        meta: { headerTitle: 'Level', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => {
          const label = LEVEL_LABELS[row.original.level] ?? row.original.level;
          return (
            <Badge variant="secondary" className="truncate" title={label}>
              {label}
            </Badge>
          );
        },
      },
      {
        id: 'applies_to',
        accessorFn: (row) =>
          row.product_code ?? row.category_name ?? 'Everything without a more specific rule',
        header: ({ column }) => <DataGridColumnHeader title="Applies to" column={column} />,
        size: 260,
        meta: { headerTitle: 'Applies to', skeleton: <Skeleton className="h-4 w-36" /> },
        cell: ({ row }) => {
          const target =
            row.original.product_code ??
            row.original.category_name ??
            'Everything without a more specific rule';
          return (
            <span className="block truncate font-medium" title={target}>
              {target}
            </span>
          );
        },
      },
      {
        id: 'rule',
        accessorFn: (row) => describeFloorRule(row),
        header: ({ column }) => <DataGridColumnHeader title="Rule" column={column} />,
        size: 280,
        enableSorting: false,
        meta: { headerTitle: 'Rule', skeleton: <Skeleton className="h-4 w-40" /> },
        // A sentence, not a mode plus a number: an admin who cannot tell which rule wins
        // cannot set the rules.
        cell: ({ row }) => {
          const sentence = describeFloorRule(row.original);
          return (
            <span className="block truncate" title={sentence}>
              {sentence}
            </span>
          );
        },
      },
      {
        id: 'notes',
        accessorFn: (row) => row.notes ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Notes" column={column} />,
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Notes', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) =>
          row.original.notes ? (
            <span className="block truncate" title={row.original.notes}>
              {row.original.notes}
            </span>
          ) : (
            <span className="text-muted-foreground">None</span>
          ),
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 110,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="outline">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 110,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) => (
          <RowActions
            editLabel="Edit floor"
            deleteLabel="Delete floor"
            onEdit={() => onEdit(row.original)}
            onDelete={() => onDelete(row.original)}
          />
        ),
      },
    ],
    [onEdit, onDelete],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    // The server returns the rules in the order they TAKE EFFECT (product beats its
    // category, category beats its parent, company default last). A sortable header
    // would let an admin scramble the one ordering that explains which rule wins.
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      listingKey="projects.types.view::price-floors"
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        <div className="px-6 py-10 text-center">
          <p className="text-sm font-semibold">No floors set</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Every price is accepted without an alert until at least one floor exists. A
            company default is the usual place to start.
          </p>
          <Button type="button" className="mt-4" onClick={onAdd}>
            <Plus className="size-4" aria-hidden />
            Set the first floor
          </Button>
        </div>
      }
    >
      <Card>
        <CardHeader className="block pt-5">
          <CardTitle className="text-sm">Price floors</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Listed in the order they take effect: a product rule beats its category, a
            category beats its parent, and the company default is the last word.
          </p>
          <DataGridListToolbar
            table={table}
            exportConfig={{ filename: 'price_floors_export.xlsx' }}
            onRefresh={onRefresh}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button type="button" size="sm" onClick={onAdd}>
                <Plus className="size-4" aria-hidden />
                Add floor
              </Button>
            }
          />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

function RowActions({
  editLabel,
  deleteLabel,
  onEdit,
  onDelete,
}: {
  editLabel: string;
  deleteLabel: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onEdit}
            aria-label={editLabel}
          >
            <Pencil className="size-4 text-muted-foreground" aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Edit</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onDelete}
            aria-label={deleteLabel}
          >
            <Trash2 className="size-4 text-destructive" aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Delete</TooltipContent>
      </Tooltip>
    </div>
  );
}
