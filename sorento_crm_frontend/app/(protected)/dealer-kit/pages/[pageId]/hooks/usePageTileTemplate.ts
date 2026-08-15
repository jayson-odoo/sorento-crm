import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  setPageTileTemplate,
  type PageTileTemplateLink,
} from '../../../services/dealerKitService';

/**
 * Save the design this brochure's tiles use.
 *
 * The page DETAIL query is deliberately NOT invalidated, for the same reason as
 * the promotion: the editor seeds its working document from it, so refetching
 * would throw away whatever a Designer has laid out and not yet saved. The link
 * comes back on the call, so the control has the fresh value without a round
 * trip.
 */
export function useSetPageTileTemplate(pageId: string) {
  const queryClient = useQueryClient();

  return useMutation<PageTileTemplateLink, Error, string | null>({
    mutationFn: (tileTemplateId) => setPageTileTemplate(pageId, tileTemplateId),
    onSuccess: (link) => {
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(link.tileTemplateId ? 'Tile design applied' : 'Tile design cleared');
    },
    onError: (error) => {
      toast.error(error.message || 'Could not save the tile design');
    },
  });
}
