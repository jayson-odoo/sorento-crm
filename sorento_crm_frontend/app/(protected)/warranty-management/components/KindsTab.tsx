'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Pencil, Plus, Search, TriangleAlert, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  useCreateKind,
  useDeleteKind,
  useKinds,
  useUpdateKind,
} from '../hooks/useWarrantyConfig';
import type { WarrantyKindRow, WarrantyKindWrite } from '../types/warranty-config.types';
import { KindFormDialog } from './KindFormDialog';
import { ScopeBadge } from './ScopeBadge';

/**
 * Zero is the whole point of this grid, so it is a flag rather than a numeral -
 * but the FLAG comes from the row (`has_no_rules` / `has_no_terms`, AC-P17), not
 * from `value === 0` here. A zero that only exists in a cell is invisible to
 * export, to MCP and to the AI assistant.
 */
function CountCell({ value, flagged }: { value: number; flagged: boolean }) {
  if (flagged) {
    return (
      <Badge variant="destructive" appearance="light" size="md">
        <TriangleAlert className="size-3.5" />
        {value}
      </Badge>
    );
  }
  return <span className="tabular-nums">{value}</span>;
}

export function KindsTab() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [noRulesOnly, setNoRulesOnly] = useState(false);
  const [noTermsOnly, setNoTermsOnly] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<WarrantyKindRow | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WarrantyKindRow | null>(null);
  const [refusedTarget, setRefusedTarget] = useState<WarrantyKindRow | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  const { data, isLoading, isError, error, refetch, isFetching } = useKinds(debouncedSearch);
  const createKind = useCreateKind();
  const updateKind = useUpdateKind();
  const deleteKind = useDeleteKind();

  const allRows = useMemo<WarrantyKindRow[]>(() => data ?? [], [data]);
  const rows = useMemo(
    () =>
      allRows.filter(
        (k) => (!noRulesOnly || k.has_no_rules) && (!noTermsOnly || k.has_no_terms),
      ),
    [allRows, noRulesOnly, noTermsOnly],
  );

  const unreachableCount = useMemo(
    () => allRows.filter((k) => k.has_no_rules).length,
    [allRows],
  );

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, noRulesOnly, noTermsOnly]);

  const nextSortOrder = useMemo(
    () => allRows.reduce((max, k) => Math.max(max, k.sort_order), 0) + 1,
    [allRows],
  );

  const submit = async (body: WarrantyKindWrite) => {
    setFormError(null);
    try {
      if (editing) {
        await updateKind.mutateAsync({ id: editing.id, body });
      } else {
        await createKind.mutateAsync(body);
      }
      setFormOpen(false);
      setEditing(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const columns = useMemo<ColumnDef<WarrantyKindRow>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Kind" column={column} />,
        size: 280,
        meta: { headerTitle: 'Kind' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'code',
        accessorFn: (row) => row.code,
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 220,
        meta: { headerTitle: 'Code' },
        cell: ({ row }) => (
          <span className="block truncate font-mono text-xs" title={row.original.code}>
            {row.original.code}
          </span>
        ),
      },
      {
        id: 'consumer_label',
        accessorFn: (row) => row.consumer_label,
        header: ({ column }) => <DataGridColumnHeader title="Consumer label" column={column} />,
        size: 240,
        meta: { headerTitle: 'Consumer label' },
        cell: ({ row }) =>
          row.original.consumer_label ? (
            <span className="block truncate" title={row.original.consumer_label}>
              {row.original.consumer_label}
            </span>
          ) : (
            <span className="text-muted-foreground">Not set</span>
          ),
      },
      {
        id: 'rule_count',
        accessorFn: (row) => row.rule_count,
        header: ({ column }) => <DataGridColumnHeader title="Rules" column={column} />,
        size: 100,
        meta: { headerTitle: 'Rules', headerClassName: 'text-right', cellClassName: 'text-right' },
        cell: ({ row }) => (
          <CountCell value={row.original.rule_count} flagged={row.original.has_no_rules} />
        ),
      },
      {
        id: 'term_count',
        accessorFn: (row) => row.term_count,
        header: ({ column }) => <DataGridColumnHeader title="Terms" column={column} />,
        size: 100,
        meta: { headerTitle: 'Terms', headerClassName: 'text-right', cellClassName: 'text-right' },
        cell: ({ row }) => (
          <CountCell value={row.original.term_count} flagged={row.original.has_no_terms} />
        ),
      },
      {
        id: 'sort_order',
        accessorFn: (row) => row.sort_order,
        header: ({ column }) => <DataGridColumnHeader title="Order" column={column} />,
        size: 90,
        meta: { headerTitle: 'Order', headerClassName: 'text-right', cellClassName: 'text-right' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.sort_order}</span>,
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Active' },
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
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 100,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Edit"
              aria-label="Edit kind"
              onClick={() => {
                setFormError(null);
                setEditing(row.original);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Delete"
              aria-label="Delete kind"
              onClick={() => {
                // AC-P12: both FK columns cascade, so a hard delete would strip
                // warranty promises out of every policy at once. Referenced kinds
                // never reach the confirmation.
                if (!row.original.has_no_terms || !row.original.has_no_rules) {
                  setRefusedTarget(row.original);
                } else {
                  setDeleteTarget(row.original);
                }
              }}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    // Client-side paging + sorting: `GET /kinds` returns the whole (small) list,
    // so without these the footer counts a page the grid never actually cuts.
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const activeFilterCount = (noRulesOnly ? 1 : 0) + (noTermsOnly ? 1 : 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <ScopeBadge scope={{ kind: 'shared' }} />
        {!isLoading && unreachableCount > 0 ? (
          <Badge variant="destructive" appearance="light" size="md">
            <TriangleAlert className="size-3.5" />
            {unreachableCount} of {allRows.length} have no rule
          </Badge>
        ) : null}
      </div>

      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load product kinds.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        listingKey="warranty.kinds.view"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          isError
            ? 'Product kinds could not be loaded.'
            : 'No product kinds match. Add one, or clear the filters.'
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              onRefresh={async () => {
                await refetch();
              }}
              isRefreshing={isFetching}
              exportConfig={false}
              filters={{
                kind: 'custom',
                active: activeFilterCount > 0,
                activeCount: activeFilterCount,
                content: (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="kinds-no-rules"
                        checked={noRulesOnly}
                        onCheckedChange={(v) => setNoRulesOnly(v === true)}
                      />
                      <Label htmlFor="kinds-no-rules">No rules</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="kinds-no-terms"
                        checked={noTermsOnly}
                        onCheckedChange={(v) => setNoTermsOnly(v === true)}
                      />
                      <Label htmlFor="kinds-no-terms">No terms</Label>
                    </div>
                  </div>
                ),
              }}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search kinds..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-56 ps-9"
                    aria-label="Search kinds"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 size-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              primaryAction={
                <Button
                  onClick={() => {
                    setFormError(null);
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" /> Add kind
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

      <KindFormDialog
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) {
            setEditing(null);
            setFormError(null);
          }
        }}
        initial={editing}
        nextSortOrder={nextSortOrder}
        onSubmit={submit}
        isSubmitting={createKind.isPending || updateKind.isPending}
        error={formError}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. Kind <strong>{deleteTarget?.name}</strong> will be
            permanently removed. No term or rule references it.
          </>
        }
        successMessage="Kind deleted"
        onDelete={async () => {
          if (deleteTarget) await deleteKind.mutateAsync(deleteTarget.id);
        }}
        onSuccess={() => setDeleteTarget(null)}
      />

      <AlertDialog open={!!refusedTarget} onOpenChange={(o) => !o && setRefusedTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cannot delete</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogDescription>
            <strong>{refusedTarget?.name}</strong> is still referenced by{' '}
            <strong>{refusedTarget?.term_count}</strong> term
            {refusedTarget?.term_count === 1 ? '' : 's'} and{' '}
            <strong>{refusedTarget?.rule_count}</strong> rule
            {refusedTarget?.rule_count === 1 ? '' : 's'}. Remove those first.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogAction onClick={() => setRefusedTarget(null)}>Close</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
