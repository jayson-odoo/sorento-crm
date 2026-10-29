'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  fetchRevisions,
  uploadAttachment,
  downloadMyRequestAttachment,
  type MyRequestAttachmentKind,
  type MyRequestKind,
} from '@/services/myRequestsService';

/**
 * A salesperson's own request, read and written through My Requests (PORTAL-P4-REQUESTS): the
 * portal's own rules (drafts, submit, revise), over the CRM session. Every write refreshes the
 * staff page's own queries too, since that is the page they are on.
 */
export const MY_REQUEST_KEY = 'my-request';

/** Their own request's revision lineage, keyed on its revision counter like the staff reads. */
export function useMyRequestRevisions(
  kind: MyRequestKind,
  id: string | null | undefined,
  revisionNo?: number | null,
) {
  return useQuery({
    queryKey: [MY_REQUEST_KEY, kind, id, 'revisions', revisionNo ?? 0],
    queryFn: () => fetchRevisions(kind, id as string),
    enabled: Boolean(id),
  });
}

/** Save a file of their own request (`downloadMyRequestAttachment`). */
export function useDownloadMyRequestAttachment() {
  return useMutation({
    mutationFn: ({ attachmentId, filename }: { attachmentId: string; filename: string }) =>
      downloadMyRequestAttachment(attachmentId, filename),
    onError: (error: Error) => toast.error(error.message || 'Download failed.'),
  });
}

/** Add a file to their own request through the generic portal upload; `refreshKeys` are the
 *  staff page's queries that show it. */
export function useUploadMyRequestAttachment(kind: MyRequestAttachmentKind, refreshKeys: unknown[][]) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ submissionId, file }: { submissionId: string; file: File }) =>
      uploadAttachment(kind, submissionId, file),
    onSuccess: () => {
      for (const key of refreshKeys) void queryClient.invalidateQueries({ queryKey: key });
      toast.success('File added');
    },
    onError: (error: Error) => toast.error(error.message || 'Upload failed.'),
  });
}
