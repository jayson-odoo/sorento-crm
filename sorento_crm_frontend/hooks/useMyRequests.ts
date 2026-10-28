'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  cancelMyNewProductApplication,
  cancelMySampleRequest,
  createMyNewProductApplication,
  createMySampleRequest,
  deleteDraftSubmission,
  fetchRevisions,
  fetchSubmission,
  reviseSubmission,
  saveDraft,
  submitDraft,
  fetchMyNewProductApplicationPrefill,
  reviseMyNewProductApplication,
  submitMyNewProductApplication,
  submitMySampleRequest,
  updateMyNewProductApplication,
  uploadAttachment,
  deleteAttachment,
  updateMySampleRequest,
  approveMyPriceTagRequest,
  collectMyPriceTagRequest,
  createMyPriceTagRequest,
  deleteMyPriceTagRequest,
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
  type ReviseSubmissionInput,
} from '@/services/myRequestsService';
import type { SampleRequestWrite } from '@/types/sampleRequest';
import type { NewProductApplicationWrite } from '@/types/newProductApplication';
import type { ChangeRequestPayload } from '@/lib/dealer-kit/review-comments';

/**
 * A salesperson's own request, read and written through My Requests (PORTAL-P4-REQUESTS): the
 * portal's own rules (drafts, submit, revise), over the CRM session. Every write refreshes the
 * staff page's own queries too, since that is the page they are on.
 */
export const MY_REQUEST_KEY = 'my-request';

export function useMyRequestSubmission(kind: MyRequestKind, id: string | null | undefined) {
  return useQuery({
    queryKey: [MY_REQUEST_KEY, kind, id],
    queryFn: () => fetchSubmission(kind, id as string),
    enabled: Boolean(id),
  });
}

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

function useRefresh(kind: MyRequestKind) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [MY_REQUEST_KEY, kind] });
    // The staff list / detail / revisions of the same form read these rows too.
    void queryClient.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === 'string' && q.queryKey[0].startsWith(kind.replace('_', '-')),
    });
  };
}

type Fields = Record<string, unknown>;
type Products = Record<string, unknown>[] | undefined;

export function useSaveMyRequestDraft(kind: MyRequestKind) {
  const refresh = useRefresh(kind);
  return useMutation({
    mutationFn: ({ fields, products, id }: { fields: Fields; products?: Products; id?: string }) =>
      saveDraft(kind, fields, products, id),
    onSuccess: () => {
      refresh();
      toast.success('Draft saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save draft.'),
  });
}

/** Submit a draft (or a rejected row); an existing row's edits travel with the submit. */
export function useSubmitMyRequest(kind: MyRequestKind) {
  const refresh = useRefresh(kind);
  return useMutation({
    mutationFn: async ({ fields, products, id }: { fields?: Fields; products?: Products; id?: string }) => {
      const target = id ?? (await saveDraft(kind, fields ?? {}, products)).id;
      return submitDraft(kind, String(target), fields, products);
    },
    onSuccess: () => {
      refresh();
      toast.success('Submitted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to submit.'),
  });
}

export function useReviseMyRequest(kind: MyRequestKind) {
  const refresh = useRefresh(kind);
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: ReviseSubmissionInput }) =>
      reviseSubmission(kind, id, input),
    onSuccess: () => {
      refresh();
      toast.success('Revision sent');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to send revision.'),
  });
}

export function useDeleteMyRequestDraft(kind: MyRequestKind) {
  const refresh = useRefresh(kind);
  return useMutation({
    mutationFn: (id: string) => deleteDraftSubmission(kind, id),
    onSuccess: () => {
      refresh();
      toast.success('Draft deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete draft.'),
  });
}

/**
 * A salesperson's own sample request written through the portal's sample request router (S4):
 * the staff page's create / update / submit, plus the portal's Cancel. The staff list and detail
 * read the same rows, so their keys refresh.
 */
export function useMySampleRequestMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['sample-requests'] });
    void queryClient.invalidateQueries({ queryKey: ['sample-request'] });
  };
  const fail = (fallback: string) => (error: Error) => toast.error(error.message || fallback);

  const create = useMutation({
    mutationFn: (data: SampleRequestWrite) => createMySampleRequest(data),
    onSuccess: refresh,
    onError: fail('Failed to save the sample request'),
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SampleRequestWrite }) => updateMySampleRequest(id, data),
    onSuccess: refresh,
    onError: fail('Failed to save the sample request'),
  });
  const submit = useMutation({
    mutationFn: (id: string) => submitMySampleRequest(id),
    onSuccess: () => {
      refresh();
      toast.success('Sample request submitted');
    },
    onError: fail('Failed to submit the sample request'),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => cancelMySampleRequest(id),
    onSuccess: refresh,
    onError: fail('Failed to cancel the sample request'),
  });
  return { create, update, submit, cancel };
}

/**
 * A salesperson's own new product application written through the portal's application router (S5):
 * the staff page's create / update / submit / revise / cancel, run by the portal's code. The staff
 * list and detail read the same rows, so their keys refresh.
 */
export function useMyNewProductApplicationMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['new-product-applications'] });
    void queryClient.invalidateQueries({ queryKey: ['new-product-application'] });
  };
  const move = (fallback: string, done?: string) => ({
    onSuccess: () => {
      refresh();
      if (done) toast.success(done);
    },
    onError: (error: Error) => toast.error(error.message || fallback),
  });
  const create = useMutation({
    mutationFn: (data: NewProductApplicationWrite) => createMyNewProductApplication(data),
    ...move('Failed to save the application'),
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: NewProductApplicationWrite }) =>
      updateMyNewProductApplication(id, data),
    ...move('Failed to save the application'),
  });
  const submit = useMutation({
    mutationFn: (id: string) => submitMyNewProductApplication(id),
    ...move('Failed to submit the application', 'Application submitted'),
  });
  const revise = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => reviseMyNewProductApplication(id, reason),
    ...move('Failed to revise the application', 'Back to draft'),
  });
  const cancel = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => cancelMyNewProductApplication(id, reason),
    ...move('Failed to cancel the application', 'Application cancelled'),
  });
  return { create, update, submit, revise, cancel };
}

/** "Start from" one of their own responded stock inquiries, read through My Requests. */
export function useMyNewProductApplicationPrefill(stockInquiryId: string | null) {
  return useQuery({
    queryKey: [MY_REQUEST_KEY, 'new_product_application', 'prefill', stockInquiryId],
    queryFn: () => fetchMyNewProductApplicationPrefill(stockInquiryId as string),
    enabled: Boolean(stockInquiryId),
    staleTime: Infinity,
    retry: 1,
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

/** Remove one of their own files at once (the portal does the same); `refreshKeys` as for the upload. */
export function useDeleteMyRequestAttachment(refreshKeys: unknown[][]) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteAttachment(linkId),
    onSuccess: () => {
      for (const key of refreshKeys) void queryClient.invalidateQueries({ queryKey: key });
      toast.success('File removed');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove attachment.'),
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
 * submit, delete a draft, approve the proof, ask for changes, download the PDF, collect, revise. The
 * staff table and request page read the same rows, so their keys refresh.
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
  const remove = useMutation({
    mutationFn: (id: string) => deleteMyPriceTagRequest(id),
    ...move('Failed to delete the draft', 'Draft deleted'),
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
  return { create, update, submit, remove, approve, requestChanges, download, collect, revise };
}
