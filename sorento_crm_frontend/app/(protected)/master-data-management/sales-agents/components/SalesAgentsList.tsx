'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { LoaderCircleIcon, MapPin, Tag } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { useBulkAnnotateSalesAgents, useSalesAgents } from '../hooks/useSalesAgents';
import { DEMAND_CLASS_OPTIONS, demandClassLabel } from '../lib/demandClass';
import { salesAgentSourceLabel } from '../lib/salesAgentSource';
import type { SalesAgent } from '../types/salesAgent.types';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

/** Which annotation a bulk dialog is setting. One field at a time, deliberately: a dialog
 *  that sets two at once has to answer "did I mean to clear the other one" every time. */
type BulkField = 'demand_class' | 'location_group';

const BULK_COPY: Record<BulkField, { title: string; label: string; placeholder: string }> = {
  demand_class: {
    title: 'Set demand class',
    label: 'Demand class',
    placeholder: 'Not set',
  },
  location_group: {
    title: 'Set location group',
    label: 'Location group',
    placeholder: 'e.g. BB',
  },
};

export default function SalesAgentsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'sales_agent', desc: false }]);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();

  // Back hands the list its own query string back, and the pager keeps
  // rewriting it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
  });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkField, setBulkField] = useState<BulkField | null>(null);
  const [bulkValue, setBulkValue] = useState('');

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, sorting]);

  const { data, isLoading, isError, error, refetch, isFetching } = useSalesAgents({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const bulkAnnotate = useBulkAnnotateSalesAgents();

  const rows = useMemo<SalesAgent[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;
  const selectedIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);

  // Carried into the record URL so its prev/next pager walks the SAME searched, sorted page
  // the user was reading (same param names as the list GET). Mirrors the sales-order list.
  const detailSearch = useMemo(
    () =>
      buildDetailSearch({
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery: debouncedSearch,
      }),
    [pagination.pageIndex, pagination.pageSize, sorting, debouncedSearch],
  );

  const detailHref = (agent: SalesAgent) =>
    `/master-data-management/sales-agents/${agent.id}${detailSearch ? `?${detailSearch}` : ''}`;

  /** The location groups this book already uses, offered before free entry so a typo does
   *  not quietly create a fourth group that matches no warehouse suffix. */
  const locationGroupOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const r of rows) {
      if (r.location_group) seen.add(r.location_group);
    }
    return [...seen].sort().map((g) => ({ value: g, label: g }));
  }, [rows]);

  const columns = useMemo<ColumnDef<SalesAgent>[]>(
    () => [
      buildSelectColumn<SalesAgent>({
        size: 44,
        rowLabel: (row) => `Select ${row.original.sales_agent}`,
      }),
      {
        accessorKey: 'sales_agent',
        header: ({ column }) => <DataGridColumnHeader title="Agent code" column={column} />,
        // The code IS the way in, the same as the SO number on the sales-order list. A real
        // anchor, so middle-click and copy-link work, and it stops its own click propagating
        // to the row handler that would otherwise navigate twice.
        cell: ({ row }) => (
          <Link
            href={detailHref(row.original)}
            onClick={(e) => e.stopPropagation()}
            className="truncate font-medium text-primary hover:underline"
            title={row.original.sales_agent}
          >
            {row.original.sales_agent}
          </Link>
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
            {salesAgentSourceLabel(row.original.source)}
          </Badge>
        ),
        size: 130,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-6 w-16" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'}>
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      // No actions column. Editing is the record page's job - the row already opens it, and
      // a pencil beside a clickable row is a second door to the same screen.
    ],
    [detailSearch],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    rowCount: total,
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const openBulk = (field: BulkField) => {
    if (selectedIds.length === 0) return;
    setBulkValue('');
    setBulkField(field);
  };

  const applyBulk = async () => {
    if (!bulkField) return;
    try {
      await bulkAnnotate.mutateAsync({
        sales_agent_ids: selectedIds,
        // Empty is an explicit "unset it on all of these", which is what `null` means to
        // the backend - the same thing the single-row modal's cleared select sends.
        [bulkField]: bulkValue || null,
      });
      setBulkField(null);
      setRowSelection({});
    } catch {
      // The mutation already toasted the reason; leave the dialog open so the selection
      // and the chosen value survive.
    }
  };

  // Two, one per annotation. The captain's first upload created 38 unclassified codes and
  // every one of them had to be opened, edited and saved on its own.
  const bulkActions: ToolbarAction[] = [
    {
      key: 'set-demand-class',
      label: 'Set demand class',
      icon: Tag,
      disabled: bulkAnnotate.isPending,
      onClick: () => openBulk('demand_class'),
    },
    {
      key: 'set-location-group',
      label: 'Set location group',
      icon: MapPin,
      disabled: bulkAnnotate.isPending,
      onClick: () => openBulk('location_group'),
    },
  ];

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
        // The whole row opens the record. The agent-code link stays a real anchor so
        // middle-click and copy-link still work, and stops its own click propagating.
        rowHref={(row) => detailHref(row)}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  isSettling={debouncedSearchSettling}
                  placeholder="Search agent code..."
                  aria-label="Clear search"
                  className="w-64"
                />
              }
              // Selection-gated, and the list HAS a selection column now, so the button is
              // reachable rather than permanently disabled.
              exportConfig={{ filename: 'sales_agents_export.xlsx' }}
              bulkActions={bulkActions}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      {/* Pick the value, then confirm - the write touches every selected row, so it states
          the count on the button rather than after the fact. */}
      <AlertDialog
        open={bulkField !== null}
        onOpenChange={(open) => {
          if (!open) setBulkField(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {bulkField ? BULK_COPY[bulkField].title : ''}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {`This applies to ${selectedIds.length} selected sales agent${
                selectedIds.length === 1 ? '' : 's'
              }.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {bulkField ? (
            <div className="space-y-1.5">
              <Label htmlFor="bulk-annotate-value">{BULK_COPY[bulkField].label}</Label>
              <SearchableSelect
                id="bulk-annotate-value"
                value={bulkValue}
                onChange={setBulkValue}
                options={
                  bulkField === 'demand_class' ? DEMAND_CLASS_OPTIONS : locationGroupOptions
                }
                placeholder={BULK_COPY[bulkField].placeholder}
                // Unset is a real choice on both columns - a class or a group set by
                // mistake has to come off the whole selection the same way it went on.
                clearable
                createOption={
                  bulkField === 'location_group'
                    ? {
                        // A group is a warehouse-code suffix somebody starts using, not a
                        // word the policy has to already know - so a new one is typed here
                        // rather than seeded first. The class select offers no such row:
                        // its vocabulary is closed and the backend refuses a third word.
                        label: (q) => (q ? `Use "${q.toUpperCase()}"` : null),
                        onCreate: (q) => setBulkValue(q.trim().toUpperCase()),
                      }
                    : undefined
                }
              />
            </div>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkAnnotate.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void applyBulk();
              }}
              disabled={bulkAnnotate.isPending}
            >
              {bulkAnnotate.isPending ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : null}
              {`Apply to ${selectedIds.length} agent${selectedIds.length === 1 ? '' : 's'}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
