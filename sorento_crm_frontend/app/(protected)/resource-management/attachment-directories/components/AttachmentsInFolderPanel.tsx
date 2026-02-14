'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDraggable } from '@dnd-kit/core';
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
import { Search, X, Download, Eye, Trash2, Plus, RefreshCw, GripVertical, FileArchive } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable, DataGridTableRowSelect, DataGridTableRowSelectAll } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useAttachments,
  useDeleteAttachment,
  useDownloadAttachment,
  useResubmitAttachmentWebhook,
} from '../../attachments/hooks/useAttachments';
import type { Attachment } from '../../attachments/types/attachment.types';
import { formatDate } from '@/lib/helpers';
import AttachmentUploadDialog from '../../attachments/components/AttachmentUploadDialog';
import AttachmentBulkImportDialog from '../../attachments/components/AttachmentBulkImportDialog';
import AttachmentDeleteDialog from '../../attachments/components/attachment-delete-dialog';
import AttachmentBulkDeleteDialog from '../../attachments/components/AttachmentBulkDeleteDialog';

const DRAG_ID_PREFIX = 'attachment-';

function AttachmentDragHandle({
  attachment,
  currentDirectoryId,
}: {
  attachment: Attachment;
  currentDirectoryId: string | null;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `${DRAG_ID_PREFIX}${attachment.id}`,
    data: {
      type: 'attachment',
      attachmentId: attachment.id,
      attachmentName: attachment.original_filename,
      currentDirectoryId: currentDirectoryId ?? null,
    },
  });
  return (
    <Button
      ref={setNodeRef}
      variant="ghost"
      size="icon"
      className="size-7 cursor-grab active:cursor-grabbing touch-none"
      aria-label="Drag to move to folder"
      style={{ opacity: isDragging ? 0.5 : 1 }}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="size-4 text-muted-foreground" />
    </Button>
  );
}

interface AttachmentsInFolderPanelProps {
  directoryId: string | null;
  directoryName?: string | null;
}

export default function AttachmentsInFolderPanel({
  directoryId,
  directoryName,
}: AttachmentsInFolderPanelProps) {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'uploaded_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [bulkImportDialogOpen, setBulkImportDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [selectedAttachment, setSelectedAttachment] = useState<Attachment | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading } = useAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    directory_id: directoryId ?? undefined,
  });

  const deleteMutation = useDeleteAttachment();
  const downloadMutation = useDownloadAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();

  const handleDownload = async (attachment: Attachment) => {
    try {
      const blob = await downloadMutation.mutateAsync(attachment.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // Error handled by mutation toast
    }
  };

  const selectedRowIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const selectedDeletableIds = useMemo(() => {
    const rows = data?.data ?? [];
    return selectedRowIds.filter((id) => {
      const row = rows.find((r) => r.id === id);
      return row && !row.is_deleted;
    });
  }, [selectedRowIds, data?.data]);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const columns = useMemo<ColumnDef<Attachment>[]>(
    () => [
      {
        id: 'drag',
        header: () => null,
        cell: ({ row }) => (
          <AttachmentDragHandle
            attachment={row.original}
            currentDirectoryId={directoryId}
          />
        ),
        size: 40,
        enableSorting: false,
        enableResizing: false,
      },
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
        cell: ({ row }) =>
          row.original.file_size_bytes ? formatFileSize(row.original.file_size_bytes) : '-',
        size: 100,
      },
      {
        accessorKey: 'uploaded_by_user.name',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded By" column={column} />,
        cell: ({ row }) => row.original.uploaded_by_user?.name ?? row.original.uploaded_by_user?.email ?? '-',
        size: 150,
      },
      {
        accessorKey: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Upload Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.uploaded_at)),
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
        cell: ({ row }) => (
          <Badge
            variant={row.original.is_deleted ? 'destructive' : 'success'}
            appearance="ghost"
          >
            <BadgeDot />
            {row.original.is_deleted ? 'Deleted' : 'Active'}
          </Badge>
        ),
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
                if (row.original.file_path) window.open(row.original.file_path, '_blank');
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
                resubmitMutation.mutate(row.original.id);
              }}
              disabled={resubmitMutation.isPending || row.original.is_deleted}
            >
              <RefreshCw
                className={`size-4 ${resubmitMutation.isPending ? 'animate-spin' : ''}`}
              />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedAttachment(row.original);
                setDeleteDialogOpen(true);
              }}
              disabled={deleteMutation.isPending || row.original.is_deleted}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
        size: 220,
        enableHiding: false,
      },
    ],
    [directoryId, deleteMutation.isPending, downloadMutation.isPending, resubmitMutation]
  );

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
    columnResizeMode: 'onChange',
  });

  const heading =
    directoryId == null
      ? 'All attachments'
      : directoryName
        ? `Attachments in "${directoryName}"`
        : 'Attachments in this folder';

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={(row) => {
          const params = new URLSearchParams({ from: 'directories' });
          if (directoryId) params.set('directoryId', directoryId);
          router.push(`/resource-management/attachments/${row.id}?${params.toString()}`);
        }}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div className="flex items-center gap-2">
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
              <span className="text-sm text-muted-foreground">{heading}</span>
            </div>
            <div className="flex items-center gap-2">
              {selectedDeletableIds.length > 0 && (
                <Button
                  variant="outline"
                  onClick={() => setBulkDeleteDialogOpen(true)}
                  className="text-destructive border-destructive/50 hover:bg-destructive/10"
                >
                  <Trash2 className="size-4 mr-2" />
                  Delete selected ({selectedDeletableIds.length})
                </Button>
              )}
              <Button onClick={() => setUploadDialogOpen(true)}>
                <Plus className="size-4 mr-2" />
                Upload
              </Button>
              <Button variant="outline" onClick={() => setBulkImportDialogOpen(true)}>
                <FileArchive className="size-4 mr-2" />
                Bulk import (ZIP)
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
        defaultDirectoryId={directoryId}
        onSuccess={() => {}}
      />
      <AttachmentBulkImportDialog
        open={bulkImportDialogOpen}
        onOpenChange={setBulkImportDialogOpen}
        defaultParentDirectoryId={directoryId}
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
