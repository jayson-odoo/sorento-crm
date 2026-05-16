'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, LoaderCircleIcon, Eye, Download, Upload, ChevronRight, ChevronDown, ChevronUp, Folder, FolderOpen, FileText, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { usePromotionAttachmentsByPromotion, useCreatePromotionAttachment, useDeletePromotionAttachment } from '../../promotion-attachments/hooks/usePromotionAttachments';
import { createPromotionAttachment as createPromotionAttachmentApi } from '../../promotion-attachments/services/promotionAttachmentService';
import { usePromotion } from '../hooks/usePromotions';
import { useDownloadAttachment, useAttachments, useUploadAttachment, useDirectoryTree } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { useUploadConflict } from '@/hooks/use-upload-conflict';
import { toast } from 'sonner';
import type { PromotionAttachment } from '../../promotion-attachments/types/promotionAttachment.types';
import { formatDate } from '@/lib/helpers';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { AttachmentDirectoryTreeNode } from '@/app/(protected)/resource-management/attachments/services/directoryService';
import { cn } from '@/lib/utils';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';

function formatAccessLevels(levels: string[] | null | undefined): string {
  if (!levels || levels.length === 0) return '—';
  return levels
    .map((l) => l.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()))
    .join(', ');
}

interface PromotionAttachmentsTabProps {
  promotionId: string | undefined;
  isEditMode: boolean;
  /** When provided (e.g. from detail page), shown as promotion access in the attachments section. */
  promotionAccessLevels?: string[] | null;
}

export default function PromotionAttachmentsTab({
  promotionId,
  isEditMode,
  promotionAccessLevels,
}: PromotionAttachmentsTabProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [addAttachmentDialogOpen, setAddAttachmentDialogOpen] = useState(false);

  // Fetch existing promotion attachments
  const { data: promotionAttachments, isLoading: isLoadingAttachments } = usePromotionAttachmentsByPromotion(promotionId || null);
  const downloadMutation = useDownloadAttachment();
  const createMutation = useCreatePromotionAttachment();
  const deleteMutation = useDeletePromotionAttachment();

  const handleDownload = async (attachmentId: string, filename: string) => {
    try {
      const blob = await downloadMutation.mutateAsync(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      // Error is handled by the mutation hook
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

  const handleRemove = (id: string) => {
    deleteMutation.mutate(id, {
      onSuccess: () => {
        // Optimistically update the cache by removing the deleted item
        queryClient.setQueryData(
          ['promotion-attachments-by-promotion', promotionId],
          (oldData: PromotionAttachment[] | undefined) => {
            if (!oldData) return oldData;
            return oldData.filter((pa) => pa.id !== id);
          }
        );
      },
    });
  };

  const formatFileSize = (bytes: number | null | undefined): string => {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  if (!isEditMode) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
          <CardTitle>Attachments</CardTitle>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setAddAttachmentDialogOpen(true)}
                disabled={!promotionId}
              >
                <Upload className="size-4" />
                Add attachment
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLinkDialogOpen(true)}
                disabled={!promotionId}
              >
                <Plus className="size-4" />
                Link Existing
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoadingAttachments ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : promotionAttachments && promotionAttachments.length > 0 ? (
            <div className="space-y-3">
              {promotionAttachments.map((pa) => (
                <div
                  key={pa.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex items-center gap-3 flex-1">
                    {pa.is_primary && (
                      <Badge variant="primary">Primary</Badge>
                    )}
                    <div className="flex-1">
                      <p className="font-medium text-sm">
                        {pa.attachment?.original_filename || 'Unknown'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {pa.attachment?.attachment_type?.type_name || 'No type'} •{' '}
                        {formatFileSize(pa.attachment?.file_size_bytes)} •{' '}
                        {pa.attachment?.uploaded_at && formatDate(new Date(pa.attachment.uploaded_at))}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      title="Open in folder"
                      onClick={() =>
                        router.push(
                          pa.attachment?.directory_id
                            ? `/resource-management/attachment-directories?directoryId=${pa.attachment.directory_id}`
                            : '/resource-management/attachment-directories',
                        )
                      }
                    >
                      <FolderOpen className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (pa.attachment?.id) {
                          handlePreview(pa.attachment.id);
                        }
                      }}
                    >
                      <Eye className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (pa.attachment?.id && pa.attachment?.original_filename) {
                          handleDownload(pa.attachment.id, pa.attachment.original_filename);
                        }
                      }}
                    >
                      <Download className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemove(pa.id)}
                      disabled={deleteMutation.isPending}
                      title="Unlink from promotion"
                    >
                      {deleteMutation.isPending ? (
                        <LoaderCircleIcon className="size-4 text-muted-foreground" />
                      ) : (
                        <Trash2 className="size-4 text-destructive" />
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No attachments linked to this promotion.
            </p>
          )}
        </CardContent>
        {linkDialogOpen && (
          <LinkAttachmentDialog
            open={linkDialogOpen}
            onOpenChange={setLinkDialogOpen}
            promotionId={promotionId}
          />
        )}
        {addAttachmentDialogOpen && promotionId && (
          <AddPromotionAttachmentDialog
            promotionId={promotionId}
            open={addAttachmentDialogOpen}
            onOpenChange={setAddAttachmentDialogOpen}
            onSuccess={() => queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion', promotionId] })}
            promotionAccessLevels={promotionAccessLevels ?? undefined}
          />
        )}
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
          <CardTitle>Attachments</CardTitle>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAddAttachmentDialogOpen(true)}
              disabled={!promotionId}
            >
              <Upload className="size-4" />
              Add attachment
            </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setLinkDialogOpen(true)}
          >
            <Plus className="size-4" />
            Link Existing
          </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoadingAttachments ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : promotionAttachments && promotionAttachments.length > 0 ? (
          <div className="space-y-3">
            {promotionAttachments.map((pa) => (
              <div
                key={pa.id}
                className="flex items-center justify-between rounded-lg border p-4"
              >
                <div className="flex items-center gap-3 flex-1">
                  <div className="flex-1">
                    <p className="font-medium text-sm">
                      {pa.attachment?.original_filename || 'Unknown'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {pa.attachment?.attachment_type?.type_name || 'No type'} •{' '}
                      {formatFileSize(pa.attachment?.file_size_bytes)} •{' '}
                      {pa.attachment?.uploaded_at && formatDate(new Date(pa.attachment.uploaded_at))}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    title="Open in folder"
                    onClick={() =>
                      router.push(
                        pa.attachment?.directory_id
                          ? `/resource-management/attachment-directories?directoryId=${pa.attachment.directory_id}`
                          : '/resource-management/attachment-directories',
                      )
                    }
                  >
                    <FolderOpen className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (pa.attachment?.id) {
                        handlePreview(pa.attachment.id);
                      }
                    }}
                  >
                    <Eye className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (pa.attachment?.id && pa.attachment?.original_filename) {
                        handleDownload(pa.attachment.id, pa.attachment.original_filename);
                      }
                    }}
                  >
                    <Download className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemove(pa.id)}
                    disabled={deleteMutation.isPending}
                    title="Unlink from promotion"
                  >
                    {deleteMutation.isPending ? (
                      <LoaderCircleIcon className="size-4 animate-spin" />
                    ) : (
                      <Trash2 className="size-4 text-destructive" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No attachments linked to this promotion. Link an existing attachment.
          </p>
        )}
      </CardContent>

      {linkDialogOpen && (
        <LinkAttachmentDialog
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
          promotionId={promotionId}
        />
      )}
      {addAttachmentDialogOpen && promotionId && (
        <AddPromotionAttachmentDialog
          promotionId={promotionId}
          open={addAttachmentDialogOpen}
          onOpenChange={setAddAttachmentDialogOpen}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion', promotionId] })}
          promotionAccessLevels={promotionAccessLevels ?? undefined}
        />
      )}
    </Card>
  );
}

// Add promotion attachment: upload file to S3 (no type, no webhook), choose folder, then link to promotion

interface AddPromotionAttachmentDialogProps {
  promotionId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  /** Promotion access levels; uploaded attachment will use these. If not provided, fetched from promotion. */
  promotionAccessLevels?: string[] | null;
}

function DirectoryTreeRow({
  node,
  depth,
  selectedId,
  expandedIds,
  onSelect,
  onToggleExpand,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  onSelect: (id: string) => void;
  onToggleExpand: (id: string) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;

  return (
    <div className="flex flex-col">
      <div
        className={cn(
          'flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer min-w-0 hover:bg-accent/50',
          isSelected && 'bg-accent text-accent-foreground'
        )}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.id)}
      >
        <button
          type="button"
          className="p-0.5 hover:bg-muted rounded shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand(node.id);
          }}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {hasChildren ? (
            <ChevronRight
              className={cn('size-4 text-muted-foreground transition-transform', isExpanded && 'rotate-90')}
            />
          ) : (
            <span className="inline-block w-4" />
          )}
        </button>
        {hasChildren && isExpanded ? (
          <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <Folder className="size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="whitespace-nowrap truncate" title={node.name}>
          {node.name}
        </span>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <DirectoryTreeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expandedIds={expandedIds}
              onSelect={onSelect}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AddPromotionAttachmentDialog({
  promotionId,
  open,
  onOpenChange,
  onSuccess,
  promotionAccessLevels: promotionAccessLevelsProp,
}: AddPromotionAttachmentDialogProps) {
  const [directoryId, setDirectoryId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const { data: promotion } = usePromotion(open ? promotionId : null);
  const promotionAccessLevels = promotionAccessLevelsProp ?? promotion?.access_levels ?? undefined;

  const { data: directoryTree = [], isLoading: isLoadingTree } = useDirectoryTree();
  const uploadMutation = useUploadAttachment();
  const createLinkMutation = useCreatePromotionAttachment();
  const { runUpload, ConflictDialog } = useUploadConflict();

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!open) {
      setDirectoryId(null);
      setFile(null);
    }
  }, [open]);

  const handleUpload = async () => {
    if (!file || !promotionId) {
      toast.error('Please select a file');
      return;
    }
    try {
      const attachment = await runUpload((onConflict) =>
        uploadMutation.mutateAsync({
          file,
          entityType: 'promotion',
          entityId: promotionId,
          directoryId: directoryId ?? undefined,
          accessLevels: promotionAccessLevels && promotionAccessLevels.length > 0 ? promotionAccessLevels : ['dealer', 'end_user'],
          onConflict,
        })
      );
      if (attachment == null) {
        // User cancelled the conflict prompt
        return;
      }
      await createLinkMutation.mutateAsync({
        promotion_id: promotionId,
        attachment_id: attachment.id,
      });
      toast.success('Attachment added and linked to this promotion');
      onSuccess?.();
      onOpenChange(false);
    } catch {
      // Toasts from mutations
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add attachment</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>
              Folder <span className="text-destructive">*</span>
            </Label>
            <p className="text-xs text-muted-foreground">
              Choose the folder where this file will be stored (hierarchical list below).
            </p>
            <ScrollArea className="h-[200px] rounded-md border p-2">
              {isLoadingTree ? (
                <div className="text-sm text-muted-foreground py-4">Loading folders...</div>
              ) : directoryTree.length === 0 ? (
                <div className="text-sm text-muted-foreground py-4">No folders yet. Upload will go to root.</div>
              ) : (
                <div className="pr-4">
                  <button
                    type="button"
                    className={cn(
                      'flex items-center gap-2 w-full rounded-md px-2 py-1.5 text-sm text-left hover:bg-accent/50',
                      directoryId === null && 'bg-accent text-accent-foreground'
                    )}
                    onClick={() => setDirectoryId(null)}
                  >
                    <Folder className="size-4 shrink-0 text-muted-foreground" />
                    <span>Root (no folder)</span>
                  </button>
                  {directoryTree.map((node) => (
                    <DirectoryTreeRow
                      key={node.id}
                      node={node}
                      depth={0}
                      selectedId={directoryId}
                      expandedIds={expandedIds}
                      onSelect={setDirectoryId}
                      onToggleExpand={toggleExpand}
                    />
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
          <div className="space-y-2">
            <Label>
              File <span className="text-destructive">*</span>
            </Label>
            <div className="flex items-center gap-2">
              <Input
                type="file"
                onChange={(e) => {
                  const chosen = e.target.files?.[0] ?? null;
                  if (chosen && chosen.name.trim().startsWith('._')) {
                    toast.error('Files starting with ._ are macOS metadata and cannot be uploaded.');
                    setFile(null);
                    e.target.value = '';
                    return;
                  }
                  setFile(chosen);
                }}
                className="flex-1"
              />
              {file && (
                <span className="text-sm text-muted-foreground truncate max-w-[180px]" title={file.name}>
                  {file.name}
                </span>
              )}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!file || uploadMutation.isPending || createLinkMutation.isPending}
          >
            {(uploadMutation.isPending || createLinkMutation.isPending) ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              'Upload & link'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
      {ConflictDialog}
    </Dialog>
  );
}

// LinkAttachmentDialog component

interface LinkAttachmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promotionId: string | undefined;
}

function LinkAttachmentDialog({ open, onOpenChange, promotionId }: LinkAttachmentDialogProps) {
  const PAGE_SIZE = 50;
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedDirectoryId, setSelectedDirectoryId] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [isLinking, setIsLinking] = useState(false);
  const queryClient = useQueryClient();

  const { data: promotion } = usePromotion(open && promotionId ? promotionId : null);
  const promotionAccessLevels = promotion?.access_levels ?? [];
  const { data: directoryTree = [], isLoading: isLoadingTree } = useDirectoryTree();

  const { data: attachmentsData, isLoading: isLoadingAttachments } = useAttachments({
    pageIndex,
    pageSize: PAGE_SIZE,
    sorting: [],
    searchQuery,
    directory_id: selectedDirectoryId,
    resolve_signed_urls: false,
  });
  const attachments = attachmentsData?.data || [];
  const pagination = attachmentsData?.pagination;
  const currentPage = pagination?.page ?? pageIndex + 1;
  const total = pagination?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Filter out attachments already linked to this promotion
  const { data: existingAttachments, isLoading: isLoadingExisting } = usePromotionAttachmentsByPromotion(promotionId || null);
  const linkedAttachmentIds = new Set(existingAttachments?.map(pa => pa.attachment_id) || []);
  // Only show attachments whose access_levels contain at least one of the promotion's access levels
  const availableAttachments = attachments.filter((a) => {
    if (linkedAttachmentIds.has(a.id)) return false;
    if (!promotionAccessLevels?.length) return true;
    const attachmentLevels = a.access_levels ?? [];
    return attachmentLevels.some((al) => promotionAccessLevels.includes(al));
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setSelectedAttachmentIds(new Set());
      setSearchQuery('');
      setSelectedDirectoryId(null);
      setPageIndex(0);
      setExpandedIds(new Set());
    }
  }, [open]);

  const selectedCount = selectedAttachmentIds.size;
  const allOnPageSelected =
    availableAttachments.length > 0 &&
    availableAttachments.every((a) => selectedAttachmentIds.has(a.id));
  const allFolderIds = useMemo(() => {
    const ids = new Set<string>();
    const walk = (nodes: AttachmentDirectoryTreeNode[]) => {
      for (const node of nodes) {
        ids.add(node.id);
        if (node.children?.length) walk(node.children);
      }
    };
    walk(directoryTree);
    return ids;
  }, [directoryTree]);

  const handleExpandAll = useCallback(() => setExpandedIds(new Set(allFolderIds)), [allFolderIds]);
  const handleCollapseAll = useCallback(() => setExpandedIds(new Set()), []);
  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelection = (attachmentId: string) => {
    setSelectedAttachmentIds((prev) => {
      const next = new Set(prev);
      if (next.has(attachmentId)) next.delete(attachmentId);
      else next.add(attachmentId);
      return next;
    });
  };

  const toggleSelectAllOnPage = () => {
    setSelectedAttachmentIds((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        availableAttachments.forEach((a) => next.delete(a.id));
      } else {
        availableAttachments.forEach((a) => next.add(a.id));
      }
      return next;
    });
  };

  const handleLink = async () => {
    if (selectedAttachmentIds.size === 0 || !promotionId) {
      toast.error('Please select at least one attachment');
      return;
    }
    setIsLinking(true);
    const ids = Array.from(selectedAttachmentIds);
    try {
      for (const attachmentId of ids) {
        await createPromotionAttachmentApi({
      promotion_id: promotionId,
          attachment_id: attachmentId,
        });
      }
        queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion', promotionId] });
      toast.success(`${ids.length} attachment(s) linked to promotion`);
      setSelectedAttachmentIds(new Set());
      setSearchQuery('');
      setSelectedDirectoryId(null);
      setPageIndex(0);
      setExpandedIds(new Set());
        onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to link attachment(s)');
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Link Existing Attachment</DialogTitle>
        </DialogHeader>
          <div className="space-y-2">
            <Label>Attachment</Label>
          {promotionAccessLevels?.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Only attachments with access type matching this promotion ({formatAccessLevels(promotionAccessLevels)}) are shown.
            </p>
          )}
        </div>
        <ResizablePanelGroup direction="horizontal" className="flex-1 min-h-0 rounded-lg border bg-card">
          <ResizablePanel defaultSize={22} minSize={16} maxSize={40} className="min-w-0">
            <div className="h-full flex flex-col overflow-hidden">
              <div className="px-2 py-2 border-b bg-muted/40 flex items-center justify-between gap-1 shrink-0">
                <span className="text-sm font-medium text-muted-foreground">Folders</span>
                <div className="flex items-center gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={handleExpandAll}
                    title="Expand all"
                    aria-label="Expand all"
                  >
                    <ChevronDown className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={handleCollapseAll}
                    title="Collapse all"
                    aria-label="Collapse all"
                  >
                    <ChevronUp className="size-4" />
                  </Button>
                </div>
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-2">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedDirectoryId(null);
                      setPageIndex(0);
                    }}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left w-full',
                      selectedDirectoryId === null && 'bg-accent text-accent-foreground',
                    )}
                  >
                    <Folder className="size-4 text-muted-foreground shrink-0" />
                    All attachments
                  </button>
                  {directoryTree.map((node) => (
                    <DirectoryTreeRow
                      key={node.id}
                      node={node}
                      depth={0}
                      selectedId={selectedDirectoryId}
                      expandedIds={expandedIds}
                      onSelect={(id) => {
                        setSelectedDirectoryId(id);
                        setPageIndex(0);
                      }}
                      onToggleExpand={handleToggleExpand}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>
          <ResizableHandle withHandle className="bg-border" />
          <ResizablePanel defaultSize={78} minSize={50} className="min-w-0">
            <div className="h-full flex flex-col overflow-hidden">
              <div className="px-3 py-2 border-b bg-muted/40 flex items-center justify-between gap-2 shrink-0">
                <span className="text-sm font-medium text-muted-foreground">Files</span>
                {availableAttachments.length > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={toggleSelectAllOnPage}>
                    {allOnPageSelected ? 'Deselect page' : 'Select page'}
                  </Button>
                )}
              </div>
              <div className="px-2 py-2 border-b shrink-0">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    placeholder="Search attachments..."
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setPageIndex(0);
                    }}
                    className="pl-8 pr-8 h-9"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => {
                        setSearchQuery('');
                        setPageIndex(0);
                      }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground rounded p-0.5"
                      aria-label="Clear search"
                    >
                      <X className="size-4" />
                    </button>
                  )}
                </div>
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="p-2">
                  {isLoadingAttachments || isLoadingExisting || isLoadingTree ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                      <LoaderCircleIcon className="size-5 animate-spin mr-2" />
                      Loading...
                    </div>
                  ) : availableAttachments.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      {attachments.length === 0
                        ? 'No files in this folder.'
                        : 'All files here are already linked to this promotion.'}
                    </div>
                  ) : (
                    <ul className="space-y-0.5">
                      {availableAttachments.map((att) => (
                        <li
                          key={att.id}
                          className={cn(
                            'flex items-center gap-2 rounded-md px-2 py-2 cursor-pointer hover:bg-accent/50',
                            selectedAttachmentIds.has(att.id) && 'bg-accent/70',
                          )}
                          onClick={() => toggleSelection(att.id)}
                        >
                          <Checkbox
                            checked={selectedAttachmentIds.has(att.id)}
                            onCheckedChange={() => toggleSelection(att.id)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <FileText className="size-4 text-muted-foreground shrink-0" />
                          <span className="truncate text-sm flex-1" title={att.original_filename}>
                            {att.original_filename}
                          </span>
                        </li>
                      ))}
                    </ul>
            )}
          </div>
              </ScrollArea>
              <div className="px-3 py-2 border-t bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Page {currentPage} of {totalPages} ({total} items)
                </span>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-2"
                    onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                    disabled={currentPage <= 1 || isLoadingAttachments}
                  >
                    Prev
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-2"
                    onClick={() => setPageIndex((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={currentPage >= totalPages || isLoadingAttachments}
                  >
                    Next
                  </Button>
                </div>
              </div>
          </div>
          </ResizablePanel>
        </ResizablePanelGroup>

        {selectedCount > 0 && (
          <p className="text-xs text-muted-foreground">
            Selected: {selectedCount} attachment(s)
          </p>
        )}

        <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleLink}
            disabled={selectedCount === 0 || isLinking}
            >
            {isLinking ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : (
              `Link ${selectedCount > 0 ? selectedCount : ''} attachment(s)`
              )}
            </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
