'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Pencil, Search, X } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useAnnotateSalesAgent, useSalesAgents } from '../hooks/useSalesAgents';
import { demandClassLabel } from '../lib/demandClass';
import type { SalesAgent, SalesAgentAnnotationPayload } from '../types/salesAgent.types';
import { EditSalesAgentModal } from './EditSalesAgentModal';

/** How a row got here. `import` is a row an order upload created on meeting a new code. */
const SOURCE_LABEL: Record<SalesAgent['source'], string> = {
  autocount: 'AutoCount',
  manual: 'Manual',
  import: 'Import',
};

export default function SalesAgentsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'sales_agent', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [editing, setEditing] = useState<SalesAgent | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, sorting]);

  const { data, isLoading, isError, error, refetch, isFetching } = useSalesAgents({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const annotate = useAnnotateSalesAgent();

  const rows = useMemo<SalesAgent[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const columns = useMemo<ColumnDef<SalesAgent>[]>(
    () => [
      {
        accessorKey: 'sales_agent',
        header: ({ column }) => <DataGridColumnHeader title="Agent code" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.sales_agent}>
            {row.original.sales_agent}
          </span>
        ),
        size: 180,
        meta: { headerTitle: 'Agent code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'person_label',
        header: ({ column }) => <DataGridColumnHeader title="Person" column={column} />,
        cell: ({ row }) =>
          row.original.person_label ? (
            <span className="truncate" title={row.original.person_label}>
              {row.original.person_label}
            </span>
          ) : (
            <span className="text-muted-foreground">Not set</span>
          ),
        size: 200,
        meta: { headerTitle: 'Person', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'demand_class',
        header: ({ column }) => <DataGridColumnHeader title="Demand class" column={column} />,
        cell: ({ row }) =>
          row.original.demand_class ? (
            <Badge variant="info" appearance="light" size="md">
              {demandClassLabel(row.original.demand_class)}
            </Badge>
          ) : (
            <span className="text-muted-foreground">Not set</span>
          ),
        size: 160,
        meta: { headerTitle: 'Demand class', skeleton: <Skeleton className="h-6 w-20" /> },
      },
      {
        accessorKey: 'location_group',
        header: ({ column }) => <DataGridColumnHeader title="Location group" column={column} />,
        cell: ({ row }) =>
          row.original.location_group ? (
            <Badge variant="secondary" appearance="light" size="md">
              {row.original.location_group}
            </Badge>
          ) : (
            <span className="text-muted-foreground">Not set</span>
          ),
        size: 150,
        meta: { headerTitle: 'Location group', skeleton: <Skeleton className="h-6 w-16" /> },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="light" size="md">
            {SOURCE_LABEL[row.original.source] ?? row.original.source}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-6 w-16" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label={`Edit ${row.original.sales_agent}`}
              title="Edit"
              onClick={() => setEditing(row.original)}
            >
              <Pencil className="size-4" />
            </Button>
          </div>
        ),
        size: 80,
        enableSorting: false,
        enableHiding: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    rowCount: total,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const save = async (payload: SalesAgentAnnotationPayload) => {
    if (!editing) return;
    await annotate.mutateAsync({ id: editing.id, data: payload });
    setEditing(null);
  };

  return (
    <div className="space-y-3">
      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load sales agents.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        listingKey="master_data.sales_agents.view"
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage="No sales agents found."
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search agent code..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-64 ps-9"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              // Export is selection-gated and this list has no selection column, so
              // offering it would render a permanently disabled button.
              exportConfig={false}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
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

      <EditSalesAgentModal
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        agent={editing}
        isSaving={annotate.isPending}
        onSave={save}
      />
    </div>
  );
}
