'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  deleteDraftSubmission,
  fetchRevisions,
  fetchSubmission,
  reviseSubmission,
  saveDraft,
  submitDraft,
  type MyRequestKind,
  type ReviseSubmissionInput,
} from '@/services/myRequestsService';

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
