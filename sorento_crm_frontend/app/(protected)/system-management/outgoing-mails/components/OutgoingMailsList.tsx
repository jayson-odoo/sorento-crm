'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
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
import { formatDateTime } from '@/lib/helpers';
import { Eye } from 'lucide-react';
import { useOutgoingMails } from '../hooks/useOutgoingMails';
import type { OutgoingMail } from '../types/outgoingMail.types';
import { getStatusBadgeVariant } from '@/lib/status-badge';

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

export default function OutgoingMailsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [status, setStatus] = useState<string>('__all__');
  const [query, setQuery] = useState<string>('');
  const [contentMail, setContentMail] = useState<OutgoingMail | null>(null);

  const { data, isLoading } = useOutgoingMails({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    status: status === '__all__' ? undefined : status,
    query: query || undefined,
  });

  const columns = useMemo<ColumnDef<OutgoingMail>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Queued At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.created_at)),
        size: 180,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'to_email',
        header: ({ column }) => <DataGridColumnHeader title="To" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.to_email || '-'}</span>
        ),
        size: 220,
      },
      {
        accessorKey: 'subject',
        header: ({ column }) => <DataGridColumnHeader title="Subject" column={column} />,
        cell: ({ row }) => (
          <span title={row.original.subject || ''} className="truncate block max-w-[420px]">
            {row.original.subject || '-'}
          </span>
        ),
        size: 420,
      },
      {
        id: 'content',
        header: ({ column }) => <DataGridColumnHeader title="Content" column={column} />,
        cell: ({ row }) => {
          const mail = row.original;
          const body = mail.body;
          const preview = body
            ? (body.startsWith('<') ? stripHtml(body) : body).slice(0, 80)
            : '';
          const hasContent = !!body;
          return (
            <div className="flex items-center gap-2 max-w-[280px]">
              <span className="truncate text-muted-foreground text-xs" title={preview}>
                {preview ? `${preview}${preview.length >= 80 ? '…' : ''}` : '-'}
              </span>
              {hasContent && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 h-8 w-8"
                  onClick={(e) => {
                    e.stopPropagation();
                    setContentMail(mail);
                  }}
                  title="View full content"
                >
                  <Eye className="size-4" />
                </Button>
              )}
            </div>
          );
        },
        size: 320,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={getStatusBadgeVariant(row.original.status)} appearance="ghost">
            {row.original.status}
          </Badge>
        ),
        size: 120,
      },
      {
        accessorKey: 'sent_at',
        header: ({ column }) => <DataGridColumnHeader title="Sent At" column={column} />,
        cell: ({ row }) =>
          row.original.sent_at ? formatDateTime(new Date(row.original.sent_at)) : '-',
        size: 180,
      },
      {
        accessorKey: 'error_message',
        header: ({ column }) => <DataGridColumnHeader title="Error" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground" title={row.original.error_message || ''}>
            {row.original.error_message || '-'}
          </span>
        ),
        size: 320,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  return (
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}>
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-48">
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All statuses</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="sent">Sent</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Input
              placeholder="Search by email or subject..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-72"
            />
          </div>
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
      <Dialog open={!!contentMail} onOpenChange={(open) => !open && setContentMail(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Email content</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto rounded border bg-muted/30 p-4 text-sm">
            {contentMail?.body?.startsWith('<') ? (
              <div
                className="prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: contentMail.body }}
              />
            ) : (
              <pre className="whitespace-pre-wrap break-words font-sans">{contentMail?.body ?? '-'}</pre>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </DataGrid>
  );
}

