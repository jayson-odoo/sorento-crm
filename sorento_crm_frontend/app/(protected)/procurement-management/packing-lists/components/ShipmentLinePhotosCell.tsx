'use client';

import { useMemo, useState } from 'react';
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
import { useUploadShipmentLinePhotos } from '@/app/(protected)/scm/hooks/useFulfilment';
import { type ShipmentLinePhoto } from '@/app/(protected)/scm/services/fulfilmentService';

/** Only images - the shared dropzone enforces this client-side, the backend's own
 *  image-extension guard (independent of the attachment type row, review round 1
 *  item 2) enforces it again server-side regardless of what an admin later widens
 *  the type's own `allowed_extensions` to. */
const IMAGE_ACCEPT = '.jpg,.jpeg,.png,.webp,.gif';

/** Thumbnails shown before the strip collapses into "+n" (R25). No cap on how many a
 *  line can HOLD (Q5) - this only bounds how many paint before the overflow badge. */
const VISIBLE_COUNT = 4;

/** Query key `useShipmentLinePhotos` (`useFulfilment.ts`) reads/invalidates - kept here
 *  too so the deferred-delete's `invalidateKeys` agrees with the read without importing
 *  the hooks file just for the key (this is a leaf cell, not a page). */
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
  const [uploadOpen, setUploadOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);

  // Upload goes through the hook layer (review round 1 item 7) - the toast and the
  // list invalidation both live in `useUploadShipmentLinePhotos` now, not here.
  const upload = useUploadShipmentLinePhotos(shipmentId);

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

  // `shipment_id`/`line_id` scope the deferred delete server-side (review round 1
  // item 1) - `EntityAttachmentLink` carries no company scope of its own, so the
  // handler asserts the photo actually belongs to THIS line before deleting it.
  const runDelete = (target: { id: string; filename: string | null }) =>
    removal.run({
      id: target.id,
      subject: target.filename ?? 'this photo',
      payload: { shipment_id: shipmentId, line_id: lineId },
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
    try {
      await upload.mutateAsync({ lineId, files: pendingFiles });
      closeUploadDialog(false);
    } catch {
      // The hook's own onError already toasted (review round 1 item 7) - the dialog
      // stays open so the picked files are not lost on a failed attempt.
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
                onClick={() => runDelete({ id: photo.id, filename: photo.filename })}
                disabled={removal.targetId === photo.id && removal.isPending}
                aria-label={`Delete ${photo.filename ?? 'photo'} for ${productLabel}`}
              >
                <X className="size-2.5" />
              </button>
            </div>
          ))}
          {overflow > 0 ? (
            <button
              type="button"
              className="shrink-0 rounded-full border bg-muted px-1.5 py-0.5 text-2xs font-medium text-muted-foreground hover:bg-muted/70"
              onClick={() => {
                setPreviewIndex(VISIBLE_COUNT);
                setPreviewOpen(true);
              }}
              aria-label={`View ${overflow} more photo(s) for ${productLabel}`}
            >
              +{overflow}
            </button>
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
            <Button variant="outline" onClick={() => closeUploadDialog(false)} disabled={upload.isPending}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={upload.isPending || pendingFiles.length === 0}>
              {upload.isPending ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Every photo is deletable from here (review round 1 item 8), including the
          overflow ones the "+n" badge does not render its own thumbnail for - the
          carousel already carries all of them (`previewItems` is the full list). */}
      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
        onDelete={(item) => runDelete({ id: item.id, filename: item.name })}
        deletingItemId={removal.targetId}
      />
    </>
  );
}

export default ShipmentLinePhotosCell;
