'use client';

/**
 * A salesperson's own files on a CRM request page (PORTAL-P4-REQUESTS P4-16): upload and remove
 * go through My Requests, as the portal does. Separate components so the hooks (and the
 * QueryClient they need) mount only in own-request mode.
 */

import { Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  useDeleteMyRequestAttachment,
  useUploadMyRequestAttachment,
} from '@/hooks/useMyRequests';
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

export function OwnAttachmentDelete({
  linkId,
  refreshKeys,
}: {
  linkId: string;
  refreshKeys: unknown[][];
}) {
  const remove = useDeleteMyRequestAttachment(refreshKeys);
  return (
    <Button
      type="button"
      variant="destructive"
      size="sm"
      disabled={remove.isPending}
      onClick={(e) => {
        e.stopPropagation();
        remove.mutate(linkId);
      }}
    >
      <Trash2 className="size-4" />
      Delete
    </Button>
  );
}
