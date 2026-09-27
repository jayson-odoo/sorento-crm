'use client';

import { useId, useMemo, useState } from 'react';
import { Paperclip, X } from 'lucide-react';
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
import { SO_LINE_ATTACHMENTS_KEY, useUploadSoLineAttachments } from '../hooks/useSoLineAttachments';
import { type SoLineAttachment } from '../services/soLineAttachmentService';

/** Q3 (grill, recommended answer): images, PDF, Excel - what #1311's manual mails
 *  already carry. Same list the backend's own hardcoded gate enforces
 *  (`app/services/so_line_attachments.py::_ALLOWED_EXTS`). */
const ACCEPT = '.jpg,.jpeg,.png,.webp,.gif,.pdf,.xlsx,.xls';

function formatSize(bytes: number | null): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface SoLineAttachmentsButtonProps {
  /** The CORE `sales_order_lines.id` this line's files key on (Q1) - never shown. */
  lineId: string;
  /** What the reader calls this line ("SO423136 L3 SRTWCY8605-PJ") - the dialog
   *  title and every aria-label read this, never the line's own uuid. */
  label: string;
  attachments: SoLineAttachment[];
  /** `projects.projects.edit` (Q6) - a viewer sees the list with no drop zone and no x. */
  canEdit: boolean;
}

/**
 * The paperclip + lightbox for a sales-order line's own clarification files (#1312,
 * PLAN-oi-line-attachments-27sep.md, AC-U1..U5). Reuses the shared `Dialog` +
 * `FileDropzone` + `AttachmentPreviewModal` shape `ShipmentLinePhotosCell.tsx`
 * already ships, not a new upload surface.
 *
 * No animation of its own (AC-U7, frequency gate: tens of uses a day) - the icon is
 * a plain ghost button, and the lightbox is the shared Dialog spring.
 *
 * The button itself calls no react-query hook - only `SoLineAttachmentsDialog` below
 * does, and it mounts only once the paperclip has been clicked at least ONCE (same
 * pattern `DecisionTrailButton`'s own dialog uses, for the same reason: this button
 * is rendered per row on the fulfilment board's list view AND the order inquiry
 * Lines tab, both of which are unit-tested with the row/cell in isolation and no
 * `QueryClientProvider` in scope - a row whose paperclip nobody has clicked must not
 * need one just because this button exists on the row).
 *
 * Fix round 1 should-fix 4: once opened, `SoLineAttachmentsDialog` stays MOUNTED
 * even after the reader closes it (`everOpened`, never un-set) - only its own
 * `open` prop toggles the Radix dialog's visibility. Unmounting it on close used to
 * tear down `useDeferredRowAction`'s own hook instance mid-countdown, which
 * (`useDeferredAction`'s own unmount effect) explicitly dismisses every toast that
 * instance raised and stops watching for the commit - so closing the lightbox
 * during the 10s window silently killed the Cancel toast AND the refresh the
 * eventual commit was supposed to trigger, even though the delete itself still
 * happened on the server a few seconds later.
 */
export function SoLineAttachmentsButton({
  lineId,
  label,
  attachments,
  canEdit,
}: SoLineAttachmentsButtonProps) {
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  // Nit (fix round 1): the count badge is visual only (`aria-hidden` below) - a
  // screen reader gets it too, via `aria-describedby` onto this hidden span, WITHOUT
  // changing the button's own accessible NAME (`aria-label` always wins name
  // computation over content, so this could not reach it that way regardless) - the
  // pinned aria-label test asserts the exact string `Attachments for ${label}`.
  const countId = useId();

  return (
    <>
      <span className="relative inline-flex shrink-0">
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          className="shrink-0"
          aria-label={`Attachments for ${label}`}
          aria-describedby={attachments.length > 0 ? countId : undefined}
          title="Attachments"
          onClick={(event) => {
            // The row itself is often a clickable surface (the board list, AC-U1) -
            // this button sits on top of it and must not trigger it too.
            event.stopPropagation();
            setEverOpened(true);
            setOpen(true);
          }}
        >
          <Paperclip className="size-3.5" aria-hidden />
        </Button>
        {attachments.length > 0 ? (
          <>
            <span
              className="pointer-events-none absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-2xs font-medium text-primary-foreground"
              aria-hidden
            >
              {attachments.length > 99 ? '99+' : attachments.length}
            </span>
            <span id={countId} className="sr-only">
              {attachments.length} {attachments.length === 1 ? 'file' : 'files'}
            </span>
          </>
        ) : null}
      </span>

      {everOpened ? (
        <SoLineAttachmentsDialog
          lineId={lineId}
          label={label}
          attachments={attachments}
          canEdit={canEdit}
          open={open}
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}

/**
 * The lightbox itself - the list, the drop zone, the upload/delete mutations. Split
 * out of `SoLineAttachmentsButton` above (see its own docstring) so those mutation
 * hooks (both call `useQueryClient()` unconditionally) never run for a row whose
 * paperclip nobody has clicked.
 */
function SoLineAttachmentsDialog({
  lineId,
  label,
  attachments,
  canEdit,
  open,
  onOpenChange,
}: SoLineAttachmentsButtonProps & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);

  const upload = useUploadSoLineAttachments();

  // Hard delete, no confirmation dialog (D7, Q8): the x parks the delete on the
  // server for the grace window and a toast carries the countdown.
  const removal = useDeferredRowAction({
    actionKey: 'sales_order_line_attachment.delete',
    entityType: 'sales_order_line_attachment',
    verb: 'Deleting',
    successMessage: 'Attachment deleted',
    invalidateKeys: [SO_LINE_ATTACHMENTS_KEY],
  });

  const runDelete = (target: { id: string; filename: string | null }) =>
    removal.run({
      id: target.id,
      subject: target.filename ?? 'this file',
      payload: { line_id: lineId },
    });

  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      attachments.map((att) => ({
        id: att.id,
        name: att.filename ?? 'File',
        url: att.url ?? '',
        downloadUrl: att.attachment_id
          ? `/api/v1/resource-management/attachments/${att.attachment_id}/download`
          : undefined,
        sizeBytes: att.size_bytes,
      })),
    [attachments],
  );

  const closeDialog = (next: boolean) => {
    onOpenChange(next);
    if (!next) setPendingFiles([]);
  };

  const handleUpload = async () => {
    if (pendingFiles.length === 0) return;
    try {
      await upload.mutateAsync({ lineId, files: pendingFiles });
      setPendingFiles([]);
    } catch {
      // The hook's own onError already toasted - the dialog stays open so the
      // picked files are not lost on a failed attempt.
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={closeDialog}>
        <DialogContent onClick={(event) => event.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
          </DialogHeader>
          {/* AC-U7: scrollable body, Upload stays reachable at 375px. dvh, not vh
              (M6-02/M6-03): vh overshoots mobile Safari's visible area. */}
          <div className="max-h-[60dvh] space-y-3 overflow-y-auto">
            {attachments.length === 0 ? (
              <p className="text-sm text-muted-foreground">No files on this line yet.</p>
            ) : (
              <ul className="space-y-1.5">
                {attachments.map((att, index) => (
                  <li
                    key={att.id}
                    className="flex items-center gap-2 rounded-md border border-border px-3 py-2"
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => {
                        setPreviewIndex(index);
                        setPreviewOpen(true);
                      }}
                    >
                      <p className="truncate text-sm font-medium" title={att.filename ?? ''}>
                        {att.filename ?? 'File'}
                      </p>
                      <p className="text-xs text-muted-foreground">{formatSize(att.size_bytes)}</p>
                    </button>
                    {canEdit ? (
                      <Button
                        type="button"
                        mode="icon"
                        variant="ghost"
                        size="sm"
                        disabled={removal.targetId === att.id && removal.isPending}
                        aria-label={`Delete ${att.filename ?? 'this file'}`}
                        onClick={() => runDelete(att)}
                      >
                        <X className="size-3.5" aria-hidden />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}

            {canEdit ? (
              <FileDropzone
                accept={ACCEPT}
                multiple
                maxSizeMb={10}
                files={pendingFiles}
                onFilesChange={setPendingFiles}
                onReject={(file, reason) =>
                  toast.error(
                    reason === 'type'
                      ? `${file.name} is not a supported file type.`
                      : reason === 'size'
                        ? `${file.name} is too large.`
                        : 'Too many files at once.',
                  )
                }
                title="Drop files here"
                hint="Images, PDF or Excel"
                aria-label={`Files to add for ${label}`}
              />
            ) : null}
          </div>
          {canEdit ? (
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => closeDialog(false)}
                disabled={upload.isPending}
              >
                Close
              </Button>
              <Button
                type="button"
                onClick={handleUpload}
                disabled={upload.isPending || pendingFiles.length === 0}
              >
                {upload.isPending ? 'Uploading...' : 'Upload'}
              </Button>
            </DialogFooter>
          ) : null}
        </DialogContent>
      </Dialog>

      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
        onDelete={canEdit ? (item) => runDelete({ id: item.id, filename: item.name }) : undefined}
        deletingItemId={removal.targetId}
      />
    </>
  );
}

export default SoLineAttachmentsButton;
