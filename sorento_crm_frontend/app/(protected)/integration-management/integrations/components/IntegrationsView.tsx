'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { Plus } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/PageHeader';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { useIntegrations } from '../hooks/useIntegrations';
import type { Integration } from '../types/integration.types';
import { IntegrationFormDialog } from './IntegrationFormDialog';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

export function StatusCell({ integration }: { integration: Integration }) {
  if (!integration.is_active) {
    return <Badge variant="secondary" appearance="light" size="sm">Inactive</Badge>;
  }
  if (integration.status === 'ERROR') {
    return <Badge variant="destructive" appearance="light" size="sm">Error</Badge>;
  }
  if (integration.status === 'ACTIVE') {
    return <Badge variant="success" appearance="light" size="sm">Connected</Badge>;
  }
  // UNVERIFIED is honest: the row exists but has never successfully
  // authenticated, so "Connected" would overstate it.
  return <Badge variant="outline" size="sm">Unverified</Badge>;
}

export function IntegrationsView() {
  const router = useRouter();
  const { data, isLoading, isError, error } = useIntegrations();
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  const rows = useMemo(() => {
    const all = data ?? [];
    if (!search.trim()) return all;
    const q = search.toLowerCase();
    return all.filter(
      (i) =>
        i.name.toLowerCase().includes(q) ||
        i.type.toLowerCase().includes(q) ||
        (i.act_as_user_name ?? '').toLowerCase().includes(q),
    );
  }, [data, search]);

  const columns = useMemo<ColumnDef<Integration>[]>(
    () => [
      {
        accessorKey: 'name',
        id: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 260,
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium" title={row.original.name}>
              {row.original.name}
            </div>
            <div
              className="truncate text-xs text-muted-foreground"
              title={row.original.act_as_user_name ?? undefined}
            >
              {row.original.act_as_user_name ? (
                `Acts as ${row.original.act_as_user_name}`
              ) : (
                // Fails closed at the auth layer, so say so rather than
                // leaving a blank that reads as "fine".
                <span className="text-destructive">No principal - cannot authenticate</span>
              )}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'type',
        id: 'type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 150,
        cell: ({ row }) => <span className="truncate">{row.original.type}</span>,
      },
      {
        accessorKey: 'status',
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 130,
        cell: ({ row }) => <StatusCell integration={row.original} />,
      },
      {
        id: 'keys',
        header: ({ column }) => <DataGridColumnHeader title="Keys" column={column} />,
        size: 110,
        cell: ({ row }) => {
          const live = row.original.keys.filter((k) => k.is_active).length;
          if (row.original.keys.length === 0) {
            return <span className="text-xs text-muted-foreground">None</span>;
          }
          return (
            <span className="text-xs">
              {live} active
              {row.original.keys.length > live && (
                <span className="text-muted-foreground">
                  {' '}
                  / {row.original.keys.length - live} retired
                </span>
              )}
            </span>
          );
        },
      },
      {
        accessorKey: 'last_used_at',
        id: 'last_used_at',
        header: ({ column }) => <DataGridColumnHeader title="Last used" column={column} />,
        size: 180,
        cell: ({ row }) =>
          row.original.last_used_at ? (
            <span className="truncate">
              {formatDateTimeInMalaysia(row.original.last_used_at)}
            </span>
          ) : (
            <span className="text-muted-foreground"> - </span>
          ),
      },
      {
        accessorKey: 'last_error',
        id: 'last_error',
        header: ({ column }) => <DataGridColumnHeader title="Last error" column={column} />,
        size: 220,
        cell: ({ row }) =>
          row.original.last_error ? (
            <span className="truncate text-destructive" title={row.original.last_error}>
              {row.original.last_error}
            </span>
          ) : (
            <span className="text-muted-foreground"> - </span>
          ),
      },
      {
        accessorKey: 'created_at',
        id: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created" column={column} />,
        size: 160,
        cell: ({ row }) => (
          <span className="truncate">{formatDateTimeInMalaysia(row.original.created_at)}</span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  if (isError) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">
          {(error as Error)?.message ?? 'Failed to load integrations'}
        </p>
      </div>
    );
  }

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => setFormOpen(true)}>
      <Plus className="size-4" /> Connect integration
    </Button>
  );

  return (
    <div className="space-y-4 p-4 md:p-6">
      <PageHeader title="Integrations">
        <p className="text-sm text-muted-foreground">
          Systems that call Sorento with an API key. Each authenticates as its own user, so
          that user&apos;s role decides what it can reach.
        </p>
      </PageHeader>

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        onRowClick={(row) =>
          router.push(`/integration-management/integrations/${row.id}`)
        }
        emptyAction={listPrimaryAction}
      >
        <Card>
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={setSearchInput}
                placeholder="Search integrations..."
                className="w-full max-w-xs"
              />
            }
            primaryAction={listPrimaryAction}
            exportConfig={false}
          />
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <IntegrationFormDialog open={formOpen} onOpenChange={setFormOpen} />
    </div>
  );
}
