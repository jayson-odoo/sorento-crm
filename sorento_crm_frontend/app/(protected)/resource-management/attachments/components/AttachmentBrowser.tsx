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
import { Search, X, ChevronRight, Download, Eye, Trash2, Plus, RefreshCw, RotateCcw, FileArchive, Pencil, Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable, DataGridTableRowSelect, DataGridTableRowSelectAll } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useAttachments, useAttachmentTypesList, useDeleteAttachment, useDownloadAttachment, useRestoreAttachment, useBulkRestoreAttachments, useDirectoryTree, useUpdateAttachment } from '../hooks/useAttachments';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { getAttachmentPreviewUrl, resubmitAttachmentWebhook } from '../services/attachmentService';
import { buildDetailSearch } from '@/lib/listNavQuery';
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
import EditAttachmentTypeDialog from './EditAttachmentTypeDialog';

export default function AttachmentBrowser() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'uploaded_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [bulkImportDialogOpen, setBulkImportDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkEditTypeOpen, setBulkEditTypeOpen] = useState(false);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Attachment | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [selectedAttachment, setSelectedAttachment] = useState<Attachment | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [directoryId, setDirectoryId] = useState<string | null>(null);
  const [attachmentTypeId, setAttachmentTypeId] = useState<string>('__all__');
  const [linkStatus, setLinkStatus] = useState<'__all__' | 'linked' | 'unlinked'>('__all__');
  const [uploadedBy, setUploadedBy] = useState('');
  const [uploadedAtFrom, setUploadedAtFrom] = useState('');
  const [uploadedAtTo, setUploadedAtTo] = useState('');
  const [pendingResubmitIds, setPendingResubmitIds] = useState<Set<string>>(new Set());

  const queryClient = useQueryClient();
  const { data: directoryTree = [] } = useDirectoryTree();
  const { data: attachmentTypes = [] } = useAttachmentTypesList();
  const isTrashView = directoryId === '__trash__';

  const { data, isLoading } = useAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    directory_id: isTrashView ? undefined : directoryId ?? undefined,
    is_deleted: isTrashView ? true : undefined,
    attachment_type_id: attachmentTypeId !== '__all__' ? attachmentTypeId : undefined,
    link_status: linkStatus !== '__all__' ? linkStatus : undefined,
    uploaded_by: uploadedBy.trim() || undefined,
    uploaded_at_from: uploadedAtFrom || undefined,
    uploaded_at_to: uploadedAtTo || undefined,
  });

  // Carry the active list query (search/sort + folder/linkage/type/uploader/date
  // filters) into the detail URL so the detail pager walks the SAME filtered set.
  // Mirrors the exact filter mapping the list fetch above sends.
  const detailSearch = useMemo(
    () =>
      buildDetailSearch(
        {
          pageIndex: pagination.pageIndex,
          pageSize: pagination.pageSize,
          sorting,
          searchQuery,
        },
        {
          directory_id: isTrashView ? undefined : directoryId ?? undefined,
          is_deleted: isTrashView ? 'true' : undefined,
          attachment_type_id:
            attachmentTypeId !== '__all__' ? attachmentTypeId : undefined,
          link_status: linkStatus !== '__all__' ? linkStatus : undefined,
          uploaded_by: uploadedBy.trim() || undefined,
          uploaded_at_from: uploadedAtFrom || undefined,
          uploaded_at_to: uploadedAtTo || undefined,
        },
      ),
    [
      pagination.pageIndex,
      pagination.pageSize,
      sorting,
      searchQuery,
      isTrashView,
      directoryId,
      attachmentTypeId,
      linkStatus,
      uploadedBy,
      uploadedAtFrom,
      uploadedAtTo,
    ],
  );

  const deleteMutation = useDeleteAttachment();
  const restoreMutation = useRestoreAttachment();
  const bulkRestoreMutation = useBulkRestoreAttachments();
  const downloadMutation = useDownloadAttachment();
  const updateMutation = useUpdateAttachment();

  const openRename = useCallback((attachment: Attachment) => {
    setRenameTarget(attachment);
    setRenameValue(attachment.stored_filename || attachment.original_filename || '');
    setRenameDialogOpen(true);
  }, []);

  const submitRename = useCallback(async () => {
    if (!renameTarget) return;
    const next = renameValue.trim();
    if (!next) {
      toast.error('Filename cannot be empty.');
      return;
    }
    if (next === (renameTarget.stored_filename || renameTarget.original_filename)) {
      setRenameDialogOpen(false);
      return;
    }
    try {
      await updateMutation.mutateAsync({ attachmentId: renameTarget.id, data: { stored_filename: next } });
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
      
      // Create a blob URL and trigger download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.stored_filename || attachment.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
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
      toast.success('Resubmitted successfully');
      setRowSelection({});
    } else if (successCount === 0) {
      toast.error(`Failed to resubmit for ${failCount} attachment(s)`);
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
        id: 'filename',
        accessorFn: (row) => row.stored_filename || row.original_filename,
        cell: ({ row }) => <span>{row.original.stored_filename || row.original.original_filename}</span>,
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        size: 250,
        meta: { headerTitle: 'Filename', skeleton: <Skeleton className="h-4 w-32" /> },
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
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'attachment_type',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Type" column={column} />,
        cell: ({ row }) => row.original.attachment_type?.type_name ?? '-',
        size: 150,
        meta: { headerTitle: 'Attachment Type', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'file_size_bytes',
        header: ({ column }) => <DataGridColumnHeader title="Size" column={column} />,
        cell: ({ row }) => row.original.file_size_bytes ? formatFileSize(row.original.file_size_bytes) : '-',
        size: 100,
        meta: { headerTitle: 'Size' },
      },
      {
        accessorKey: 'uploaded_by_user.name',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded By" column={column} />,
        cell: ({ row }) => row.original.uploaded_by_user?.name ?? row.original.uploaded_by_user?.email ?? '-',
        size: 150,
        meta: { headerTitle: 'Uploaded By' },
      },
      {
        accessorKey: 'uploaded_at',
        header: ({ column }) => <DataGridColumnHeader title="Upload at" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.uploaded_at)),
        size: 180,
        meta: { headerTitle: 'Upload at' },
      },
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Entity" column={column} />,
        size: 120,
        meta: { headerTitle: 'Entity' },
      },
      {
        accessorKey: 'entity_name',
        header: ({ column }) => <DataGridColumnHeader title="Entity Name" column={column} />,
        size: 150,
        meta: { headerTitle: 'Entity Name' },
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

  // Bulk actions surface in the toolbar's selection strip; trash vs active
  // folders expose different sets, mirroring the previous hand-rolled buttons.
  const bulkActions: ToolbarAction[] = [];
  if (selectedDeletableIds.length > 0 && isTrashView) {
    bulkActions.push({
      key: 'bulk-restore',
      label: `Restore selected (${selectedDeletableIds.length})`,
      icon: RotateCcw,
      disabled: bulkRestoreMutation.isPending,
      onClick: () =>
        bulkRestoreMutation.mutate(selectedDeletableIds, {
          onSuccess: () => setRowSelection({}),
        }),
    });
    bulkActions.push({
      key: 'bulk-permanent-delete',
      label: `Permanently delete (${selectedDeletableIds.length})`,
      icon: Trash2,
      destructive: true,
      onClick: () => setBulkDeleteDialogOpen(true),
    });
  }
  if (selectedDeletableIds.length > 0 && !isTrashView) {
    bulkActions.push({
      key: 'bulk-attachment-type',
      label: `Attachment type (${selectedDeletableIds.length})`,
      icon: Tag,
      onClick: () => setBulkEditTypeOpen(true),
    });
    bulkActions.push({
      key: 'bulk-resubmit',
      label: `Resubmit selected (${selectedDeletableIds.length})`,
      icon: RefreshCw,
      disabled: isResubmittingBulk,
      onClick: handleBulkResubmit,
    });
    bulkActions.push({
      key: 'bulk-delete',
      label: `Delete selected (${selectedDeletableIds.length})`,
      icon: Trash2,
      destructive: true,
      onClick: handleBulkDelete,
    });
  }

  // Always-visible toolbar actions (not selection-gated).
  const secondaryActions: ToolbarAction[] = [];
  if (!isTrashView) {
    secondaryActions.push({
      key: 'bulk-import',
      label: 'Bulk import (ZIP)',
      icon: FileArchive,
      onClick: () => setBulkImportDialogOpen(true),
    });
  }

  // The folder/trash selector lives in the filter popover; count it as an active
  // filter only when narrowed away from "All folders".
  const totalFilterCount =
    (directoryId !== null ? 1 : 0) +
    (attachmentTypeId !== '__all__' ? 1 : 0) +
    (linkStatus !== '__all__' ? 1 : 0) +
    (uploadedBy.trim() ? 1 : 0) +
    (uploadedAtFrom || uploadedAtTo ? 1 : 0);

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        onRowClick={(row) =>
          router.push(
            `/resource-management/attachments/${row.id}${detailSearch ? `?${detailSearch}` : ''}`,
          )
        }
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
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
              }
              filters={{
                kind: 'custom',
                active: totalFilterCount > 0,
                activeCount: totalFilterCount,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Folder</p>
                      <SearchableSelect
                        value={directoryId ?? '__all__'}
                        onChange={(v) =>
                          setDirectoryId(v === '__all__' ? null : v === '__trash__' ? '__trash__' : v)
                        }
                        options={[
                          { value: '__all__', label: 'All folders' },
                          ...flattenDirectoryTree(directoryTree).map((d) => ({
                            value: d.id,
                            label: d.label,
                          })),
                          { value: '__trash__', label: 'Trash' },
                        ]}
                        placeholder="All folders"
                        triggerClassName="w-full"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Attachment type</p>
                      <SearchableSelect
                        value={attachmentTypeId}
                        onChange={(value) => {
                          setAttachmentTypeId(value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                        options={[
                          { value: '__all__', label: 'All attachment types' },
                          ...attachmentTypes.map((type) => ({
                            value: type.id,
                            label: type.type_name,
                          })),
                        ]}
                        placeholder="Attachment type"
                        triggerClassName="w-full"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Link status</p>
                      <SearchableSelect
                        value={linkStatus}
                        onChange={(value) => {
                          setLinkStatus(value as '__all__' | 'linked' | 'unlinked');
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                        options={[
                          { value: '__all__', label: 'All files' },
                          { value: 'linked', label: 'Linked' },
                          { value: 'unlinked', label: 'Not linked' },
                        ]}
                        placeholder="Link status"
                        triggerClassName="w-full"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Uploaded by user id</p>
                      <Input
                        placeholder="Uploaded by user id"
                        value={uploadedBy}
                        onChange={(event) => {
                          setUploadedBy(event.target.value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                        className="w-full"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Uploaded from</p>
                      <Input
                        type="date"
                        value={uploadedAtFrom}
                        onChange={(event) => {
                          setUploadedAtFrom(event.target.value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                        className="w-full"
                        aria-label="Uploaded from"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Uploaded to</p>
                      <Input
                        type="date"
                        value={uploadedAtTo}
                        onChange={(event) => {
                          setUploadedAtTo(event.target.value);
                          setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                        }}
                        className="w-full"
                        aria-label="Uploaded to"
                      />
                    </div>
                  </div>
                ),
              }}
              exportConfig={{ filename: 'attachments_export.xlsx' }}
              bulkActions={bulkActions}
              secondaryActions={secondaryActions}
              primaryAction={
                !isTrashView ? (
                  <Button
                    onClick={() => setUploadDialogOpen(true)}
                    data-guide-target="resource-management.files.upload-button"
                  >
                    <Plus className="size-4 mr-2" />
                    Create Attachment
                  </Button>
                ) : undefined
              }
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

    <EditAttachmentTypeDialog
      open={bulkEditTypeOpen}
      onOpenChange={setBulkEditTypeOpen}
      attachmentIds={selectedDeletableIds}
      onSaved={() => setRowSelection({})}
    />

    <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Rename file</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="rename-input">
            Filename <span className="text-destructive">*</span>
          </Label>
          <Input
            id="rename-input"
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
