import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getMessagePushScope,
  updateMessagePushScope,
  type MessagePushScope,
} from '@/services/messagePushScopeService';

export const MESSAGE_PUSH_SCOPE_KEY = ['message-push-scope'] as const;

/** Current user's message push scope (PLAN-message-push). */
export function useMessagePushScopeQuery() {
  return useQuery<MessagePushScope, Error>({
    queryKey: MESSAGE_PUSH_SCOPE_KEY,
    queryFn: getMessagePushScope,
    retry: false,
  });
}

/**
 * Saves the scope. The caller keeps the select responsive by showing its own optimistic
 * value; on failure this puts the server's value back in the cache so the select reverts
 * (AC-M4) and toasts the extracted message.
 */
export function useMessagePushScopeMutation() {
  const queryClient = useQueryClient();
  return useMutation<MessagePushScope, Error, MessagePushScope>({
    mutationFn: updateMessagePushScope,
    onSuccess: (scope) => {
      queryClient.setQueryData(MESSAGE_PUSH_SCOPE_KEY, scope);
      toast.success('Message notification setting updated');
    },
    onError: (err) => toast.error(err.message),
  });
}
