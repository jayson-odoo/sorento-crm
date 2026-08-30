'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { MessageCircle, MessageCircleOff, Search, TriangleAlert, X } from 'lucide-react';
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
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useRespondContactOutboundMutations,
  useRespondContactsOutbound,
} from '../hooks/useRespondContactsOutbound';
import type {
  OutboundFilter,
  RespondContactOutboundRow,
} from '../types/respondContactOutbound.types';

/** Which confirmation is open, if any. Disabling always confirms. */
type PendingAction =
  | { kind: 'bulk-disable'; count: number }
  | { kind: 'disable-all'; count: number }
  | { kind: 'enable-all'; count: number }
  | null;

export default function RespondContactsOutboundList() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [outbound, setOutbound] = useState<OutboundFilter>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [pending, setPending] = useState<PendingAction>(null);

  const { data, isLoading, isFetching, isError, error, refetch } = useRespondContactsOutbound({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    searchQuery: searchQuery || undefined,
    outbound,
  });

  const { setOne, setBulk } = useRespondContactOutboundMutations();

  const rows = useMemo(() => data?.data ?? [], [data]);
  const total = data?.pagination?.total ?? 0;
  const counts = data?.counts ?? { enabled: 0, disabled: 0, total: 0 };
  const selectedIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const busy = setOne.isPending || setBulk.isPending;

  const clearSelection = () => setRowSelection({});

  const columns = useMemo<ColumnDef<RespondContactOutboundRow>[]>(
    () => [
      buildSelectColumn<RespondContactOutboundRow>(),
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate font-medium"
            title={row.original.name ?? undefined}
          >
            {row.original.name || 'Unnamed contact'}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'phone_number',
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate tabular-nums"
            title={row.original.phone_number ?? undefined}
          >
            {row.original.phone_number || '-'}
          </span>
        ),
        size: 160,
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'respond_io_id',
        header: ({ column }) => (
          <DataGridColumnHeader title="Respond.io ID" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="block truncate text-muted-foreground"
            title={row.original.respond_io_id ?? undefined}
          >
            {row.original.respond_io_id || '-'}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Respond.io ID', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'outbound_enabled',
        header: ({ column }) => (
          <DataGridColumnHeader title="Outbound" column={column} />
        ),
        cell: ({ row }) => (
          <Badge variant={row.original.outbound_enabled ? 'success' : 'destructive'}>
            {row.original.outbound_enabled ? 'Enabled' : 'Disabled'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Outbound', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'toggle',
        header: () => <span className="sr-only">Toggle outbound</span>,
        cell: ({ row }) => (
          <Switch
            checked={row.original.outbound_enabled}
            disabled={busy}
            aria-label={
              row.original.outbound_enabled
                ? `Disable outbound for ${row.original.name || row.original.phone_number || 'this contact'}`
                : `Enable outbound for ${row.original.name || row.original.phone_number || 'this contact'}`
            }
            onCheckedChange={(checked) =>
              setOne.mutate({ contactId: row.original.id, enabled: checked })
            }
          />
        ),
        size: 80,
        enableHiding: false,
      },
    ],
    [busy, setOne],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    onPaginationChange: setPagination,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    manualPagination: true,
    manualFiltering: true,
    // The server orders silenced-first, then by name. Nothing here re-sorts, so
    // do not offer a header control that would do nothing.
    enableSorting: false,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const runBulk = (enabled: boolean, ids: string[]) =>
    setBulk.mutate({ enabled, contactIds: ids }, { onSuccess: clearSelection });

  const confirmPending = () => {
    if (!pending) return;
    if (pending.kind === 'bulk-disable') {
      runBulk(false, selectedIds);
    } else {
      setBulk.mutate(
        { enabled: pending.kind === 'enable-all', all: true },
        { onSuccess: clearSelection },
      );
    }
    setPending(null);
  };

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={busy || counts.disabled === 0}
        onClick={() => setPending({ kind: 'enable-all', count: counts.disabled })}
      >
        <MessageCircle className="size-4" />
        Enable all
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 text-destructive border-destructive/50 hover:bg-destructive/10"
        disabled={busy || counts.enabled === 0}
        onClick={() => setPending({ kind: 'disable-all', count: counts.enabled })}
      >
        <MessageCircleOff className="size-4" />
        Disable all
      </Button>
    </>
  );

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="block">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-6">
              <Summary label="Can be messaged" value={counts.enabled} tone="ok" />
              <Summary label="Silenced" value={counts.disabled} tone="off" />
              <Summary label="Total contacts" value={counts.total} tone="muted" />
            </div>
            {counts.disabled > 0 && (
              <Badge variant="destructive" className="w-fit">
                {counts.disabled === counts.total && counts.total > 0
                  ? 'All outbound messaging is off'
                  : `${counts.disabled} contact(s) will receive nothing`}
              </Badge>
            )}
          </div>
        </CardHeader>
      </Card>

      {isError && (
        <Alert variant="destructive" appearance="light">
          <AlertIcon>
            <TriangleAlert />
          </AlertIcon>
          <AlertTitle>
            {(error as Error)?.message || 'Failed to load Respond contacts'}
          </AlertTitle>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </Alert>
      )}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        emptyMessage={
          searchQuery || outbound !== 'all'
            ? 'No contact matches this search.'
            : 'No Respond.io contacts yet. They appear here once a contact messages us or is synced from Respond.io.'
        }
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyAction={listPrimaryAction}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                  <Input
                    placeholder="Search name, phone or Respond.io ID..."
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setPagination((p) => ({ ...p, pageIndex: 0 }));
                    }}
                    className="ps-9 w-72"
                  />
                  {searchQuery && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: outbound !== 'all',
                activeCount: outbound !== 'all' ? 1 : 0,
                content: (
                  <div className="space-y-1.5">
                    <Label>Outbound</Label>
                    <SearchableSelect
                      value={outbound}
                      onChange={(v) => {
                        setOutbound(v as OutboundFilter);
                        setPagination((p) => ({ ...p, pageIndex: 0 }));
                      }}
                      options={[
                        { value: 'all', label: 'All contacts' },
                        { value: 'enabled', label: 'Enabled' },
                        { value: 'disabled', label: 'Disabled' },
                      ]}
                      placeholder="Outbound"
                      triggerClassName="w-full"
                    />
                  </div>
                ),
              }}
              exportConfig={{ filename: 'respond_contacts_outbound_export.xlsx' }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
              // The kill switch stays VISIBLE. Feeding it through
              // `secondaryActions` would collapse it into an unlabelled
              // "Actions" overflow at two entries, which is the wrong place for
              // the control this page exists to offer.
              primaryAction={listPrimaryAction}
              bulkActions={[
                {
                  key: 'bulk-enable',
                  label: `Enable (${selectedIds.length})`,
                  icon: MessageCircle,
                  disabled: busy,
                  onClick: () => runBulk(true, selectedIds),
                },
                {
                  key: 'bulk-disable',
                  label: `Disable (${selectedIds.length})`,
                  icon: MessageCircleOff,
                  destructive: true,
                  disabled: busy,
                  onClick: () =>
                    setPending({ kind: 'bulk-disable', count: selectedIds.length }),
                },
              ]}
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

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending?.kind === 'enable-all'
                ? 'Enable outbound messaging for every contact'
                : pending?.kind === 'disable-all'
                  ? 'Disable outbound messaging for EVERY contact'
                  : 'Disable outbound messaging'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.kind === 'enable-all' &&
                `${pending.count} silenced contact(s) will be able to receive WhatsApp messages again, including any you muted on purpose.`}
              {pending?.kind === 'disable-all' &&
                `No customer will receive any WhatsApp message until outbound is switched back on. This silences all ${pending.count} contact(s) that can currently be messaged.`}
              {pending?.kind === 'bulk-disable' &&
                `${pending.count} selected contact(s) will receive no WhatsApp messages until you switch them back on.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmPending}
              disabled={busy}
              className={
                pending?.kind === 'enable-all'
                  ? undefined
                  : 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
              }
            >
              {pending?.kind === 'enable-all'
                ? 'Enable all'
                : pending?.kind === 'disable-all'
                  ? 'Disable all contacts'
                  : 'Disable'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Summary({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'ok' | 'off' | 'muted';
}) {
  const valueClass =
    tone === 'ok'
      ? 'text-green-600'
      : tone === 'off'
        ? 'text-destructive'
        : 'text-foreground';
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
    </div>
  );
}
