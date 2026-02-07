'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  Row,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X, ChevronRight, Download, Eye, Trash2, Plus, RefreshCw } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable, DataGridTableRowSelect, DataGridTableRowSelectAll } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useAttachments, useDeleteAttachment, useDownloadAttachment, useResubmitAttachmentWebhook } from '../hooks/useAttachments';
import type { Attachment } from '../types/attachment.types';
import { formatDate } from '@/lib/helpers';
import AttachmentUploadDialog from './AttachmentUploadDialog';
import AttachmentDeleteDialog from './attachment-delete-dialog';
import AttachmentBulkDeleteDialog from './AttachmentBulkDeleteDialog';

export default function AttachmentBrowser() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'uploaded_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [selectedAttachment, setSelectedAttachment] = useState<Attachment | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading } = useAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const deleteMutation = useDeleteAttachment();
  const downloadMutation = useDownloadAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();

  const handleDownload = async (attachment: Attachment) => {
    try {
      const blob = await downloadMutation.mutateAsync(attachment.id);
      
      // Create a blob URL and trigger download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      // Error is handled by the mutation hook (toast)
    }
  };

  const handleDelete = (attachment: Attachment) => {
    setSelectedAttachment(attachment);
    setDeleteDialogOpen(true);
  };

  const handleResubmit = async (attachment: Attachment) => {
    // Prevent multiple simultaneous resubmits for the same attachment
    if (resubmitMutation.isPending) {
      return;
    }
    try {
      await resubmitMutation.mutateAsync(attachment.id);
    } catch (error) {
      // Error is handled by the mutation hook (toast)
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const selectedRowIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const selectedDeletableIds = useMemo(() => {
    const rows = data?.data ?? [];
    return selectedRowIds.filter((id) => {
      const row = rows.find((r) => r.id === id);
      return row && !row.is_deleted;
    });
  }, [selectedRowIds, data?.data]);

  const columns = useMemo<ColumnDef<Attachment>[]>(
    () => [
      {
        id: 'select',
        header: () => <DataGridTableRowSelectAll />,
        cell: ({ row }) => <DataGridTableRowSelect row={row} />,
        size: 40,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="size-5" /> },
        enableResizing: false,
      },
      {
        accessorKey: 'original_filename',
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'mime_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => {
          const mimeType = row.original.mime_type || '-';
          // Truncate long MIME types and show tooltip on hover
          const displayType = mimeType.length > 30 ? mimeType.substring(0, 30) + '...' : mimeType;
          return (
            <span title={mimeType} className="block truncate">
              {displayType}
            </span>
          );
        },
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'attachment_type',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Type" column={column} />,
        cell: ({ row }) => row.original.attachment_type?.type_name ?? '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'file_size_bytes',
        header: ({ column }) => <DataGridColumnHeader title="Size" column={column} />,
        cell: ({ row }) => row.original.file_size_bytes ? formatFileSize(row.original.file_size_bytes) : '-',
        size: 100,
      },
      {
        accessorKey: 'uploaded_by_user.name',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded By" column={column} />,
        cell: ({ row }) => row.original.uploaded_by_user?.name || '-',
        size: 150,
      },
      {
        accessorKey: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Upload Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.uploaded_at)),
        size: 150,
      },
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Entity" column={column} />,
        size: 120,
      },
      {
        accessorKey: 'entity_name',
        header: ({ column }) => <DataGridColumnHeader title="Entity Name" column={column} />,
        size: 150,
      },
      {
        accessorKey: 'virus_status',
        header: ({ column }) => <DataGridColumnHeader title="Virus Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.virus_status || 'unknown';
          const variants: Record<string, 'success' | 'warning' | 'destructive' | 'secondary'> = {
            clean: 'success',
            scanning: 'warning',
            infected: 'destructive',
            unknown: 'secondary',
          };
          return (
            <Badge variant={variants[status] || 'secondary'} appearance="ghost">
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'is_deleted',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const isDeleted = row.original.is_deleted;
          return (
            <Badge
              variant={isDeleted ? 'destructive' : 'success'}
              appearance="ghost"
            >
              <BadgeDot />
              {isDeleted ? 'Deleted' : 'Active'}
            </Badge>
          );
        },
        size: 100,
      },
      {
        accessorKey: 'actions',
        header: 'Actions',
        cell: ({ row }) => (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <Button 
              variant="ghost" 
              size="sm" 
              title="Preview"
              onClick={(e) => {
                e.stopPropagation();
                if (row.original.file_path) {
                  window.open(row.original.file_path, '_blank');
                }
              }}
            >
              <Eye className="size-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              title="Download"
              onClick={(e) => {
                e.stopPropagation();
                handleDownload(row.original);
              }}
              disabled={downloadMutation.isPending}
            >
              <Download className="size-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              title="Resubmit to n8n"
              onClick={(e) => {
                e.stopPropagation();
                handleResubmit(row.original);
              }}
              disabled={resubmitMutation.isPending || row.original.is_deleted}
            >
              <RefreshCw className={`size-4 ${resubmitMutation.isPending ? 'animate-spin' : ''}`} />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(row.original);
              }}
              disabled={deleteMutation.isPending || row.original.is_deleted}
            >
              <Trash2 className="size-4" />
            </Button>
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </div>
        ),
        size: 220,
        enableHiding: false,
      },
    ],
    [deleteMutation.isPending, downloadMutation.isPending, resubmitMutation.isPending],
  );

  const handleBulkDelete = () => {
    if (selectedDeletableIds.length > 0) {
      setBulkDeleteDialogOpen(true);
    }
  };

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    enableRowSelection: (row: Row<Attachment>) => !row.original.is_deleted,
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={(row) => router.push(`/resource-management/attachments/${row.id}`)}
      >
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search attachments..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="ps-9 w-64"
              />
              {searchQuery && (
                <Button
                  mode="icon"
                  variant="dim"
                  className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => setSearchQuery('')}
                >
                  <X />
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2">
              {selectedDeletableIds.length > 0 && (
                <Button
                  variant="outline"
                  onClick={handleBulkDelete}
                  className="text-destructive border-destructive/50 hover:bg-destructive/10"
                >
                  <Trash2 className="size-4 mr-2" />
                  Delete selected ({selectedDeletableIds.length})
                </Button>
              )}
              <Button onClick={() => setUploadDialogOpen(true)}>
                <Plus className="size-4 mr-2" />
                Create Attachment
              </Button>
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
    </DataGrid>

    <AttachmentUploadDialog
      open={uploadDialogOpen}
      onOpenChange={setUploadDialogOpen}
      onSuccess={() => {
        // Refresh the attachments list
        // The query will automatically refetch due to query invalidation in the mutation
      }}
    />

    <AttachmentDeleteDialog
      open={deleteDialogOpen}
      onOpenChange={setDeleteDialogOpen}
      attachment={selectedAttachment}
    />

    <AttachmentBulkDeleteDialog
      open={bulkDeleteDialogOpen}
      onOpenChange={setBulkDeleteDialogOpen}
      attachmentIds={selectedDeletableIds}
      onSuccess={() => setRowSelection({})}
    />
    </>
  );
}
