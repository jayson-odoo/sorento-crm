'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, LoaderCircleIcon, Eye, Download, Folder, ChevronDown, FolderOpen, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Skeleton } from '@/components/ui/skeleton';
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
import { useProductAttachmentsByProduct, useDeleteProductAttachment } from '../../product-attachments/hooks/useProductAttachments';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';
import { formatDate } from '@/lib/helpers';
import LinkAttachmentBrowserDialog from './LinkAttachmentBrowserDialog';
import AttachmentDetailModal from '@/app/(protected)/resource-management/attachments/components/AttachmentDetailModal';
import ManageFieldLinksDialog from '@/app/(protected)/resource-management/attachments/components/ManageFieldLinksDialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { useFieldLinkageSchema } from '../hooks/useFieldLinkageSchema';
import { useProduct } from '../hooks/useProducts';
import { useProductBrochureImage } from '../hooks/useProductBrochureImage';
import ProductBrochureImageControl, {
  BrochureImageBadge,
  isImageAttachment,
} from './ProductBrochureImageControl';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';

function attachmentDirectoriesHref(directoryId: string | null | undefined): string {
  const base = '/resource-management/attachment-directories';
  if (directoryId) return `${base}?directoryId=${encodeURIComponent(directoryId)}`;
  return base;
}

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
  const [detailModalAttachmentId, setDetailModalAttachmentId] = useState<string | null>(null);
  const [manageLinksFor, setManageLinksFor] = useState<{ attachmentId: string; initialKeys: string[] } | null>(null);
  // Held as a pair so the dialog can name the file: the rows carry near-identical
  // filenames, and an id alone tells the user nothing about which one they hit.
  const [unlinkTarget, setUnlinkTarget] = useState<{ id: string; filename: string } | null>(null);

  // Fetch existing product attachments
  const { data: productAttachments, isLoading: isLoadingAttachments } = useProductAttachmentsByProduct(productId || null);
  const { data: productDetail } = useProduct(productId || null);
  const { data: fieldLinkageSchema } = useFieldLinkageSchema('product');
  const { data: accessTypes = [] } = useContactAccessTypes();
  const accessTypeNameByCode = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of accessTypes) m.set(t.code, t.name);
    return m;
  }, [accessTypes]);
  const downloadMutation = useDownloadAttachment();
  const deleteMutation = useDeleteProductAttachment();
  const {
    chosenAttachmentId,
    chooseBrochureImage,
    clearChosenBrochureImage,
    savingAttachmentId,
    isClearing,
  } = useProductBrochureImage(productId, productAttachments);

  // Build a per-attachment field-key list from the product's `field_attachments`
  // map. The map is keyed by field_key, so we invert it once.
  const fieldKeysByAttachmentId = useMemo(() => {
    const out = new Map<string, string[]>();
    const fa = productDetail?.field_attachments;
    if (!fa) return out;
    for (const [fieldKey, atts] of Object.entries(fa)) {
      for (const att of atts ?? []) {
        const arr = out.get(att.id) ?? [];
        if (!arr.includes(fieldKey)) arr.push(fieldKey);
        out.set(att.id, arr);
      }
    }
    return out;
  }, [productDetail]);

  // Map field_key -> human label from the registry; used to render badges.
  const fieldLabelByKey = useMemo(() => {
    const out = new Map<string, string>();
    for (const f of fieldLinkageSchema?.fields ?? []) {
      out.set(f.name, f.label);
    }
    return out;
  }, [fieldLinkageSchema]);

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
      // Keep UI quiet here; details/download remain available.
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
    const unique = Array.from(new Set(levels));
    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {unique.map((level) => (
          <Badge key={level} variant="secondary">
            {accessTypeNameByCode.get(level) ?? level}
          </Badge>
        ))}
      </div>
    );
  };

  const attachmentNeighbourItems = useMemo(
    () =>
      (productAttachments ?? [])
        .map((pa) => pa.attachment?.id)
        .filter(Boolean) as string[],
    [productAttachments]
  );

  // Group attachments by full_directory_path; use "Uncategorized" when null/empty
  const groupedByDirectory = useMemo(() => {
    if (!productAttachments || productAttachments.length === 0) return [];
    const groups = new Map<string, ProductAttachment[]>();
    for (const pa of productAttachments) {
      const path = pa.attachment?.full_directory_path?.trim() || null;
      const key = path || 'Uncategorized';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(pa);
    }
    // Sort: Uncategorized first, then alphabetically by path
    const entries = Array.from(groups.entries()).sort(([a], [b]) => {
      if (a === 'Uncategorized') return -1;
      if (b === 'Uncategorized') return 1;
      return a.localeCompare(b);
    });
    return entries;
  }, [productAttachments]);

  const renderAttachmentItem = (pa: ProductAttachment) => {
    const attachmentId = pa.attachment?.id;
    const fieldKeys = attachmentId ? (fieldKeysByAttachmentId.get(attachmentId) ?? []) : [];
    // Only an image can be the photo on a catalogue tile; a spec sheet there is
    // worse than no photo, so PDFs are never offered the control.
    const canBeBrochureImage = isImageAttachment(
      pa.attachment?.mime_type,
      pa.attachment?.original_filename,
    );
    // Compared against the one chosen id rather than read off the row, so two
    // rows can never render the mark at the same time. Not gated on the file
    // being an image: a flag that legacy data left on a PDF has to stay visible
    // and clearable, or the product is marked with nothing on screen saying so.
    const isBrochureImage = !!attachmentId && attachmentId === chosenAttachmentId;
    return (
    <div
      key={pa.id}
      data-testid={`product-attachment-row-${pa.id}`}
      className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {isBrochureImage && <BrochureImageBadge />}
        <div className="min-w-0 flex-1">
          <p className="font-medium text-sm break-words">
            {pa.attachment?.original_filename || 'Unknown'}
          </p>
          <p className="text-xs text-muted-foreground">
            {pa.attachment?.attachment_type?.type_name || 'No type'} •{' '}
            {formatFileSize(pa.attachment?.file_size_bytes)} •{' '}
            {pa.attachment?.uploaded_at && formatDate(new Date(pa.attachment.uploaded_at))}
          </p>
          {renderAccessLevels(pa.attachment?.access_levels ?? pa.access_levels)}
          {fieldKeys.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5" data-testid={`attachment-field-badges-${pa.id}`}>
              {fieldKeys.map((key) => (
                <Badge key={key} variant="primary" className="text-[10px]">
                  {fieldLabelByKey.get(key) ?? key}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1 sm:gap-2">
        {isEditMode && attachmentId && (canBeBrochureImage || isBrochureImage) && (
          <ProductBrochureImageControl
            isChosen={isBrochureImage}
            isSaving={savingAttachmentId === attachmentId}
            isClearing={isClearing}
            onChoose={() => chooseBrochureImage(attachmentId)}
            onClear={clearChosenBrochureImage}
          />
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => pa.attachment?.id && setDetailModalAttachmentId(pa.attachment.id)}
              title="View attachment details"
            >
              <FolderOpen className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>View attachment details</TooltipContent>
        </Tooltip>
        {isEditMode && attachmentId && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  setManageLinksFor({ attachmentId, initialKeys: fieldKeys })
                }
                data-testid={`manage-field-links-${pa.id}`}
              >
                <Settings2 className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Manage field links</TooltipContent>
          </Tooltip>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => pa.attachment?.id && handlePreview(pa.attachment.id)}
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
        {isEditMode && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Unlink attachment"
            title="Unlink attachment"
            onClick={() =>
              setUnlinkTarget({
                id: pa.id,
                filename: pa.attachment?.original_filename || 'this attachment',
              })
            }
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              <Trash2 className="size-4 text-destructive" />
            )}
          </Button>
        )}
      </div>
    </div>
    );
  };

  const renderDirectoryGroups = () => (
    <div className="space-y-3">
      {groupedByDirectory.map(([dirPath, items]) => {
        const directoryId = items[0]?.attachment?.directory_id ?? null;
        return (
        <Collapsible key={dirPath} defaultOpen>
          <div className="flex items-center gap-2 rounded-lg border bg-muted/50 overflow-hidden">
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="group flex flex-1 min-w-0 items-center gap-2 px-4 py-3 text-left hover:bg-muted transition-colors"
              >
                <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
                <Folder className="size-4 shrink-0 text-muted-foreground" />
                <span className="font-medium text-sm truncate">
                  {dirPath}
                </span>
                <Badge variant="secondary" className="ml-auto shrink-0">
                  {items.length} {items.length === 1 ? 'file' : 'files'}
                </Badge>
              </button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent>
            <div className="mt-2 space-y-2 pl-6 border-l-2 border-muted ml-2">
              {items.map((pa) => renderAttachmentItem(pa))}
            </div>
          </CollapsibleContent>
        </Collapsible>
        );
      })}
    </div>
  );

  if (!isEditMode) {
    return (
      <>
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
              renderDirectoryGroups()
            ) : (
              <p className="text-sm text-muted-foreground">
                No attachments linked to this product.
              </p>
            )}
          </CardContent>
        </Card>
        <AttachmentDetailModal
          open={detailModalAttachmentId != null}
          onOpenChange={(open) => !open && setDetailModalAttachmentId(null)}
          attachmentId={detailModalAttachmentId}
          neighbourItems={attachmentNeighbourItems.map((id) => ({ id }))}
          onAttachmentChange={setDetailModalAttachmentId}
        />
        {productId && manageLinksFor && (
          <ManageFieldLinksDialog
            open={manageLinksFor != null}
            onOpenChange={(open) => !open && setManageLinksFor(null)}
            productId={productId}
            attachmentId={manageLinksFor.attachmentId}
            initialFieldKeys={manageLinksFor.initialKeys}
            onSaved={() => {
              queryClient.invalidateQueries({ queryKey: ['product', productId] });
              setManageLinksFor(null);
            }}
          />
        )}
      </>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-6">
            <CardTitle>Attachments</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setLinkDialogOpen(true)}
            >
              <Plus className="size-4" />
              Link Attachment
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
            renderDirectoryGroups()
          ) : (
            <p className="text-sm text-muted-foreground">
              No attachments linked to this product. Upload a new attachment or link an existing one.
            </p>
          )}
        </CardContent>
      </Card>
      <LinkAttachmentBrowserDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        productId={productId}
      />
      <AttachmentDetailModal
        open={detailModalAttachmentId != null}
        onOpenChange={(open) => !open && setDetailModalAttachmentId(null)}
        attachmentId={detailModalAttachmentId}
        neighbourItems={attachmentNeighbourItems.map((id) => ({ id }))}
        onAttachmentChange={setDetailModalAttachmentId}
      />
      {productId && manageLinksFor && (
        <ManageFieldLinksDialog
          open={manageLinksFor != null}
          onOpenChange={(open) => !open && setManageLinksFor(null)}
          productId={productId}
          attachmentId={manageLinksFor.attachmentId}
          initialFieldKeys={manageLinksFor.initialKeys}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['product', productId] });
            setManageLinksFor(null);
          }}
        />
      )}
      <AlertDialog
        open={unlinkTarget != null}
        onOpenChange={(open) => !open && setUnlinkTarget(null)}
      >
        {/* Capped height because at 375px a long filename pushes the footer off
            screen, leaving the user with no way to cancel. */}
        <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>Unlink attachment?</AlertDialogTitle>
            <AlertDialogDescription>
              <span className="font-medium break-words">{unlinkTarget?.filename}</span> will no
              longer be attached to this product. This action cannot be undone. The file stays in
              Resource Management and can be linked again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                if (unlinkTarget) handleRemove(unlinkTarget.id);
                setUnlinkTarget(null);
              }}
              disabled={deleteMutation.isPending}
            >
              Unlink
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
