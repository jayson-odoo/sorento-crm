'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  ColumnDef,
  PaginationState,
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
  FileArchive,
  RotateCcw,
  Shield,
  Pencil,
  Tag,
  Filter,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTableRowSelect, DataGridTableRowSelectAll } from '@/components/ui/data-grid-table';
import { DraggableAttachmentsTable } from './DraggableAttachmentsTable';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
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
import { useAttachmentTypes } from '../../attachment-types/hooks/useAttachmentTypes';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { getUsersSelect, type UserSelectItem } from '@/services/userSelectService';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import { CalendarDays } from 'lucide-react';
import type { DateRange } from 'react-day-picker';
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
import EditAttachmentTypeDialog from '../../attachments/components/EditAttachmentTypeDialog';
import { TRASH_VIEW_ID, TRASH_FOLDER_PREFIX, FOLDER_ALL_ID } from '../constants';

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
  const [accessLevelFilters, setAccessLevelFilters] = useState<string[]>([]);
  const [accessLevelsMatch, setAccessLevelsMatch] = useState<'any' | 'all' | 'exact'>('any');
  const [attachmentTypeId, setAttachmentTypeId] = useState<string>('__all__');
  const [linkStatus, setLinkStatus] = useState<'__all__' | 'linked' | 'unlinked'>('__all__');
  const [uploadedBy, setUploadedBy] = useState<string>('__all__');
  const [uploadedRange, setUploadedRange] = useState<DateRange | undefined>();
  const uploadedAtFrom = uploadedRange?.from ? format(uploadedRange.from, 'yyyy-MM-dd') : '';
  const uploadedAtTo = uploadedRange?.to ? format(uploadedRange.to, 'yyyy-MM-dd') : '';
  const { data: usersSelect = [] as UserSelectItem[] } = useQuery({
    queryKey: ['users-select', 'attachment-filter'],
    queryFn: () => getUsersSelect({ status: 'ACTIVE' }),
    staleTime: 5 * 60 * 1000,
  });
  const { data: attachmentTypesData } = useAttachmentTypes({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'type_name', desc: false }],
    searchQuery: '',
  });
  const attachmentTypes = attachmentTypesData?.data ?? [];
  const extraFilterCount =
    (attachmentTypeId !== '__all__' ? 1 : 0) +
    (linkStatus !== '__all__' ? 1 : 0) +
    (uploadedBy !== '__all__' ? 1 : 0) +
    (uploadedAtFrom || uploadedAtTo ? 1 : 0);
  const totalFilterCount = accessLevelFilters.length + extraFilterCount;
  const { data: accessTypes = [] } = useContactAccessTypes();
  const accessTypeNameByCode = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of accessTypes) m.set(t.code, t.name);
    return m;
  }, [accessTypes]);
  const toggleAccessLevel = (code: string) => {
    setAccessLevelFilters((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  };
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [bulkImportDialogOpen, setBulkImportDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkEditTypeOpen, setBulkEditTypeOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [viewAttachmentId, setViewAttachmentId] = useState<string | null>(null);

  // Deep-link from Upload Activity drawer: `?attachment_id=<uuid>` opens the
  // detail modal for that row. We strip the param after handling so back-nav
  // doesn't keep re-opening the modal.
  const _router = useRouter();
  const _pathname = usePathname();
  const _searchParams = useSearchParams();
  useEffect(() => {
    const deepLinkId = _searchParams?.get('attachment_id');
    if (deepLinkId && deepLinkId !== viewAttachmentId) {
      setViewAttachmentId(deepLinkId);
      setViewModalOpen(true);
      const next = new URLSearchParams(_searchParams?.toString() ?? '');
      next.delete('attachment_id');
      const qs = next.toString();
      _router.replace(qs ? `${_pathname}?${qs}` : (_pathname ?? '/'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_searchParams]);
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
    access_levels: accessLevelFilters.length > 0 ? accessLevelFilters : undefined,
    access_levels_match: accessLevelFilters.length > 0 ? accessLevelsMatch : undefined,
    attachment_type_id: attachmentTypeId !== '__all__' ? attachmentTypeId : undefined,
    link_status: linkStatus !== '__all__' ? linkStatus : undefined,
    uploaded_by: uploadedBy !== '__all__' ? uploadedBy : undefined,
    uploaded_at_from: uploadedAtFrom || undefined,
    uploaded_at_to: uploadedAtTo || undefined,
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
    // stored_filename is the user-facing, editable name (original_filename is immutable).
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
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.stored_filename || attachment.original_filename || 'download';
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
        accessorFn: (row) => row.stored_filename || row.original_filename,
        cell: ({ row }) => <span>{row.original.stored_filename || row.original.original_filename}</span>,
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
        id: 'access_levels',
        header: ({ column }) => <DataGridColumnHeader title="Access" column={column} />,
        accessorFn: (row) => (row.access_levels ?? []).join(','),
        enableSorting: false,
        cell: ({ row }) => {
          const levels = Array.from(new Set(row.original.access_levels ?? []));
          if (levels.length === 0) return <span className="text-muted-foreground">-</span>;
          return (
            <div className="flex flex-wrap gap-1">
              {levels.map((code) => (
                <Badge key={code} variant="secondary" className="text-[10px]">
                  {accessTypeNameByCode.get(code) ?? code}
                </Badge>
              ))}
            </div>
          );
        },
        size: 220,
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
      accessTypeNameByCode,
      selectedDeletableIds,
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
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1 relative" title="Filters">
                    <Filter className="size-4" />
                    Filters
                    {totalFilterCount > 0 && (
                      <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                        {totalFilterCount}
                      </Badge>
                    )}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-72" align="start">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium text-sm">Filters</h4>
                      {totalFilterCount > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-auto px-1 text-xs"
                          onClick={() => {
                            setAccessLevelFilters([]);
                            setAccessLevelsMatch('any');
                            setAttachmentTypeId('__all__');
                            setLinkStatus('__all__');
                            setUploadedBy('__all__');
                            setUploadedRange(undefined);
                            setPagination((p) => ({ ...p, pageIndex: 0 }));
                          }}
                        >
                          Clear all
                        </Button>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Attachment type</p>
                      <Select
                        value={attachmentTypeId}
                        onValueChange={(v) => {
                          setAttachmentTypeId(v);
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="All attachment types" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__all__">All attachment types</SelectItem>
                          {attachmentTypes.map((t) => (
                            <SelectItem key={t.id} value={t.id}>
                              {t.type_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Link status</p>
                      <Select
                        value={linkStatus}
                        onValueChange={(v) => {
                          setLinkStatus(v as '__all__' | 'linked' | 'unlinked');
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="All files" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__all__">All files</SelectItem>
                          <SelectItem value="linked">Linked</SelectItem>
                          <SelectItem value="unlinked">Not linked</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Uploaded by</p>
                      <Select
                        value={uploadedBy}
                        onValueChange={(v) => {
                          setUploadedBy(v);
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="All users" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__all__">All users</SelectItem>
                          {usersSelect.map((u) => (
                            <SelectItem key={u.id} value={u.id}>
                              {u.name?.trim() || u.email}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium">Uploaded date range</p>
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            className="w-full justify-start font-normal"
                          >
                            <CalendarDays className="size-4 me-2 opacity-70" />
                            {uploadedRange?.from ? (
                              uploadedRange.to ? (
                                <span>
                                  {format(uploadedRange.from, 'dd MMM yyyy')} -{' '}
                                  {format(uploadedRange.to, 'dd MMM yyyy')}
                                </span>
                              ) : (
                                <span>{format(uploadedRange.from, 'dd MMM yyyy')}</span>
                              )
                            ) : (
                              <span className="text-muted-foreground">Any date</span>
                            )}
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                          <Calendar
                            mode="range"
                            defaultMonth={uploadedRange?.from}
                            selected={uploadedRange}
                            onSelect={(range) => {
                              setUploadedRange(range);
                              setPagination((p) => ({ ...p, pageIndex: 0 }));
                            }}
                            numberOfMonths={2}
                          />
                          {uploadedRange && (
                            <div className="flex justify-end p-2 border-t">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setUploadedRange(undefined);
                                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                                }}
                              >
                                Clear
                              </Button>
                            </div>
                          )}
                        </PopoverContent>
                      </Popover>
                    </div>
                    <div className="border-t pt-2">
                      <h4 className="font-medium text-sm mb-1.5">Access levels</h4>
                    </div>
                    {accessTypes.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        No access types configured.
                      </p>
                    ) : (
                      <>
                        <label
                          htmlFor="access-filter-select-all"
                          className="flex items-center gap-2 text-sm cursor-pointer border-b pb-2"
                        >
                          <Checkbox
                            id="access-filter-select-all"
                            checked={
                              accessLevelFilters.length === accessTypes.length
                                ? true
                                : accessLevelFilters.length > 0
                                  ? 'indeterminate'
                                  : false
                            }
                            onCheckedChange={(v) => {
                              setAccessLevelFilters(
                                v === true ? accessTypes.map((t) => t.code) : []
                              );
                              setPagination((p) => ({ ...p, pageIndex: 0 }));
                            }}
                          />
                          <span className="font-medium">Select all</span>
                        </label>
                        <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
                          {accessTypes.map((opt) => {
                            const id = `access-filter-${opt.code}`;
                            const checked = accessLevelFilters.includes(opt.code);
                            return (
                              <label
                                key={opt.code}
                                htmlFor={id}
                                className="flex items-center gap-2 text-sm cursor-pointer"
                              >
                                <Checkbox
                                  id={id}
                                  checked={checked}
                                  onCheckedChange={() => toggleAccessLevel(opt.code)}
                                />
                                <span>{opt.name}</span>
                              </label>
                            );
                          })}
                        </div>
                        <div className="border-t pt-2 space-y-1.5">
                          <p className="text-xs font-medium">Match mode</p>
                          <RadioGroup
                            value={accessLevelsMatch}
                            onValueChange={(v) => {
                              setAccessLevelsMatch(v as 'any' | 'all' | 'exact');
                              setPagination((p) => ({ ...p, pageIndex: 0 }));
                            }}
                            size="sm"
                            className="gap-1.5"
                          >
                            <label htmlFor="access-match-any" className="flex items-start gap-2 text-xs cursor-pointer">
                              <RadioGroupItem id="access-match-any" value="any" className="mt-0.5" />
                              <span>
                                <span className="font-medium">Any of selected</span>
                                <span className="block text-muted-foreground">Show files tagged with at least one chosen level.</span>
                              </span>
                            </label>
                            <label htmlFor="access-match-all" className="flex items-start gap-2 text-xs cursor-pointer">
                              <RadioGroupItem id="access-match-all" value="all" className="mt-0.5" />
                              <span>
                                <span className="font-medium">All of selected</span>
                                <span className="block text-muted-foreground">File must include every chosen level (extras allowed).</span>
                              </span>
                            </label>
                            <label htmlFor="access-match-exact" className="flex items-start gap-2 text-xs cursor-pointer">
                              <RadioGroupItem id="access-match-exact" value="exact" className="mt-0.5" />
                              <span>
                                <span className="font-medium">Exactly these</span>
                                <span className="block text-muted-foreground">File's levels must match the selection exactly.</span>
                              </span>
                            </label>
                          </RadioGroup>
                        </div>
                      </>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
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
                <Button
                  variant="outline"
                  onClick={() => setBulkEditTypeOpen(true)}
                  data-testid="bulk-attachment-type-trigger"
                >
                  <Tag className="size-4 mr-2" />
                  Attachment type ({selectedDeletableIds.length})
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
                  <Button
                    onClick={() => setUploadDialogOpen(true)}
                    data-guide-target="resource-management.files.upload-button"
                  >
                    <Plus className="size-4 mr-2" />
                    Upload
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setBulkImportDialogOpen(true)}
                    data-guide-target="resource-management.files.bulk-import-button"
                  >
                    <FileArchive className="size-4 mr-2" />
                    Bulk import (ZIP)
                  </Button>
                </>
              )}
            </div>
          </CardHeader>
          {/* LatestImportStatusPanel removed — bulk-ZIP progress + n8n
              integration status now live in the Upload Activity drawer
              (top-nav icon). See docs/plans/PLAN-upload-activity-drawer.md. */}
          <CardTable>
            <ScrollArea>
              <DraggableAttachmentsTable
                currentDirectoryId={directoryId}
                selectedIds={selectedDeletableIds}
                draggable={!isTrashView}
              />
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
        defaultDirectoryId={effectiveDirectoryId ?? null}
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
