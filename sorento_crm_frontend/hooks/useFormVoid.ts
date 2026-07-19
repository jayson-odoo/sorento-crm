'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  voidForm,
  type VoidableResource,
  type VoidFormPayload,
  type VoidFormResult,
} from '@/lib/formVoidService';

/**
 * Mutation hook for voiding a form (R3). UI → hook → feature service → (mock).
 *
 * Phase 1: the underlying `voidForm` service is mocked (no network). On success
 * it invalidates the caller-supplied query keys so the detail page refetches and
 * flips into its read-only / VoidBanner state, and toasts.
 */
export function useFormVoid(
  resource: VoidableResource,
  id: string,
  options?: { queryKeysToInvalidate?: unknown[][]; onSuccess?: (r: VoidFormResult) => void },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VoidFormPayload) => voidForm(resource, id, payload),
    onSuccess: (result) => {
      (options?.queryKeysToInvalidate ?? []).forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
      toast.success('Form voided');
      options?.onSuccess?.(result);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to void form');
    },
  });
}
