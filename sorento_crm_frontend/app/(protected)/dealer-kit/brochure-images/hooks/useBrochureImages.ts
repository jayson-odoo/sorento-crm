import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  listBrochureImages,
  setBrochureImage,
  type BrochureImageListParams,
} from '../../services/brochureImageService';

export const BROCHURE_IMAGES_QUERY_KEY = 'dealer-kit-brochure-images';

export function useBrochureImagesQuery(params: BrochureImageListParams) {
  return useQuery({
    queryKey: [
      BROCHURE_IMAGES_QUERY_KEY,
      params.promotionId ?? '',
      params.onlyUnset ?? true,
      params.query ?? '',
      params.page ?? 1,
      params.limit ?? null,
    ],
    queryFn: () => listBrochureImages(params),
    // The list is a worklist somebody works down; a stale page would show a
    // product they have already dealt with as still needing a photo.
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSetBrochureImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, attachmentId }: { productId: string; attachmentId: string }) =>
      setBrochureImage(productId, attachmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [BROCHURE_IMAGES_QUERY_KEY] });
      toast.success('Brochure image set');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Could not save the brochure image');
    },
  });
}
