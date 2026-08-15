'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createMessageSnippet,
  deleteMessageSnippet,
  getMessageSnippetOptions,
  listMessageSnippets,
  updateMessageSnippet,
  type MessageSnippetListQuery,
} from '../services/messageSnippetService';
import type { MessageSnippetFormData } from '../types/messageSnippet.types';

const LIST_KEY = ['message-snippets'] as const;

/** The composer picker's key. Per ticket, because the bodies come back resolved. */
export const snippetOptionsKey = (trackingId: string | null) =>
  ['message-snippet-options', trackingId] as const;

export function useMessageSnippets(query: MessageSnippetListQuery) {
  return useQuery({
    queryKey: [...LIST_KEY, query],
    queryFn: () => listMessageSnippets(query),
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreateMessageSnippet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MessageSnippetFormData) => createMessageSnippet(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
      toast.success('Snippet created');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateMessageSnippet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<MessageSnippetFormData> }) =>
      updateMessageSnippet(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
      toast.success('Snippet updated');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDeleteMessageSnippet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteMessageSnippet(id),
    // The success toast belongs to ConfirmDeleteDialog (product standard), so
    // this one only refreshes the list.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * The snippets offered by the composer's "/" picker, resolved against the open
 * ticket. Disabled until the picker actually opens: a drawer nobody types "/"
 * in must not cost a request.
 */
export function useMessageSnippetOptions(trackingId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: snippetOptionsKey(trackingId),
    queryFn: () => getMessageSnippetOptions({ trackingId }),
    enabled,
    // Resolved against a ticket whose contact name does not change mid-session.
    staleTime: 60_000,
    retry: 1,
  });
}
