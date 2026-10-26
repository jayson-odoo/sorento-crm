import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  applyAccessSheet,
  previewAccessSheet,
  type AccessSheetConfirmed,
} from '@/services/contactAccessSheetService';

export function usePreviewAccessSheet() {
  return useMutation({
    mutationFn: (file: File) => previewAccessSheet(file),
    onError: (error: Error) => toast.error(error.message || 'Failed to read the sheet'),
  });
}

export function useApplyAccessSheet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, confirmed }: { file: File; confirmed: AccessSheetConfirmed }) =>
      applyAccessSheet(file, confirmed),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      void queryClient.invalidateQueries({ queryKey: ['contact-customers'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to apply the sheet'),
  });
}
