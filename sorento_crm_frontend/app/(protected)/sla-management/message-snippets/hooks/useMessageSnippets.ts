'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

import {
  createMessageSnippet,
  getMessageSnippetOptions,
  listMessageSnippets,
  updateMessageSnippet,
  type MessageSnippetListQuery,
} from '../services/messageSnippetService';
import type { MessageSnippetFormData } from '../types/messageSnippet.types';

const LIST_KEY = ['message-snippets'] as const;
/** Every ticket's picker cache, whatever it was resolved against. */
const OPTIONS_KEY = ['message-snippet-options'] as const;

/** The composer picker's key. Per ticket, because the bodies come back resolved. */
export const snippetOptionsKey = (trackingId: string | null) =>
  [...OPTIONS_KEY, trackingId] as const;

/**
 * Admin CRUD moves BOTH caches: the listing, and every composer picker. A
 * snippet edited (or deactivated) while a drawer is open otherwise keeps
 * offering the old wording for the rest of the session.
 */
function invalidateSnippets(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: LIST_KEY });
  void queryClient.invalidateQueries({ queryKey: OPTIONS_KEY });
}

export function useMessageSnippets(query: MessageSnippetListQuery) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...LIST_KEY, query],
    queryFn: () => listMessageSnippets(query),
    retry: 1,
  });
}

export function useCreateMessageSnippet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MessageSnippetFormData) => createMessageSnippet(body),
    onSuccess: () => {
      invalidateSnippets(queryClient);
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
      invalidateSnippets(queryClient);
      toast.success('Snippet updated');
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
