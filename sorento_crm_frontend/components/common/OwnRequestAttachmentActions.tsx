'use client';

/**
 * A salesperson's own files on a CRM request page (PORTAL-P4-REQUESTS P4-16): upload and download
 * go through My Requests, as the portal does; remove parks `my_request_attachment.unlink` (D7),
 * which runs the portal's own unlink when its window lapses. Separate components so the hooks (and
 * the QueryClient they need) mount only in own-request mode.
 */

import { Download, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useDownloadMyRequestAttachment, useUploadMyRequestAttachment } from '@/hooks/useMyRequests';
import type { MyRequestAttachmentKind } from '@/services/myRequestsService';

export function OwnAttachmentUpload({
  kind,
  requestId,
  refreshKeys,
}: {
  kind: MyRequestAttachmentKind;
  requestId: string;
  refreshKeys: unknown[][];
}) {
  const upload = useUploadMyRequestAttachment(kind, refreshKeys);
  return (
    <Button asChild disabled={upload.isPending}>
      <label className="cursor-pointer">
        <Upload className="size-4" />
        Upload file
        <input
          type="file"
          aria-label="Upload file"
          className="sr-only"
          disabled={upload.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file) upload.mutate({ submissionId: requestId, file });
          }}
        />
      </label>
    </Button>
  );
}

/** Download as a fetch, not a link: an admin viewing as them must send the impersonation header. */
export function OwnAttachmentDownload({
  attachmentId,
  filename,
}: {
  attachmentId: string;
  filename: string;
}) {
  const download = useDownloadMyRequestAttachment();
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={download.isPending}
      onClick={(e) => {
        e.stopPropagation();
        download.mutate({ attachmentId, filename });
      }}
    >
      <Download className="size-4" />
      Download
    </Button>
  );
}

export function OwnAttachmentDelete({
  linkId,
  refreshKeys,
}: {
  linkId: string;
  refreshKeys: unknown[][];
}) {
  const remove = useDeferredAction({
    actionKey: 'my_request_attachment.unlink',
    entityType: 'my_request_attachment',
    entityId: linkId,
    verb: 'Removing',
    subject: '',
    surface: 'inline',
    // Only their own uploads carry this, a handful per request: each reads `current` from mount,
    // so a countdown started before a reload (or in another tab) still shows on its row.
    watchFromMount: true,
    successMessage: 'File removed',
    invalidateKeys: refreshKeys,
  });
  return (
    <DeferredActionButton
      pending={remove.pending}
      verb="Removing"
      onCancel={remove.cancel}
      // A table cell: the countdown's own minimum width overflows one.
      className="min-w-0"
      idle={
        <Button
          type="button"
          variant="destructive"
          size="sm"
          disabled={remove.isPending || remove.isBlocked}
          onClick={(e) => {
            e.stopPropagation();
            remove.start();
          }}
        >
          <Trash2 className="size-4" />
          Delete
        </Button>
      }
    />
  );
}
