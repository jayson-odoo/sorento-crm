'use client';

import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { toast } from '@/lib/toast';
import {
  uploadShipmentLinePhotos,
  type ShipmentLinePhoto,
} from '../../../scm/services/fulfilmentService';

/** Only images - the shared dropzone enforces this client-side, the backend's own
 *  attachment-type extensions (Phase 2) enforce it again server-side. */
const IMAGE_ACCEPT = '.jpg,.jpeg,.png,.webp,.gif';

/** Thumbnails shown before the strip collapses into "+n" (R25). No cap on how many a
 *  line can HOLD (Q5) - this only bounds how many paint before the overflow badge. */
const VISIBLE_COUNT = 4;

/** Query key `useShipmentLinePhotos` (`useFulfilment.ts`) reads/invalidates - kept here
 *  too so the upload success path and the deferred-delete's `invalidateKeys` agree with
 *  the read without importing the hooks file (this is a leaf cell, not a page). */
export function shipmentLinePhotosQueryKey(shipmentId: string | null) {
  return ['scm', 'fulfilment', 'line-photos', shipmentId] as const;
}

interface ShipmentLinePhotosCellProps {
  shipmentId: string;
  /** Null for a draft line that has never been saved - there is nowhere to upload to
   *  until the line has a real id. */
  lineId: string | null;
  /** What the reader calls this line ("SRTWC286-SH"), for aria-labels and the dialog
   *  title - never the line's uuid (no UUIDs in the UI). */
  productLabel: string;
  photos: ShipmentLinePhoto[];
}

export function ShipmentLinePhotosCell({
  shipmentId,
  lineId,
  productLabel,
  photos,
}: ShipmentLinePhotosCellProps) {
  const queryClient = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);

  // Hard delete, no confirmation dialog (D7): the "x" parks the delete on the server
  // for the grace window and a toast carries the countdown - matches the convention
  // this codebase's own CLAUDE.md and every other list (message snippets, supplier
  // code aliases, translation memory) already use, in place of the plan text's
  // `ConfirmDeleteDialog` (retired). See `## Deviations (lane C)`.
  const removal = useDeferredRowAction({
    actionKey: 'shipment_line_photo.delete',
    entityType: 'shipment_line_photo',
    verb: 'Deleting',
    successMessage: 'Photo deleted',
    invalidateKeys: [shipmentLinePhotosQueryKey(shipmentId)],
  });

  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      photos.map((photo) => ({
        id: photo.id,
        name: photo.filename ?? 'Photo',
        url: photo.url ?? '',
        downloadUrl: photo.attachment_id
          ? `/api/v1/resource-management/attachments/${photo.attachment_id}/download`
          : undefined,
      })),
    [photos],
  );

  const visible = photos.slice(0, VISIBLE_COUNT);
  const overflow = photos.length - visible.length;

  const closeUploadDialog = (open: boolean) => {
    setUploadOpen(open);
    if (!open) setPendingFiles([]);
  };

  const handleUpload = async () => {
    if (!lineId || pendingFiles.length === 0) return;
    setUploading(true);
    try {
      await uploadShipmentLinePhotos(shipmentId, lineId, pendingFiles);
      await queryClient.invalidateQueries({ queryKey: shipmentLinePhotosQueryKey(shipmentId) });
      toast.success(pendingFiles.length === 1 ? 'Photo added' : `${pendingFiles.length} photos added`);
      closeUploadDialog(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to upload photos');
    } finally {
      setUploading(false);
    }
  };

  if (!lineId) {
    return <span className="text-xs text-muted-foreground">Save the line first</span>;
  }

  return (
    <>
      <div className="flex items-center gap-1">
        {/* Only the strip scrolls (375px, AC-L1) - the fixed max-width keeps it inside
            this cell rather than widening the column, and the "+" stays reachable. */}
        <div className="flex max-w-[140px] items-center gap-1 overflow-x-auto">
          {visible.map((photo, index) => (
            <div key={photo.id} className="group relative shrink-0">
              <button
                type="button"
                className="block size-9 shrink-0 overflow-hidden rounded border bg-muted"
                onClick={() => {
                  setPreviewIndex(index);
                  setPreviewOpen(true);
                }}
                aria-label={`View ${photo.filename ?? 'photo'} for ${productLabel}`}
              >
                {photo.thumbnail_url ? (
                  <img
                    src={photo.thumbnail_url}
                    alt=""
                    className="size-full object-cover"
                  />
                ) : null}
              </button>
              <button
                type="button"
                className="absolute -right-1 -top-1 hidden size-4 items-center justify-center rounded-full bg-destructive text-destructive-foreground group-hover:flex disabled:opacity-50"
                onClick={() =>
                  removal.run({ id: photo.id, subject: photo.filename ?? 'this photo' })
                }
                disabled={removal.targetId === photo.id && removal.isPending}
                aria-label={`Delete ${photo.filename ?? 'photo'} for ${productLabel}`}
              >
                <X className="size-2.5" />
              </button>
            </div>
          ))}
          {overflow > 0 ? (
            <span className="shrink-0 text-xs text-muted-foreground">+{overflow}</span>
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          onClick={() => setUploadOpen(true)}
          aria-label={`Add photos for ${productLabel}`}
        >
          <Plus className="size-4" />
        </Button>
      </div>

      <Dialog open={uploadOpen} onOpenChange={closeUploadDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add photos - {productLabel}</DialogTitle>
          </DialogHeader>
          <FileDropzone
            accept={IMAGE_ACCEPT}
            multiple
            files={pendingFiles}
            onFilesChange={setPendingFiles}
            onReject={(file, reason) =>
              toast.error(
                reason === 'type'
                  ? `${file.name} is not an image.`
                  : reason === 'size'
                    ? `${file.name} is too large.`
                    : 'Too many files at once.',
              )
            }
            title="Drop photos here"
            hint="JPG, PNG, WEBP or GIF"
            aria-label={`Photos to add for ${productLabel}`}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => closeUploadDialog(false)} disabled={uploading}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={uploading || pendingFiles.length === 0}>
              {uploading ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
      />
    </>
  );
}

export default ShipmentLinePhotosCell;
