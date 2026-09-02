import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  setPagePromotion,
  type PagePromotionLink,
} from '../../../services/dealerKitService';

/**
 * Save which promotion prices this brochure (PLAN D5).
 *
 * The pages LIST is invalidated, and the page DETAIL query deliberately is not:
 * the editor screen seeds its working document from that query, so refetching
 * it would throw away whatever a Designer has laid out and not yet saved. The
 * link itself is returned by the call, so the control has the fresh value
 * without a round trip.
 */
export function useSetPagePromotion(pageId: string) {
  const queryClient = useQueryClient();

  return useMutation<PagePromotionLink, Error, string | null>({
    mutationFn: (promotionId) => setPagePromotion(pageId, promotionId),
    onSuccess: (link) => {
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(
        link.promotionId ? 'Promotion linked' : 'Promotion cleared',
      );
    },
    onError: (error) => {
      toast.error(error.message || 'Could not save the promotion');
    },
  });
}
