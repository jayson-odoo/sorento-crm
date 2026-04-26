'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, Eye, ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { getProductAttachmentsByProduct } from '@/app/(protected)/master-data-management/product-attachments/services/productAttachmentService';
import type { ProductAttachment } from '@/app/(protected)/master-data-management/product-attachments/types/productAttachment.types';
import {
  filterProductImageAttachments,
  filterTechnicalSpecAttachments,
} from '@/app/(protected)/commercial-management/quotation-revisions/lib/quotationProductImages';
import { cn } from '@/lib/utils';

function usePreviewUrl(attachmentId: string | null, enabled: boolean) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!attachmentId || !enabled) {
      setSrc(null);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setFailed(false);
    getAttachmentPreviewUrl(attachmentId)
      .then((url) => {
        if (!cancelled) setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [attachmentId, enabled]);

  return { src, failed };
}

function AttachmentThumb({
  attachmentId,
  filename,
  mimeType,
  className,
  onClick,
}: {
  attachmentId: string;
  filename: string;
  mimeType: string | null | undefined;
  className?: string;
  onClick?: () => void;
}) {
  const isImg = mimeType?.startsWith('image/');
  const { src, failed } = usePreviewUrl(attachmentId, Boolean(isImg));

  if (!isImg || failed || !src) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'flex size-16 shrink-0 items-center justify-center rounded-lg border border-[#e5e7eb] bg-[#f9fafb] text-[#6a7282]',
          className,
        )}
        aria-label={filename}
      >
        <ImageIcon className="size-6" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative size-16 shrink-0 overflow-hidden rounded-lg border border-[#e5e7eb] bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#e7000b]',
        className,
      )}
      aria-label={filename}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- signed/presigned URLs from API */}
      <img src={src} alt="" className="size-full object-cover" />
    </button>
  );
}

function LightboxImage({ attachmentId, open }: { attachmentId: string | null; open: boolean }) {
  const { src, failed } = usePreviewUrl(attachmentId, open && !!attachmentId);

  if (!open || !attachmentId) return null;

  return (
    <div className="flex max-h-[min(80vh,720px)] w-full items-center justify-center bg-black/5 p-4 pt-12">
      {failed || !src ? (
        <div className="text-muted-foreground text-sm">Preview unavailable.</div>
      ) : (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img src={src} alt="" className="max-h-[min(80vh,720px)] max-w-full object-contain" />
      )}
    </div>
  );
}

type Props = {
  productId: string | null | undefined;
  selectedAttachmentIds: string[];
  selectedTechnicalSpecIds?: string[];
  mode: 'view' | 'edit';
  onSelectionChange?: (ids: string[]) => void;
  onTechnicalSpecSelectionChange?: (ids: string[]) => void;
};

export function QuotationLineProductImages({
  productId,
  selectedAttachmentIds,
  selectedTechnicalSpecIds = [],
  mode,
  onSelectionChange,
  onTechnicalSpecSelectionChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [lightboxId, setLightboxId] = useState<string | null>(null);
  const downloadMut = useDownloadAttachment();

  const { data: productAttachments = [], isFetching } = useQuery({
    queryKey: ['quotation-line-product-images', productId],
    queryFn: () => getProductAttachmentsByProduct(productId!),
    enabled: Boolean(productId && open),
    staleTime: 60_000,
  });

  const imageRows = useMemo(() => filterProductImageAttachments(productAttachments), [productAttachments]);
  const technicalRows = useMemo(() => filterTechnicalSpecAttachments(productAttachments), [productAttachments]);

  const selectedSet = useMemo(() => new Set(selectedAttachmentIds), [selectedAttachmentIds]);
  const selectedTechnicalSet = useMemo(() => new Set(selectedTechnicalSpecIds), [selectedTechnicalSpecIds]);

  const toggle = (row: ProductAttachment) => {
    const id = row.attachment_id;
    if (!id || !onSelectionChange) return;
    const next = new Set(selectedAttachmentIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(Array.from(next));
  };
  const toggleTechnical = (row: ProductAttachment) => {
    const id = row.attachment_id;
    if (!id || !onTechnicalSpecSelectionChange) return;
    const next = new Set(selectedTechnicalSpecIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onTechnicalSpecSelectionChange(Array.from(next));
  };

  const handleDownload = async (attachmentId: string, filename: string) => {
    try {
      const blob = await downloadMut.mutateAsync(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      /* mutation toasts */
    }
  };

  const handleEye = async (attachmentId: string) => {
    try {
      const url = await getAttachmentPreviewUrl(attachmentId);
      if (url) window.open(url, '_blank', 'noopener,noreferrer');
    } catch {
      /* quiet */
    }
  };

  if (!productId?.trim()) return null;

  const count = selectedAttachmentIds.length + selectedTechnicalSpecIds.length;

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="relative inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-[#e5e7eb] bg-white text-[#6a7282] shadow-sm transition-colors hover:bg-[#f9fafb] hover:text-[#101828]"
            aria-label="Product images and technical specs"
          >
            <ImageIcon className="size-4" />
            {count > 0 ? (
              <span className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#22c55e] px-1 text-[10px] font-semibold leading-none text-white">
                {count > 99 ? '99+' : count}
              </span>
            ) : null}
          </button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[min(100vw-2rem,400px)] border-[#e5e7eb] p-0 shadow-lg"
          align="start"
          sideOffset={6}
        >
          <div className="border-b border-[#e5e7eb] px-4 py-3">
            <p className="text-sm font-semibold text-[#101828]">Product attachments</p>
          </div>

          <div className="max-h-[min(360px,50vh)] overflow-y-auto px-4 py-3">
            {isFetching ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[#6a7282]">Product images</p>
                  {imageRows.length === 0 ? (
                    <p className="text-muted-foreground text-sm">No Product Image attachments.</p>
                  ) : (
                    <ul className="flex flex-col gap-3">
                      {imageRows.map((row) => {
                        const att = row.attachment;
                        if (!att?.id) return null;
                        const id = row.attachment_id;
                        const name = att.original_filename || 'File';
                        const selected = selectedSet.has(id);

                        return (
                          <li
                            key={row.id}
                            className={cn(
                              'flex gap-3 rounded-xl border border-[#e5e7eb] bg-[#fafafa] p-2',
                              selected && 'border-[#bbf7d0] bg-[#f0fdf4]',
                            )}
                          >
                            <AttachmentThumb
                              attachmentId={att.id}
                              filename={name}
                              mimeType={att.mime_type}
                              onClick={() => setLightboxId(att.id)}
                            />
                            <div className="flex min-w-0 flex-1 flex-col gap-1">
                              <div className="flex items-start gap-2">
                                {mode === 'edit' ? (
                                  <div className="flex items-center gap-2 pt-0.5">
                                    <Checkbox
                                      id={`img-${row.id}`}
                                      checked={selected}
                                      onCheckedChange={() => toggle(row)}
                                    />
                                    <Label htmlFor={`img-${row.id}`} className="cursor-pointer text-xs font-normal text-[#4a5565]">
                                      On quotation
                                    </Label>
                                  </div>
                                ) : (
                                  <span
                                    className={cn(
                                      'rounded-full px-2 py-0.5 text-[10px] font-medium',
                                      selected ? 'bg-[#dcfce7] text-[#166534]' : 'bg-[#f3f4f6] text-[#6a7282]',
                                    )}
                                  >
                                    {selected ? 'Selected' : 'Not selected'}
                                  </span>
                                )}
                              </div>
                              <p className="truncate text-xs font-medium text-[#101828]" title={name}>
                                {name}
                              </p>
                              <div className="flex flex-wrap gap-1">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 gap-1 px-2 text-xs text-[#e7000b]"
                                  onClick={() => void handleEye(att.id)}
                                >
                                  <Eye className="size-3.5" />
                                  Preview
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 gap-1 px-2 text-xs text-[#4a5565]"
                                  onClick={() => void handleDownload(att.id, name)}
                                  disabled={downloadMut.isPending}
                                >
                                  <Download className="size-3.5" />
                                  Download
                                </Button>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[#6a7282]">Technical spec</p>
                  {technicalRows.length === 0 ? (
                    <p className="text-muted-foreground text-sm">No Technical Spec attachments.</p>
                  ) : (
                    <ul className="flex flex-col gap-3">
                      {technicalRows.map((row) => {
                        const att = row.attachment;
                        if (!att?.id) return null;
                        const id = row.attachment_id;
                        const name = att.original_filename || 'File';
                        const selected = selectedTechnicalSet.has(id);

                        return (
                          <li
                            key={`spec-${row.id}`}
                            className={cn(
                              'flex gap-3 rounded-xl border border-[#e5e7eb] bg-[#fafafa] p-2',
                              selected && 'border-[#bbf7d0] bg-[#f0fdf4]',
                            )}
                          >
                            <AttachmentThumb
                              attachmentId={att.id}
                              filename={name}
                              mimeType={att.mime_type}
                              onClick={() => setLightboxId(att.id)}
                            />
                            <div className="flex min-w-0 flex-1 flex-col gap-1">
                              <div className="flex items-start gap-2">
                                {mode === 'edit' ? (
                                  <div className="flex items-center gap-2 pt-0.5">
                                    <Checkbox
                                      id={`spec-${row.id}`}
                                      checked={selected}
                                      onCheckedChange={() => toggleTechnical(row)}
                                    />
                                    <Label htmlFor={`spec-${row.id}`} className="cursor-pointer text-xs font-normal text-[#4a5565]">
                                      On quotation
                                    </Label>
                                  </div>
                                ) : (
                                  <span
                                    className={cn(
                                      'rounded-full px-2 py-0.5 text-[10px] font-medium',
                                      selected ? 'bg-[#dcfce7] text-[#166534]' : 'bg-[#f3f4f6] text-[#6a7282]',
                                    )}
                                  >
                                    {selected ? 'Selected' : 'Not selected'}
                                  </span>
                                )}
                              </div>
                              <p className="truncate text-xs font-medium text-[#101828]" title={name}>
                                {name}
                              </p>
                              <div className="flex flex-wrap gap-1">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 gap-1 px-2 text-xs text-[#e7000b]"
                                  onClick={() => void handleEye(att.id)}
                                >
                                  <Eye className="size-3.5" />
                                  Preview
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 gap-1 px-2 text-xs text-[#4a5565]"
                                  onClick={() => void handleDownload(att.id, name)}
                                  disabled={downloadMut.isPending}
                                >
                                  <Download className="size-3.5" />
                                  Download
                                </Button>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>

      <Dialog open={Boolean(lightboxId)} onOpenChange={(o) => !o && setLightboxId(null)}>
        <DialogContent className="max-w-[min(95vw,900px)] border-0 p-0 sm:max-w-[min(95vw,900px)]" showCloseButton>
          <LightboxImage attachmentId={lightboxId} open={Boolean(lightboxId)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
