'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
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
import {
  Search,
  X,
  Download,
  Eye,
  Trash2,
  Plus,
  RefreshCw,
  GripVertical,
  FileArchive,
  RotateCcw,
  Shield,
  Pencil,
} from 'lucide-react';
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
  useRestoreAttachment,
  useBulkRestoreAttachments,
  useRestoreDirectory,
  useUpdateAttachment,
} from '../../attachments/hooks/useAttachments';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { getAttachmentPreviewUrl, resubmitAttachmentWebhook } from '../../attachments/services/attachmentService';
import type { Attachment } from '../../attachments/types/attachment.types';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import AttachmentUploadDialog from '../../attachments/components/AttachmentUploadDialog';
import AttachmentBulkImportDialog from '../../attachments/components/AttachmentBulkImportDialog';
import AttachmentDeleteDialog from '../../attachments/components/attachment-delete-dialog';
import AttachmentBulkDeleteDialog from '../../attachments/components/AttachmentBulkDeleteDialog';
import AttachmentDetailModal from '../../attachments/components/AttachmentDetailModal';
import { TRASH_VIEW_ID, TRASH_FOLDER_PREFIX, FOLDER_ALL_ID } from '../constants';

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
  /** Called when user restores a folder from trash; parent can switch view (e.g. to TRASH_VIEW_ID) */
  onRestoreFolder?: () => void;
  /** @deprecated Folders are only shown in the left pane; kept for parent compatibility */
  onSelectFolder?: (id: string) => void;
  /** Bulk adjust access levels for the selected attachment rows */
  onBulkAdjustAccessLevels?: (attachmentIds: string[]) => void;
}

export default function AttachmentsInFolderPanel({
  directoryId,
  onRestoreFolder,
  onBulkAdjustAccessLevels,
}: AttachmentsInFolderPanelProps) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'uploaded_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [bulkImportDialogOpen, setBulkImportDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [viewAttachmentId, setViewAttachmentId] = useState<string | null>(null);
  const [selectedAttachment, setSelectedAttachment] = useState<Attachment | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [pendingResubmitIds, setPendingResubmitIds] = useState<Set<string>>(new Set());

  const queryClient = useQueryClient();
  const isTrashView =
    directoryId === TRASH_VIEW_ID || (directoryId ?? '').startsWith(TRASH_FOLDER_PREFIX);
  const trashFolderId =
    directoryId?.startsWith(TRASH_FOLDER_PREFIX) ? directoryId.slice(TRASH_FOLDER_PREFIX.length) : null;

  // When "All attachments" is selected (directoryId null or FOLDER_ALL_ID), omit directory_id so the API
  // returns all attachments including those with no folder (e.g. stock list uploads).
  const effectiveDirectoryId =
    directoryId === null || directoryId === FOLDER_ALL_ID ? undefined : directoryId;
  const { data, isLoading } = useAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    directory_id: trashFolderId ?? (isTrashView ? undefined : effectiveDirectoryId),
    is_deleted: isTrashView ? true : undefined,
  });

  const deleteMutation = useDeleteAttachment();
  const restoreMutation = useRestoreAttachment();
  const bulkRestoreMutation = useBulkRestoreAttachments();
  const restoreDirectoryMutation = useRestoreDirectory();
  const downloadMutation = useDownloadAttachment();
  const updateMutation = useUpdateAttachment();

  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Attachment | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const openRename = useCallback((attachment: Attachment) => {
    setRenameTarget(attachment);
    setRenameValue(attachment.original_filename || '');
    setRenameDialogOpen(true);
  }, []);

  const submitRename = useCallback(async () => {
    if (!renameTarget) return;
    const next = renameValue.trim();
    if (!next) {
      toast.error('Filename cannot be empty.');
      return;
    }
    if (next === renameTarget.original_filename) {
      setRenameDialogOpen(false);
      return;
    }
    try {
      await updateMutation.mutateAsync({ attachmentId: renameTarget.id, data: { original_filename: next } });
      toast.success('Renamed.');
      setRenameDialogOpen(false);
      setRenameTarget(null);
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Rename failed.');
    }
  }, [renameTarget, renameValue, updateMutation, queryClient]);

  const [isResubmittingBulk, setIsResubmittingBulk] = useState(false);

  const handleResubmit = useCallback(
    async (attachment: Attachment) => {
      const { id } = attachment;
      setPendingResubmitIds((prev) => new Set(prev).add(id));
      try {
        await resubmitAttachmentWebhook(id);
        toast.success('Resubmitted successfully');
        queryClient.invalidateQueries({ queryKey: ['attachments'] });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to resubmit');
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
      toast.success('Resubmitted successfully');
      setRowSelection({});
    } else if (successCount === 0) {
      toast.error(`Failed to resubmit for ${failCount} attachment(s)`);
    } else {
      toast.warning(`Resubmitted ${successCount}, failed ${failCount}`);
    }
  }, [selectedDeletableIds, queryClient]);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const columns = useMemo<ColumnDef<Attachment>[]>(
    () => [
      ...(isTrashView
        ? []
        : [
            {
              id: 'drag',
              header: () => null,
              cell: ({ row }: { row: Row<Attachment> }) => (
                <AttachmentDragHandle
                  attachment={row.original}
                  currentDirectoryId={directoryId}
                />
              ),
              size: 40,
              enableSorting: false,
              enableResizing: false,
            },
          ]),
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
        id: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        accessorFn: (row) => row.original_filename,
        cell: ({ row }) => <span>{row.original.original_filename}</span>,
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        accessorFn: (row) => row.mime_type,
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
        id: 'attachment_type',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Type" column={column} />,
        accessorFn: (row) => row.attachment_type?.type_name,
        cell: ({ row }) => row.original.attachment_type?.type_name ?? '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'size',
        header: ({ column }) => <DataGridColumnHeader title="Size" column={column} />,
        accessorFn: (row) => row.file_size_bytes,
        cell: ({ row }) =>
          row.original.file_size_bytes ? formatFileSize(row.original.file_size_bytes) : '-',
        size: 100,
      },
      {
        id: 'uploaded_by',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded By" column={column} />,
        accessorFn: (row) =>
          row.uploaded_by_user?.name ?? row.uploaded_by_user?.email,
        cell: ({ row }) =>
          row.original.uploaded_by_user?.name ?? row.original.uploaded_by_user?.email ?? '-',
        size: 150,
      },
      {
        id: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Upload at" column={column} />,
        accessorFn: (row) => row.uploaded_at,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.uploaded_at),
        size: 180,
      },
      {
        id: 'actions',
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
                    setSelectedAttachment(row.original);
                    setDeleteDialogOpen(true);
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
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation();
                    openRename(row.original);
                  }}
                  disabled={row.original.is_deleted}
                >
                  <Pencil className="size-4" />
                </Button>
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
                  <RefreshCw
                    className={`size-4 ${pendingResubmitIds.has(row.original.id) ? 'animate-spin' : ''}`}
                  />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Move to trash"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedAttachment(row.original);
                    setDeleteDialogOpen(true);
                  }}
                  disabled={deleteMutation.isPending || row.original.is_deleted}
                >
                  <Trash2 className="size-4" />
                </Button>
              </>
            )}
          </div>
        ),
        size: 220,
        enableHiding: false,
      },
    ],
    [
      directoryId,
      isTrashView,
      deleteMutation.isPending,
      downloadMutation.isPending,
      handleResubmit,
      pendingResubmitIds,
      restoreMutation.isPending,
    ]
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
    enableRowSelection: (row) => isTrashView || !row.original.is_deleted,
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={(row) => {
          setViewAttachmentId(row.id);
          setViewModalOpen(true);
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
            </div>
            <div className="flex items-center gap-2">
              {trashFolderId && (
                <Button
                  variant="outline"
                  onClick={() =>
                    restoreDirectoryMutation.mutate(trashFolderId, {
                      onSuccess: onRestoreFolder,
                    })
                  }
                  disabled={restoreDirectoryMutation.isPending}
                >
                  <RotateCcw className="size-4 mr-2" />
                  Restore folder and contents
                </Button>
              )}
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
              {selectedDeletableIds.length > 0 && !isTrashView && onBulkAdjustAccessLevels && (
                <Button
                  variant="outline"
                  onClick={() => onBulkAdjustAccessLevels(selectedDeletableIds)}
                >
                  <Shield className="size-4 mr-2" />
                  Access levels ({selectedDeletableIds.length})
                </Button>
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
                    onClick={() => setBulkDeleteDialogOpen(true)}
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
                    Upload
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

      <AttachmentDetailModal
        open={viewModalOpen}
        onOpenChange={(open) => {
          setViewModalOpen(open);
          if (!open) setViewAttachmentId(null);
        }}
        attachmentId={viewAttachmentId}
        neighbourItems={(data?.data ?? []).map((a) => ({ id: a.id }))}
        onAttachmentChange={setViewAttachmentId}
      />

      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename file</DialogTitle>
            <DialogDescription>
              Renames the display label and the filename used when downloading. The underlying storage object and CDN URL are not changed.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rename-input-folder">
              Filename <span className="text-destructive">*</span>
            </Label>
            <Input
              id="rename-input-folder"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="new-filename.ext"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !updateMutation.isPending) {
                  e.preventDefault();
                  submitRename();
                }
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)} disabled={updateMutation.isPending}>
              Cancel
            </Button>
            <Button onClick={submitRename} disabled={updateMutation.isPending || !renameValue.trim()}>
              {updateMutation.isPending ? 'Saving…' : 'Rename'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
