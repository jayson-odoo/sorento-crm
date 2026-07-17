'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTable,
  CardToolbar,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { EM_DASH } from '../../lib/format';
import { useCategoryOptions } from '../../hooks/useScmOptions';
import {
  useCreateTopic,
  useDeleteTopic,
  useMarketTopics,
  useUpdateTopic,
} from '../hooks/useMarket';
import { CADENCE_LABEL, resolveCategoryLabel } from '../lib/marketLabels';
import type { MarketResearchTopic, MarketResearchTopicWrite } from '../types/market.types';
import { AddEditTopicModal } from './AddEditTopicModal';

export function MarketTopicsGrid() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MarketResearchTopic | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MarketResearchTopic | null>(null);

  const { data, isLoading, isError, error } = useMarketTopics();
  const { data: categoryOptions } = useCategoryOptions();
  const createTopic = useCreateTopic();
  const updateTopic = useUpdateTopic();
  const deleteTopic = useDeleteTopic();

  const rows = useMemo<MarketResearchTopic[]>(() => data ?? [], [data]);

  const columns = useMemo<ColumnDef<MarketResearchTopic>[]>(
    () => [
      {
        accessorKey: 'label',
        header: ({ column }) => <DataGridColumnHeader title="Topic" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.label}>
            {row.original.label}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Topic', skeleton: <Skeleton className="h-5 w-40" /> },
      },
      {
        id: 'category',
        accessorFn: (row) => row.category_ref ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Category" column={column} />,
        cell: ({ row }) => {
          const label = resolveCategoryLabel(row.original.category_ref, categoryOptions);
          return label ? (
            <span className="truncate" title={label}>
              {label}
            </span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          );
        },
        size: 180,
        meta: { headerTitle: 'Category' },
      },
      {
        accessorKey: 'currency',
        header: ({ column }) => <DataGridColumnHeader title="Currency" column={column} />,
        cell: ({ row }) =>
          row.original.currency ? (
            <Badge variant="info" appearance="light" size="md">
              {row.original.currency}
            </Badge>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ),
        size: 110,
        meta: { headerTitle: 'Currency' },
      },
      {
        accessorKey: 'cadence',
        header: ({ column }) => <DataGridColumnHeader title="Cadence" column={column} />,
        cell: ({ row }) => CADENCE_LABEL[row.original.cadence],
        size: 130,
        meta: { headerTitle: 'Cadence' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="success" appearance="light" size="md">
              Active
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" size="md">
              Inactive
            </Badge>
          ),
        size: 110,
        meta: { headerTitle: 'Active' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label="Edit topic"
              title="Edit topic"
              onClick={() => {
                setEditing(row.original);
                setModalOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label="Delete topic"
              title="Delete topic"
              onClick={() => setDeleteTarget(row.original)}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
      },
    ],
    [categoryOptions],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting, globalFilter: searchQuery },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearchQuery,
    globalFilterFn: (row, _columnId, filterValue) => {
      const q = String(filterValue).toLowerCase().trim();
      if (!q) return true;
      const t = row.original;
      return (
        t.label.toLowerCase().includes(q) ||
        (t.category_ref ?? '').toLowerCase().includes(q) ||
        (t.currency ?? '').toLowerCase().includes(q) ||
        t.search_prompt.toLowerCase().includes(q)
      );
    },
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const submitTopic = async (body: MarketResearchTopicWrite) => {
    if (editing) {
      await updateTopic.mutateAsync({ id: editing.id, body });
    } else {
      await createTopic.mutateAsync(body);
    }
    setModalOpen(false);
    setEditing(null);
  };

  const recordCount = table.getFilteredRowModel().rows.length;

  return (
    <div className="space-y-3">
      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load research topics.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={recordCount}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage="No research topics configured yet."
      >
        <Card>
          <CardHeader className="flex items-center justify-between gap-3">
            <CardHeading>
              <div className="relative">
                <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search topics..."
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
            </CardHeading>
            <CardToolbar>
              <Button
                onClick={() => {
                  setEditing(null);
                  setModalOpen(true);
                }}
              >
                <Plus className="size-4" />
                Add topic
              </Button>
            </CardToolbar>
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

      <AddEditTopicModal
        open={modalOpen}
        onOpenChange={(o) => {
          setModalOpen(o);
          if (!o) setEditing(null);
        }}
        mode={editing ? 'edit' : 'create'}
        initial={editing}
        onSubmit={submitTopic}
        isSubmitting={createTopic.isPending || updateTopic.isPending}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. The research topic{' '}
            <strong>{deleteTarget?.label}</strong> will be permanently removed.
          </>
        }
        successMessage="Research topic deleted"
        onDelete={async () => {
          if (deleteTarget) await deleteTopic.mutateAsync(deleteTarget.id);
        }}
        onSuccess={() => setDeleteTarget(null)}
      />
    </div>
  );
}
