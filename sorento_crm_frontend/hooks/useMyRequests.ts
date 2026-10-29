'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  fetchRevisions,
  uploadAttachment,
  downloadMyRequestAttachment,
  approveMyPriceTagRequest,
  collectMyPriceTagRequest,
  createMyPriceTagRequest,
  downloadMyPriceTagPdf,
  fetchMyPriceTagDebtors,
  fetchMyPriceTagRequest,
  requestMyPriceTagChanges,
  reviseMyPriceTagRequest,
  submitMyPriceTagRequest,
  updateMyPriceTagRequest,
  type MyPriceTagLineWrite,
  type MyPriceTagWrite,
  type MyRequestAttachmentKind,
  type MyRequestKind,
} from '@/services/myRequestsService';
import type { ChangeRequestPayload } from '@/lib/dealer-kit/review-comments';

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

// ---------------------------------------------------------------- Price Tag Request (S7)

/** Their own price tag request as the portal answers it (the detail body plus its revision policy). */
export function useMyPriceTagRequest(id: string | null | undefined) {
  return useQuery({
    queryKey: [MY_REQUEST_KEY, 'price_tag_request', id],
    queryFn: () => fetchMyPriceTagRequest(id as string),
    enabled: Boolean(id),
  });
}

/** The debtors the portal's picker offers them: every agent their contact is linked to. */
export function useMyPriceTagDebtors(enabled: boolean) {
  return useQuery({
    queryKey: [MY_REQUEST_KEY, 'price_tag_request', 'debtors'],
    queryFn: fetchMyPriceTagDebtors,
    enabled,
    staleTime: 60_000,
  });
}

/**
 * A salesperson's own price tag request written through the portal's price tag router (S7): save,
 * submit, approve the proof, ask for changes, download the PDF, collect, revise. Deleting a draft is
 * the deferred `my_request.delete` (`MyRequestActions`). The staff table and request page read the
 * same rows, so their keys refresh.
 */
export function useMyPriceTagMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: [MY_REQUEST_KEY, 'price_tag_request'] });
  };
  const move = (fallback: string, done?: string) => ({
    onSuccess: () => {
      refresh();
      if (done) toast.success(done);
    },
    onError: (error: Error) => toast.error(error.message || fallback),
  });
  const create = useMutation({
    mutationFn: (data: MyPriceTagWrite) => createMyPriceTagRequest(data),
    ...move('Failed to save the price tag request'),
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: MyPriceTagWrite }) => updateMyPriceTagRequest(id, data),
    ...move('Failed to save the price tag request'),
  });
  const submit = useMutation({
    mutationFn: (id: string) => submitMyPriceTagRequest(id),
    ...move('Failed to submit the price tag request', 'Submitted'),
  });
  const approve = useMutation({
    mutationFn: (id: string) => approveMyPriceTagRequest(id),
    ...move('Failed to approve the proof', 'Proof approved'),
  });
  const requestChanges = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ChangeRequestPayload }) =>
      requestMyPriceTagChanges(id, payload),
    ...move('Failed to send the change requests', 'Change requests sent'),
  });
  const download = useMutation({
    mutationFn: (id: string) => downloadMyPriceTagPdf(id),
    onError: (error: Error) => toast.error(error.message || 'Failed to download the PDF'),
  });
  const collect = useMutation({
    mutationFn: (id: string) => collectMyPriceTagRequest(id),
    ...move('Failed to mark collected', 'Marked collected'),
  });
  const revise = useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: { reason: string; expectedRevisionNo: number; fields: Record<string, unknown>; products: MyPriceTagLineWrite[] };
    }) => reviseMyPriceTagRequest(id, input),
    ...move('Failed to send the revision', 'Revision sent'),
  });
  return { create, update, submit, approve, requestChanges, download, collect, revise };
}
