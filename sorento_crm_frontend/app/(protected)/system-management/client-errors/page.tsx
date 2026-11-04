'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  type ColumnDef,
  type PaginationState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { DataGrid } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { browserLabel, getClientErrors, type ClientErrorRow } from './services/clientErrorService';
import { ClientErrorDetailDrawer } from './ClientErrorDetailDrawer';

function localInput(offsetHours: number): string {
  const d = new Date(Date.now() - offsetHours * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const KIND_OPTIONS = [
  { value: 'true', label: 'Stale build (chunk load)' },
  { value: 'false', label: 'Other errors' },
];

export default function ClientErrorsPage() {
  const [dateFrom, setDateFrom] = useState(() => localInput(24 * 7));
  // Open-ended by default, so a refetch picks up reports that arrive after the page opened.
  const [dateTo, setDateTo] = useState('');
  const [kind, setKind] = useState('');
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [selected, setSelected] = useState<ClientErrorRow | null>(null);

  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery, dateFrom, dateTo, kind]);

  const filters = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      chunk_only: kind === '' ? undefined : kind === 'true',
      search: searchQuery || undefined,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
    }),
    [dateFrom, dateTo, kind, searchQuery, pagination],
  );

  const { data, isLoading, isFetching, isPlaceholderData, error, refetch } = useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['clientErrors', filters],
    queryFn: () => getClientErrors(filters),
  });

  const columns = useMemo<ColumnDef<ClientErrorRow>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="When" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 170,
        meta: { headerTitle: 'When' },
      },
      {
        accessorKey: 'user_name',
        header: ({ column }) => <DataGridColumnHeader title="User" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.user_name ?? ''}>
            {row.original.user_name ?? '-'}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'User' },
      },
      {
        accessorKey: 'boundary',
        header: ({ column }) => <DataGridColumnHeader title="Screen" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={row.original.boundary === 'global' ? 'destructive' : 'warning'}
            appearance="light"
            size="sm"
          >
            {row.original.boundary === 'global' ? 'App could not start' : 'Page error'}
          </Badge>
        ),
        size: 160,
        meta: { headerTitle: 'Screen' },
      },
      {
        accessorKey: 'message',
        header: ({ column }) => <DataGridColumnHeader title="Error" column={column} />,
        cell: ({ row }) => {
          const text = `${row.original.error_name ?? 'Error'}: ${row.original.message ?? ''}`;
          return (
            <span className="block truncate font-mono text-xs" title={text}>
              {row.original.is_chunk_error ? 'Stale build - ' : ''}
              {text}
            </span>
          );
        },
        size: 360,
        meta: { headerTitle: 'Error' },
      },
      {
        accessorKey: 'path',
        header: ({ column }) => <DataGridColumnHeader title="Page" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate font-mono text-xs" title={row.original.path ?? ''}>
            {row.original.path ?? '-'}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Page' },
      },
      {
        accessorKey: 'user_agent',
        header: ({ column }) => <DataGridColumnHeader title="Browser" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.user_agent ?? ''}>
            {browserLabel(row.original.user_agent)}
          </span>
        ),
        size: 100,
        meta: { headerTitle: 'Browser' },
      },
      {
        accessorKey: 'build_sha',
        header: ({ column }) => <DataGridColumnHeader title="Build" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs" title={row.original.build_sha ?? ''}>
            {(row.original.build_sha ?? '-').slice(0, 10)}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Build' },
      },
    ],
    [],
  );

  const rows = data?.data ?? [];
  const total = data?.total ?? 0;

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    manualPagination: true,
    manualSorting: true,
    enableSorting: false,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <Container>
      <PageHeader title="Client Errors" />

      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-3 p-5">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">From</Label>
            <Input
              type="datetime-local"
              value={dateFrom}
              data-testid="client-errors-from"
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-56"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">To</Label>
            <Input
              type="datetime-local"
              value={dateTo}
              data-testid="client-errors-to"
              onChange={(e) => setDateTo(e.target.value)}
              className="w-56"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Kind</Label>
            <SearchableSelect
              value={kind}
              onChange={(v) => setKind(v ?? '')}
              options={KIND_OPTIONS}
              placeholder="All errors"
              className="w-56"
              clearable
            />
          </div>
        </div>
      </Card>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        error={error}
        onRetry={() => void refetch()}
        isPlaceholderData={isPlaceholderData}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) => setSelected(row)}
      >
        <Card>
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={setSearchInput}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search error, page, reference, build..."
                data-testid="client-errors-search"
                className="w-full max-w-xs"
              />
            }
          />
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <ClientErrorDetailDrawer row={selected} onClose={() => setSelected(null)} />
    </Container>
  );
}
