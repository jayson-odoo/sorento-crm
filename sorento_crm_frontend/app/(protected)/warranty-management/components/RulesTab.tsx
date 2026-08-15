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
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useCreateKindRule,
  useDeleteKindRule,
  useKindOptions,
  useKindRules,
  useUpdateKindRule,
} from '../hooks/useWarrantyConfig';
import { formatMatchTypeLabel } from '../lib/warrantyLabels';
import type {
  WarrantyKindRuleRow,
  WarrantyKindRuleUpdate,
} from '../types/warranty-config.types';
import { KindRuleFormDialog } from './KindRuleFormDialog';
import { RuleTesterCard } from './RuleTesterCard';
import { ScopeBadge } from './ScopeBadge';

export function RulesTab() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [kindFilter, setKindFilter] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<WarrantyKindRuleRow | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WarrantyKindRuleRow | null>(null);

  const { data: kindOptions } = useKindOptions();
  const { data, isLoading, isError, error, refetch, isFetching } = useKindRules(kindFilter || null);

  const createRule = useCreateKindRule();
  const updateRule = useUpdateKindRule();
  const deleteRule = useDeleteKindRule();

  const rows = useMemo<WarrantyKindRuleRow[]>(() => data ?? [], [data]);
  const kinds = useMemo(() => kindOptions ?? [], [kindOptions]);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [kindFilter]);

  const submit = async (body: WarrantyKindRuleUpdate) => {
    setFormError(null);
    try {
      if (editing) {
        // PATCH is partial: an edit that never touched the match type omits the
        // key, so a stored value the picker does not know survives (AC-P24).
        await updateRule.mutateAsync({ id: editing.id, body });
      } else {
        // Create is strict - the dialog always sends a match type when there is
        // no incumbent row to preserve.
        if (!body.match_type) throw new Error('Select a match type');
        await createRule.mutateAsync({ ...body, match_type: body.match_type });
      }
      setFormOpen(false);
      setEditing(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const columns = useMemo<ColumnDef<WarrantyKindRuleRow>[]>(
    () => [
      {
        id: 'kind_name',
        accessorFn: (row) => row.kind_name,
        header: ({ column }) => <DataGridColumnHeader title="Kind" column={column} />,
        size: 240,
        meta: { headerTitle: 'Kind' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.kind_name}>
            {row.original.kind_name}
          </span>
        ),
      },
      {
        id: 'match_type',
        accessorFn: (row) => row.match_type,
        header: ({ column }) => <DataGridColumnHeader title="Match type" column={column} />,
        size: 150,
        meta: { headerTitle: 'Match type' },
        cell: ({ row }) => (
          <Badge variant="info" appearance="light" size="md">
            {formatMatchTypeLabel(row.original.match_type)}
          </Badge>
        ),
      },
      {
        id: 'match_value',
        accessorFn: (row) => row.match_value,
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        size: 420,
        meta: { headerTitle: 'Value' },
        cell: ({ row }) => (
          <span className="block truncate font-mono text-xs" title={row.original.match_value}>
            {row.original.match_value}
          </span>
        ),
      },
      {
        id: 'priority',
        accessorFn: (row) => row.priority,
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        size: 110,
        meta: {
          headerTitle: 'Priority',
          headerClassName: 'text-right',
          cellClassName: 'text-right',
        },
        cell: ({ row }) => <span className="tabular-nums">{row.original.priority}</span>,
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
              aria-label="Edit rule"
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
              aria-label="Delete rule"
              onClick={() => setDeleteTarget(row.original)}
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
    // Client-side paging + sorting: `GET /kind-rules` returns the whole list.
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ScopeBadge scope={{ kind: 'shared' }} />
      </div>

      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load kind rules.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        listingKey="warranty.kinds.view::rules"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          isError
            ? 'Kind rules could not be loaded.'
            : 'No rules yet. Add one so products can reach a kind.'
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
              searchSlot={
                <div className="flex items-center gap-2">
                  <Label htmlFor="rules-kind-filter" className="shrink-0 text-muted-foreground">
                    Kind
                  </Label>
                  <SearchableSelect
                    id="rules-kind-filter"
                    value={kindFilter}
                    onChange={setKindFilter}
                    clearable
                    placeholder="All kinds"
                    className="w-56"
                    options={kinds.map((k) => ({
                      value: k.id,
                      label: k.name,
                      searchText: k.code,
                    }))}
                  />
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
                  <Plus className="size-4" /> Add rule
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

      <RuleTesterCard kinds={kinds} />

      <KindRuleFormDialog
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) {
            setEditing(null);
            setFormError(null);
          }
        }}
        initial={editing}
        kinds={kinds}
        defaultKindId={kindFilter}
        onSubmit={submit}
        isSubmitting={createRule.isPending || updateRule.isPending}
        error={formError}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. The{' '}
            <strong>
              {deleteTarget ? formatMatchTypeLabel(deleteTarget.match_type) : ''}
            </strong>{' '}
            rule <strong>{deleteTarget?.match_value}</strong> for{' '}
            <strong>{deleteTarget?.kind_name}</strong> will be permanently removed.
          </>
        }
        successMessage="Rule deleted"
        onDelete={async () => {
          if (deleteTarget) await deleteRule.mutateAsync(deleteTarget.id);
        }}
        onSuccess={() => setDeleteTarget(null)}
      />
    </div>
  );
}
