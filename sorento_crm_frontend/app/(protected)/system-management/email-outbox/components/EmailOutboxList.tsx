'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { sanitizedHtml } from '@/lib/sanitize';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
import { Eye, RotateCcw, Ban, ChevronDown, Download } from 'lucide-react';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useBulkCancelEmailOutbox,
  useBulkRetryEmailOutbox,
  useCancelEmailOutboxRow,
  useEmailOutbox,
  useEmailOutboxRow,
  useRetryEmailOutboxRow,
} from '../hooks/useEmailOutbox';
import type { EmailOutboxRow } from '../types/emailOutbox.types';

export default function EmailOutboxList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [status, setStatus] = useState<string>('__all__');
  const {
    value: queryInput,
    setValue: setQueryInput,
    debouncedValue: query,
    isSettling: querySettling,
  } = useDebouncedSearch();
  const [detailId, setDetailId] = useState<string | null>(null);
  const [cancelRow, setCancelRow] = useState<EmailOutboxRow | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // A search brings the reader back to page 0 to see the matches.
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [query]);

  const { data, isLoading, isPlaceholderData, refetch, isFetching } = useEmailOutbox({
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
          <Badge status={row.original.status}>
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
                title="View" aria-label="View"
                onClick={() => setDetailId(r.id)}
              >
                <Eye className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Retry" aria-label="Retry"
                disabled={!canRetry || retryMut.isPending}
                onClick={() => retryMut.mutate(r.id)}
              >
                <RotateCcw className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Cancel" aria-label="Cancel"
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
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ columnsVisibility: true, width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            bulkActionsSlot={({ openExport }) => (
              // Consolidated "Action ▾" dropdown in the base toolbar's bulk strip
              // (reuses DataGridListToolbar; Export lives inside via openExport).
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5" disabled={bulkPending}>
                    Action
                    <ChevronDown className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    disabled={bulkPending}
                    onClick={() => bulkRetryMut.mutate(selectedIds, { onSuccess: clearSelection })}
                  >
                    <RotateCcw className="size-4 me-2" /> Retry selected
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={bulkPending}
                    className="text-destructive focus:text-destructive"
                    onClick={() => bulkCancelMut.mutate(selectedIds, { onSuccess: clearSelection })}
                  >
                    <Ban className="size-4 me-2" /> Cancel selected
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={openExport}>
                    <Download className="size-4 me-2" /> Export
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            searchSlot={
              <ListSearchInput
                value={queryInput}
                onChange={setQueryInput}
                isSettling={isSearchInFlight(querySettling, isFetching, query)}
                placeholder="Search recipient or subject..."
                className="w-72"
              />
            }
            filters={{
              kind: 'custom',
              active: status !== '__all__',
              activeCount: status !== '__all__' ? 1 : 0,
              content: (
                <div className="space-y-3">
                  <SearchableSelect
                    value={status}
                    onChange={setStatus}
                    options={[
                      { value: '__all__', label: 'All statuses' },
                      { value: 'pending', label: 'Pending' },
                      { value: 'sending', label: 'Sending' },
                      { value: 'sent', label: 'Sent' },
                      { value: 'failed', label: 'Failed' },
                      { value: 'cancelled', label: 'Cancelled' },
                      { value: 'deferred', label: 'Deferred' },
                    ]}
                    placeholder="Status"
                  />
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
          <DataGridTable />
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
                    <Badge status={detail.status}>
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
                      dangerouslySetInnerHTML={sanitizedHtml(detail.body_html)}
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
