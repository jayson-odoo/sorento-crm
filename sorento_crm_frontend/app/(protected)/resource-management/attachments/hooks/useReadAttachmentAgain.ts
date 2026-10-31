import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { readAttachmentAgain } from '../services/attachmentService';

/** Queue the AI's reading of one file again; refreshes the detail page's metadata. */
export function useReadAttachmentAgain() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => readAttachmentAgain(id),
    onSuccess: (_data, id) => {
      toast.success('Queued for reading');
      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', id] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to queue the AI read'),
  });
}
