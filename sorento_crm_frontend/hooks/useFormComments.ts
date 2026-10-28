'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useRequestScope } from '@/hooks/useRequestScope';
import {
  addFormComment,
  editFormComment,
  listFormComments,
} from '@/services/formCommentsService';
import {
  deleteSubmissionComment,
  editSubmissionComment,
  fetchSubmissionComments,
  postSubmissionComment,
  type MyRequestKind,
} from '@/services/myRequestsService';
import type { FormCommentKind } from '@/types/formComments';

export const FORM_COMMENTS_KEY = 'form-comments';

// A user limited to their own requests (PORTAL-P4-REQUESTS) talks to the thread as its submitter,
// through My Requests: the staff route only lets them read, and a staff comment would WhatsApp them.

export function useFormCommentsQuery(kind: FormCommentKind, id: string) {
  const { limited } = useRequestScope(kind);
  return useQuery({
    queryKey: [FORM_COMMENTS_KEY, kind, id, limited],
    queryFn: () =>
      limited
        ? fetchSubmissionComments(kind as MyRequestKind, id)
        : listFormComments(kind, id),
    enabled: Boolean(id),
  });
}

/**
 * Post a staff comment. The comment is saved before the WhatsApp is queued, so a channel
 * problem is a warning about the notification, never a lost comment.
 */
export function useAddFormComment(kind: FormCommentKind, id: string) {
  const queryClient = useQueryClient();
  const { limited } = useRequestScope(kind);
  return useMutation({
    mutationFn: ({
      body,
      files,
      parentId,
    }: {
      body: string;
      files: File[];
      parentId?: string;
    }) =>
      limited
        ? postSubmissionComment(kind as MyRequestKind, id, body, files, parentId)
        : addFormComment(kind, id, body, files, parentId),
    onSuccess: ({ delivery }) => {
      queryClient.invalidateQueries({
        queryKey: [FORM_COMMENTS_KEY, kind, id],
      });
      if (delivery === 'no_whatsapp') {
        toast.warning(
          'Comment posted. The submitter has no WhatsApp contact, so they were not notified.',
        );
      } else if (delivery === 'failed') {
        toast.warning(
          'Comment posted, but the WhatsApp to the submitter could not be sent.',
        );
      } else {
        toast.success('Comment posted');
      }
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to post the comment'),
  });
}

/** Edit a comment in place; no notification goes out for an edit. */
export function useEditFormComment(kind: FormCommentKind, id: string) {
  const queryClient = useQueryClient();
  const { limited } = useRequestScope(kind);
  return useMutation({
    mutationFn: ({ commentId, body }: { commentId: string; body: string }) =>
      limited
        ? editSubmissionComment(kind as MyRequestKind, id, commentId, body)
        : editFormComment(kind, id, commentId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [FORM_COMMENTS_KEY, kind, id],
      });
      toast.success('Comment saved');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to save the comment'),
  });
}

/**
 * A limited user's own comment goes at once, through My Requests (the portal's own delete). The
 * staff delete is a server-deferred countdown (`FormCommentDelete`) and stays with staff.
 */
export function useDeleteMyComment(kind: FormCommentKind, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) => deleteSubmissionComment(kind as MyRequestKind, id, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [FORM_COMMENTS_KEY, kind, id] });
      toast.success('Comment deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete the comment'),
  });
}
