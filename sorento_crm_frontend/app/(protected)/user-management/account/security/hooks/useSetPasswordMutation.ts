'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  setPassword,
  type SetPasswordInput,
} from '@/services/accountPasswordService';

/**
 * Account > Security's Password card (plan 5.3). `onSuccess` closes the
 * dialog; the mutation's own `error` is read inline in the form (`change-
 * password-dialog.tsx`) and is not toasted a second time.
 */
export function useSetPasswordMutation(options: { onSuccess?: () => void } = {}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SetPasswordInput) => setPassword(input),
    onSuccess: () => {
      toast.success('Password saved.');
      queryClient.invalidateQueries({ queryKey: ['account-profile'] });
      options.onSuccess?.();
    },
    // No onError toast: the dialog shows the error inline, once (fix lane
    // round 2, reviewer Nit 4).
  });
}
