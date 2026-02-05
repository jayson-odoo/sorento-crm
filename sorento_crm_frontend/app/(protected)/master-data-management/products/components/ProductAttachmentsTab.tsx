'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, LoaderCircleIcon, Eye, Download, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { useProductAttachmentsByProduct, useCreateProductAttachment, useDeleteProductAttachment } from '../../product-attachments/hooks/useProductAttachments';
import { useDownloadAttachment, useAttachments } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { toast } from 'sonner';
import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';
import { formatDate } from '@/lib/helpers';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';

interface ProductAttachmentsTabProps {
  productId: string | undefined;
  isEditMode: boolean;
}

export default function ProductAttachmentsTab({
  productId,
  isEditMode,
}: ProductAttachmentsTabProps) {
  const queryClient = useQueryClient();
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);

  // Fetch existing product attachments
  const { data: productAttachments, isLoading: isLoadingAttachments } = useProductAttachmentsByProduct(productId || null);
  const downloadMutation = useDownloadAttachment();
  const createMutation = useCreateProductAttachment();
  const deleteMutation = useDeleteProductAttachment();

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

  const handleRemove = (id: string) => {
    deleteMutation.mutate(id, {
      onSuccess: () => {
        // Optimistically update the cache by removing the deleted item
        queryClient.setQueryData(
          ['product-attachments-by-product', productId],
          (oldData: ProductAttachment[] | undefined) => {
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

  const renderAccessLevels = (levels?: string[] | null) => {
    if (!levels || levels.length === 0) return null;
    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {levels.map((level) => (
          <Badge key={level} variant="secondary">
            {level === 'dealer' ? 'Dealer' : 'End User'}
          </Badge>
        ))}
      </div>
    );
  };

  if (!isEditMode) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Attachments</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoadingAttachments ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : productAttachments && productAttachments.length > 0 ? (
            <div className="space-y-3">
              {productAttachments.map((pa) => (
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
                    {renderAccessLevels(pa.access_levels)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (pa.attachment?.id) {
                          window.open(pa.attachment.file_path, '_blank');
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
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No attachments linked to this product.
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Attachments</CardTitle>
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
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoadingAttachments ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : productAttachments && productAttachments.length > 0 ? (
          <div className="space-y-3">
            {productAttachments.map((pa) => (
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
                    {renderAccessLevels(pa.access_levels)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (pa.attachment?.id) {
                        window.open(pa.attachment.file_path, '_blank');
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
            No attachments linked to this product. Upload a new attachment or link an existing one.
          </p>
        )}
      </CardContent>

      {linkDialogOpen && (
        <LinkAttachmentDialog
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
          productId={productId}
        />
      )}
    </Card>
  );
}

// LinkAttachmentDialog component - uses imports from top of file

interface LinkAttachmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId: string | undefined;
}

function LinkAttachmentDialog({ open, onOpenChange, productId }: LinkAttachmentDialogProps) {
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<string>('');
  const [accessLevels, setAccessLevels] = useState<string[]>(['dealer', 'end_user']);
  const createMutation = useCreateProductAttachment();
  const queryClient = useQueryClient();

  const { data: attachmentsData, isLoading: isLoadingAttachments } = useAttachments({
    pageIndex: 0,
    pageSize: 100,
    sorting: [],
    searchQuery: '',
  });
  const attachments = attachmentsData?.data || [];

  // Filter out attachments already linked to this product
  const { data: existingAttachments, isLoading: isLoadingExisting } = useProductAttachmentsByProduct(productId || null);
  const linkedAttachmentIds = new Set(existingAttachments?.map(pa => pa.attachment_id) || []);
  const availableAttachments = attachments.filter(a => !linkedAttachmentIds.has(a.id));

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setSelectedAttachmentId('');
      setSortOrder('');
      setAccessLevels(['dealer', 'end_user']);
    }
  }, [open]);

  const handleLink = () => {
    if (!selectedAttachmentId || !productId) {
      toast.error('Please select an attachment');
      return;
    }

    createMutation.mutate({
      product_id: productId,
      attachment_id: selectedAttachmentId,
      sort_order: sortOrder ? parseInt(sortOrder, 10) : undefined,
      access_levels: accessLevels,
    }, {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product', productId] });
        setSelectedAttachmentId('');
        setSortOrder('');
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Link Existing Attachment</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Attachment</Label>
            {isLoadingAttachments || isLoadingExisting ? (
              <div className="text-sm text-muted-foreground">Loading attachments...</div>
            ) : (
              <Select value={selectedAttachmentId} onValueChange={setSelectedAttachmentId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an attachment..." />
                </SelectTrigger>
                <SelectContent>
                  {availableAttachments.map((attachment) => (
                    <SelectItem key={attachment.id} value={attachment.id}>
                      {attachment.original_filename}
                    </SelectItem>
                  ))}
                  {availableAttachments.length === 0 && (
                    <SelectItem value="__no_attachments__" disabled>
                      No available attachments
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="space-y-2">
            <Label>Sort Order (optional)</Label>
            <Input
              type="number"
              placeholder="e.g., 1"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              min="0"
            />
          </div>
          <div className="space-y-2">
            <Label>Access Levels</Label>
            <div className="flex flex-wrap gap-4">
              {['dealer', 'end_user'].map((level) => {
                const checked = accessLevels.includes(level);
                return (
                  <label key={level} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(value) => {
                        const next = new Set(accessLevels);
                        if (value) {
                          next.add(level);
                        } else {
                          next.delete(level);
                        }
                        setAccessLevels(Array.from(next));
                      }}
                    />
                    {level === 'dealer' ? 'Dealer' : 'End User'}
                  </label>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleLink}
              disabled={!selectedAttachmentId || createMutation.isPending}
            >
              {createMutation.isPending ? (
                <LoaderCircleIcon className="size-4 animate-spin" />
              ) : (
                'Link Attachment'
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
