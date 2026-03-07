'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
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
import { Search, X, ChevronRight, Download, Eye, Trash2, Plus, RefreshCw, FolderOpen, RotateCcw, FileArchive } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable, DataGridTableRowSelect, DataGridTableRowSelectAll } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useAttachments, useDeleteAttachment, useDownloadAttachment, useRestoreAttachment, useBulkRestoreAttachments, useDirectoryTree } from '../hooks/useAttachments';
import { getAttachmentPreviewUrl, resubmitAttachmentWebhook } from '../services/attachmentService';
import type { Attachment } from '../types/attachment.types';
import type { AttachmentDirectoryTreeNode } from '../services/directoryService';

function flattenDirectoryTree(nodes: AttachmentDirectoryTreeNode[], prefix = ''): { id: string; label: string }[] {
  return nodes.flatMap((n) => [
    { id: n.id, label: prefix ? `${prefix} / ${n.name}` : n.name },
    ...flattenDirectoryTree(n.children, prefix ? `${prefix} / ${n.name}` : n.name),
  ]);
}
import { formatDateTime } from '@/lib/helpers';
import AttachmentUploadDialog from './AttachmentUploadDialog';
import AttachmentBulkImportDialog from './AttachmentBulkImportDialog';
import AttachmentDeleteDialog from './attachment-delete-dialog';
import AttachmentBulkDeleteDialog from './AttachmentBulkDeleteDialog';

export default function AttachmentBrowser() {
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
  const [directoryId, setDirectoryId] = useState<string | null>(null);
  const [pendingResubmitIds, setPendingResubmitIds] = useState<Set<string>>(new Set());

  const queryClient = useQueryClient();
  const { data: directoryTree = [] } = useDirectoryTree();
  const isTrashView = directoryId === '__trash__';

  const { data, isLoading } = useAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    directory_id: isTrashView ? undefined : directoryId ?? undefined,
    is_deleted: isTrashView ? true : undefined,
  });

  const deleteMutation = useDeleteAttachment();
  const restoreMutation = useRestoreAttachment();
  const bulkRestoreMutation = useBulkRestoreAttachments();
  const downloadMutation = useDownloadAttachment();

  const [isResubmittingBulk, setIsResubmittingBulk] = useState(false);

  const handleResubmit = useCallback(
    async (attachment: Attachment) => {
      const { id } = attachment;
      setPendingResubmitIds((prev) => new Set(prev).add(id));
      try {
        await resubmitAttachmentWebhook(id);
        toast.success('Webhook resubmitted successfully');
        queryClient.invalidateQueries({ queryKey: ['attachments'] });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to resubmit webhook');
      } finally {
        setPendingResubmitIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [queryClient]
  );

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

  const handlePreview = async (attachmentId: string) => {
    try {
      const previewUrl = await getAttachmentPreviewUrl(attachmentId);
      if (previewUrl) {
        window.open(previewUrl, '_blank');
      }
    } catch {
      toast.error('Failed to open attachment preview');
    }
  };

  const handleDelete = (attachment: Attachment) => {
    setSelectedAttachment(attachment);
    setDeleteDialogOpen(true);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const selectedRowIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);
  const selectedDeletableIds = useMemo(() => {
    const rows = data?.data ?? [];
    if (isTrashView) return selectedRowIds;
    return selectedRowIds.filter((id) => {
      const row = rows.find((r) => r.id === id);
      return row && !row.is_deleted;
    });
  }, [selectedRowIds, data?.data, isTrashView]);

  const handleBulkResubmit = useCallback(async () => {
    const ids = selectedDeletableIds;
    if (ids.length === 0) return;
    setIsResubmittingBulk(true);
    setPendingResubmitIds((prev) => new Set(Array.from(prev).concat(ids)));
    let successCount = 0;
    let failCount = 0;
    for (const id of ids) {
      try {
        await resubmitAttachmentWebhook(id);
        successCount += 1;
      } catch {
        failCount += 1;
      } finally {
        setPendingResubmitIds((prev) => {
          const next = new Set(Array.from(prev));
          next.delete(id);
          return next;
        });
      }
    }
    setIsResubmittingBulk(false);
    queryClient.invalidateQueries({ queryKey: ['attachments'] });
    if (failCount === 0) {
      toast.success(`Webhook resubmitted for ${successCount} attachment(s)`);
      setRowSelection({});
    } else if (successCount === 0) {
      toast.error(`Failed to resubmit webhook for ${failCount} attachment(s)`);
    } else {
      toast.warning(`Resubmitted ${successCount}, failed ${failCount}`);
    }
  }, [selectedDeletableIds, queryClient]);

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
        cell: ({ row }) => row.original.uploaded_by_user?.name ?? row.original.uploaded_by_user?.email ?? '-',
        size: 150,
      },
      {
        accessorKey: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Upload at" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.uploaded_at)),
        size: 180,
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
                handlePreview(row.original.id);
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
            {isTrashView ? (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Restore"
                  onClick={(e) => {
                    e.stopPropagation();
                    restoreMutation.mutate(row.original.id);
                  }}
                  disabled={restoreMutation.isPending}
                >
                  <RotateCcw className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Permanently delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(row.original);
                  }}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="size-4 text-destructive" />
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Resubmit to n8n"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleResubmit(row.original);
                  }}
                  disabled={pendingResubmitIds.has(row.original.id) || row.original.is_deleted}
                >
                  <RefreshCw className={`size-4 ${pendingResubmitIds.has(row.original.id) ? 'animate-spin' : ''}`} />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Move to trash"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(row.original);
                  }}
                  disabled={deleteMutation.isPending || row.original.is_deleted}
                >
                  <Trash2 className="size-4" />
                </Button>
              </>
            )}
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </div>
        ),
        size: 220,
        enableHiding: false,
      },
    ],
    [
      isTrashView,
      deleteMutation.isPending,
      downloadMutation.isPending,
      handleResubmit,
      pendingResubmitIds,
      restoreMutation.isPending,
    ],
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
    enableRowSelection: (row: Row<Attachment>) => isTrashView || !row.original.is_deleted,
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={(row) => router.push(`/resource-management/attachments/${row.id}`)}
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
              <Select
                value={directoryId ?? '__all__'}
                onValueChange={(v) =>
                  setDirectoryId(v === '__all__' ? null : v === '__trash__' ? '__trash__' : v)
                }
              >
                <SelectTrigger className="w-[200px]">
                  <FolderOpen className="size-4 opacity-70 mr-1" />
                  <SelectValue placeholder="All folders" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All folders</SelectItem>
                  {flattenDirectoryTree(directoryTree).map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.label}
                    </SelectItem>
                  ))}
                  <SelectItem value="__trash__">
                    <span className="flex items-center gap-2">
                      <Trash2 className="size-4" />
                      Trash
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              {selectedDeletableIds.length > 0 && isTrashView && (
                <>
                  <Button
                    variant="outline"
                    onClick={() =>
                      bulkRestoreMutation.mutate(selectedDeletableIds, {
                        onSuccess: () => setRowSelection({}),
                      })
                    }
                    disabled={bulkRestoreMutation.isPending}
                  >
                    <RotateCcw className="size-4 mr-2" />
                    Restore selected ({selectedDeletableIds.length})
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setBulkDeleteDialogOpen(true)}
                    className="text-destructive border-destructive/50 hover:bg-destructive/10"
                  >
                    <Trash2 className="size-4 mr-2" />
                    Permanently delete ({selectedDeletableIds.length})
                  </Button>
                </>
              )}
              {selectedDeletableIds.length > 0 && !isTrashView && (
                <>
                  <Button
                    variant="outline"
                    onClick={handleBulkResubmit}
                    disabled={isResubmittingBulk}
                  >
                    <RefreshCw
                      className={`size-4 mr-2 ${isResubmittingBulk ? 'animate-spin' : ''}`}
                    />
                    Resubmit selected ({selectedDeletableIds.length})
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleBulkDelete}
                    className="text-destructive border-destructive/50 hover:bg-destructive/10"
                  >
                    <Trash2 className="size-4 mr-2" />
                    Delete selected ({selectedDeletableIds.length})
                  </Button>
                </>
              )}
              {!isTrashView && (
                <>
                  <Button onClick={() => setUploadDialogOpen(true)}>
                    <Plus className="size-4 mr-2" />
                    Create Attachment
                  </Button>
                  <Button variant="outline" onClick={() => setBulkImportDialogOpen(true)}>
                    <FileArchive className="size-4 mr-2" />
                    Bulk import (ZIP)
                  </Button>
                </>
              )}
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
      permanent={isTrashView}
    />

    <AttachmentBulkDeleteDialog
      open={bulkDeleteDialogOpen}
      onOpenChange={setBulkDeleteDialogOpen}
      attachmentIds={selectedDeletableIds}
      permanent={isTrashView}
      onSuccess={() => setRowSelection({})}
    />
    </>
  );
}
