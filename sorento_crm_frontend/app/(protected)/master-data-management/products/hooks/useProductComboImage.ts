'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  deleteProductComboImage,
  uploadProductComboImage,
} from '../services/productComboService';
import { combosKey } from './useProductCombos';

/**
 * The combo's own cover picture (AC-S5-2/S5-3/S5-5 extended): upload and
 * clear, both through the query cache like every other combo mutation on
 * this page, instead of `ComboImageControl`'s own `useState` + bare service
 * call - a mutation hook the same shape `useUpdateProductComboPart` already
 * is, not a one-off.
 */
export function useProductComboImage(productId: string | undefined) {
  const queryClient = useQueryClient();

  const upload = useMutation({
    mutationFn: (input: { comboId: string; file: File }) =>
      uploadProductComboImage(input.comboId, input.file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: combosKey(productId) });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to upload the image'),
  });

  const del = useMutation({
    mutationFn: (comboId: string) => deleteProductComboImage(comboId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: combosKey(productId) });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to clear the image'),
  });

  return {
    uploadMutateAsync: upload.mutateAsync,
    deleteMutateAsync: del.mutateAsync,
    isUploading: upload.isPending,
    isDeleting: del.isPending,
  };
}
