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
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Eye, RotateCcw, Ban, Search, X } from 'lucide-react';
import {
  useBulkCancelEmailOutbox,
  useBulkRetryEmailOutbox,
  useCancelEmailOutboxRow,
  useEmailOutbox,
  useEmailOutboxRow,
  useRetryEmailOutboxRow,
} from '../hooks/useEmailOutbox';
import type { EmailOutboxRow } from '../types/emailOutbox.types';
import { getStatusBadgeVariant } from '@/lib/status-badge';

export default function EmailOutboxList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [status, setStatus] = useState<string>('__all__');
  const [query, setQuery] = useState<string>('');
  const [detailId, setDetailId] = useState<string | null>(null);
  const [cancelRow, setCancelRow] = useState<EmailOutboxRow | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = useEmailOutbox({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    status: status === '__all__' ? undefined : status,
    query: query || undefined,
  });

  const detailQuery = useEmailOutboxRow(detailId);
  const retryMut = useRetryEmailOutboxRow();
  const cancelMut = useCancelEmailOutboxRow();
  const bulkRetryMut = useBulkRetryEmailOutbox();
  const bulkCancelMut = useBulkCancelEmailOutbox();
  const selectedIds = Object.keys(rowSelection);
  const bulkPending = bulkRetryMut.isPending || bulkCancelMut.isPending;
  const clearSelection = () => setRowSelection({});

  const columns = useMemo<ColumnDef<EmailOutboxRow>[]>(
    () => [
      buildSelectColumn<EmailOutboxRow>(),
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Queued At" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 170,
        meta: { headerTitle: 'Queued At', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'event_key',
        header: ({ column }) => <DataGridColumnHeader title="Event" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs" title={row.original.event_key}>
            {row.original.event_key}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Event' },
      },
      {
        accessorKey: 'recipient_email',
        header: ({ column }) => <DataGridColumnHeader title="To" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.recipient_email || '-'}</span>
        ),
        size: 220,
        meta: { headerTitle: 'To' },
      },
      {
        accessorKey: 'subject',
        header: ({ column }) => <DataGridColumnHeader title="Subject" column={column} />,
        cell: ({ row }) => (
          <span title={row.original.subject || ''} className="truncate block max-w-[360px]">
            {row.original.subject || '-'}
          </span>
        ),
        size: 360,
        meta: { headerTitle: 'Subject' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={getStatusBadgeVariant(row.original.status)} appearance="ghost">
            {row.original.status}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'priority',
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        cell: ({ row }) => row.original.priority,
        size: 90,
        meta: { headerTitle: 'Priority' },
      },
      {
        accessorKey: 'attempt_count',
        header: ({ column }) => <DataGridColumnHeader title="Attempts" column={column} />,
        cell: ({ row }) => `${row.original.attempt_count} / ${row.original.max_attempts}`,
        size: 100,
        meta: { headerTitle: 'Attempts' },
      },
      {
        accessorKey: 'scheduled_for',
        header: ({ column }) => <DataGridColumnHeader title="Scheduled" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.scheduled_for),
        size: 170,
        meta: { headerTitle: 'Scheduled' },
      },
      {
        accessorKey: 'sent_at',
        header: ({ column }) => <DataGridColumnHeader title="Sent At" column={column} />,
        cell: ({ row }) =>
          row.original.sent_at ? formatDateTimeInMalaysia(row.original.sent_at) : '-',
        size: 170,
        meta: { headerTitle: 'Sent At' },
      },
      {
        accessorKey: 'error_message',
        header: ({ column }) => <DataGridColumnHeader title="Error" column={column} />,
        cell: ({ row }) => (
          <span
            className="text-xs text-muted-foreground truncate block max-w-[280px]"
            title={row.original.error_message || ''}
          >
            {row.original.error_message || '-'}
          </span>
        ),
        size: 280,
        meta: { headerTitle: 'Error' },
      },
      {
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => {
          const r = row.original;
          const canRetry = r.status === 'failed' || r.status === 'cancelled';
          const canCancel = r.status === 'pending' || r.status === 'deferred';
          return (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="View"
                onClick={() => setDetailId(r.id)}
              >
                <Eye className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Retry"
                disabled={!canRetry || retryMut.isPending}
                onClick={() => retryMut.mutate(r.id)}
              >
                <RotateCcw className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Cancel"
                disabled={!canCancel}
                onClick={() => setCancelRow(r)}
              >
                <Ban className="size-4" />
              </Button>
            </div>
          );
        },
        size: 140,
        enableHiding: false,
      },
    ],
    [retryMut],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  const detail = detailQuery.data;

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      tableLayout={{ columnsVisibility: true, width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block">
          {selectedIds.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
              <span className="text-sm font-medium">{selectedIds.length} selected</span>
              <div className="ms-auto flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={bulkPending}
                  onClick={() =>
                    bulkRetryMut.mutate(selectedIds, { onSuccess: clearSelection })
                  }
                >
                  <RotateCcw className="size-4" /> Retry selected
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  disabled={bulkPending}
                  onClick={() =>
                    bulkCancelMut.mutate(selectedIds, { onSuccess: clearSelection })
                  }
                >
                  <Ban className="size-4" /> Cancel selected
                </Button>
                <Button variant="dim" size="sm" disabled={bulkPending} onClick={clearSelection}>
                  Clear
                </Button>
              </div>
            </div>
          )}
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search recipient or subject..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="ps-9 w-72"
                />
                {query && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: status !== '__all__',
              activeCount: status !== '__all__' ? 1 : 0,
              content: (
                <div className="space-y-3">
                  <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger>
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">All statuses</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="sending">Sending</SelectItem>
                      <SelectItem value="sent">Sent</SelectItem>
                      <SelectItem value="failed">Failed</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
                      <SelectItem value="deferred">Deferred</SelectItem>
                    </SelectContent>
                  </Select>
                  {status !== '__all__' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => setStatus('__all__')}
                    >
                      Clear filters
                    </Button>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'email_outbox_export.xlsx' }}
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
      <Dialog open={!!detailId} onOpenChange={(open) => !open && setDetailId(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Outbox row detail</DialogTitle>
          </DialogHeader>
          {detail ? (
            <div className="flex-1 overflow-auto space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-muted-foreground">Event</div>
                  <div className="font-mono">{detail.event_key}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Status</div>
                  <div>
                    <Badge variant={getStatusBadgeVariant(detail.status)} appearance="ghost">
                      {detail.status}
                    </Badge>
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground">Recipient</div>
                  <div className="font-mono">{detail.recipient_email}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Priority</div>
                  <div>{detail.priority}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Attempts</div>
                  <div>
                    {detail.attempt_count} / {detail.max_attempts}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground">Scheduled</div>
                  <div>{formatDateTimeInMalaysia(detail.scheduled_for)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Sent</div>
                  <div>{detail.sent_at ? formatDateTimeInMalaysia(detail.sent_at) : '-'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Coalesce key</div>
                  <div className="font-mono text-xs break-all">{detail.coalesce_key || '-'}</div>
                </div>
              </div>
              {detail.error_message && (
                <div className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm">
                  <div className="font-medium text-destructive mb-1">Error</div>
                  <pre className="whitespace-pre-wrap text-xs">{detail.error_message}</pre>
                </div>
              )}
              <div>
                <div className="text-muted-foreground text-sm mb-1">Subject</div>
                <div className="font-medium">{detail.subject}</div>
              </div>
              <div>
                <div className="text-muted-foreground text-sm mb-1">Body (HTML preview)</div>
                <div className="rounded border bg-muted/30 p-3 text-sm">
                  {detail.body_html ? (
                    <div
                      className="prose prose-sm dark:prose-invert max-w-none"
                      dangerouslySetInnerHTML={{ __html: detail.body_html }}
                    />
                  ) : (
                    <pre className="whitespace-pre-wrap">{detail.body_text || '-'}</pre>
                  )}
                </div>
              </div>
              {detail.metadata && (
                <div>
                  <div className="text-muted-foreground text-sm mb-1">Metadata</div>
                  <pre className="rounded border bg-muted/30 p-3 text-xs overflow-auto">
                    {JSON.stringify(detail.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <Skeleton className="h-32" />
          )}
        </DialogContent>
      </Dialog>
      <AlertDialog open={!!cancelRow} onOpenChange={(open) => !open && setCancelRow(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel outbox row?</AlertDialogTitle>
            <AlertDialogDescription>
              This row will be marked cancelled and will not be sent. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep pending</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (cancelRow) {
                  cancelMut.mutate(cancelRow.id);
                  setCancelRow(null);
                }
              }}
            >
              Cancel send
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DataGrid>
  );
}
