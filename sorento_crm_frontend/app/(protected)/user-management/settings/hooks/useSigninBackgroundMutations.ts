'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { uploadSigninBackground } from '../services/signinBackgroundService';

/**
 * Upload the sign-in background.
 *
 * Removal is not here: it is destructive, so it goes through `ConfirmDeleteDialog`, which owns
 * its own mutation, toast and invalidation.
 *
 * Invalidating `system-settings` is what makes the preview true - the settings layout refetches
 * the blob and the card renders the URL the server actually stored. The sign-in page is a
 * different origin of state (nobody has a session there) and picks the change up on its next load.
 */
export function useSigninBackgroundMutations() {
  const queryClient = useQueryClient();

  const upload = useMutation({
    mutationFn: (file: File) => uploadSigninBackground(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast.success('Sign-in background updated');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { upload };
}
