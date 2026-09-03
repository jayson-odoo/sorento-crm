import { useCallback, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

// The flag is product master data, so the write lives with the products
// feature and this screen is its second caller, not its second implementation.
import { setBrochureImage } from '@/app/(protected)/master-data-management/products/services/productBrochureImageService';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

import {
  adoptSingleBrochureImages,
  listBrochureImages,
  listBrochureImagePromotionOptions,
  type BrochureImageListParams,
  type BrochureImagePage,
} from '../../services/brochureImageService';

export const BROCHURE_IMAGES_QUERY_KEY = 'dealer-kit-brochure-images';

export function useBrochureImagesQuery(params: BrochureImageListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
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
    retry: 1,
  });
}

/**
 * Answer every product on the page whose photo is not in doubt.
 *
 * Fired once per page of the worklist, and idempotent on the server, so a
 * remount or a refetch costs one no-op request rather than churning
 * `is_primary`. Silent on success: it is not news that a product with one photo
 * uses that photo, and a toast per page would be noise between the user and the
 * rows that DO need them.
 */
export function useAdoptSingleBrochureImages() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productIds: string[]) => adoptSingleBrochureImages(productIds),
    onSuccess: (adopted) => {
      if (adopted.length === 0) return;
      // Patched in place, exactly as a single choice is, and for the same
      // reason: an invalidation with `only_unset` on would pull the answered
      // rows out from under whoever is working down the list.
      queryClient.setQueriesData<BrochureImagePage>(
        { queryKey: [BROCHURE_IMAGES_QUERY_KEY] },
        (current) => {
          if (!current) return current;
          const answered = new Set(adopted);
          return {
            ...current,
            items: current.items.map((row) =>
              answered.has(row.productId) && row.candidates.length === 1
                ? { ...row, chosenAttachmentId: row.candidates[0].attachmentId }
                : row,
            ),
            remaining: Math.max(0, current.remaining - adopted.length),
          };
        },
      );
    },
    onError: (error: Error) => {
      // Worth saying: the user will otherwise see single-photo products sitting
      // unanswered and assume the screen is broken.
      toast.error(error.message || 'Could not take the single photos');
    },
  });
}


export function useSetBrochureImage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, attachmentId }: { productId: string; attachmentId: string }) =>
      setBrochureImage(productId, attachmentId),
    onSuccess: (_result, { productId, attachmentId }) => {
      // Patched in place rather than invalidated. An invalidation refetches with
      // only_unset still on, so the answered product disappears and every row
      // below it slides up by a card while the user is mid-sequence: the next
      // click then lands on a product they were not looking at. The cached page
      // holds its order for as long as the user is working down it; changing a
      // filter or a page fetches a fresh worklist.
      queryClient.setQueriesData<BrochureImagePage>(
        { queryKey: [BROCHURE_IMAGES_QUERY_KEY] },
        (current) => {
          if (!current) return current;
          const target = current.items.find((row) => row.productId === productId);
          if (!target) return current;
          return {
            ...current,
            items: current.items.map((row) =>
              row.productId === productId ? { ...row, chosenAttachmentId: attachmentId } : row,
            ),
            // Only a product that had nothing chosen has just left the backlog,
            // so re-answering one already answered must not double-count it.
            remaining: target.chosenAttachmentId
              ? current.remaining
              : Math.max(0, current.remaining - 1),
          };
        },
      );
      toast.success('Brochure image set');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Could not save the brochure image');
      // Nothing to undo here on purpose: the count is only ever decremented in
      // onSuccess, so a failed save leaves it agreeing with the list. Anything
      // that moves the patch above into onMutate owes this branch the reverse
      // patch, or the header will claim work that was never saved.
    },
  });
}

interface BrochureImagePromotionOptions {
  /**
   * Stable across renders. As an inline closure its identity changed on every
   * parent render, and SearchableSelect keys its fetch effect on it: a keystroke
   * in the product search box then cost a page of promotions.
   */
  fetchOptions: (query: string, pageIndex: number) => Promise<SearchableSelectOption[]>;
  /**
   * The option behind a selected value, remembered from a page already fetched.
   * Without it the trigger has nothing to render once the selection falls off
   * the current page, and an id is never an acceptable label.
   */
  optionFor: (value: string) => SearchableSelectOption | undefined;
}

export function useBrochureImagePromotionOptions(): BrochureImagePromotionOptions {
  const seen = useRef(new Map<string, SearchableSelectOption>());

  const fetchOptions = useCallback(async (query: string, pageIndex: number) => {
    const options = await listBrochureImagePromotionOptions(query, pageIndex);
    for (const option of options) seen.current.set(option.value, option);
    return options;
  }, []);

  const optionFor = useCallback((value: string) => seen.current.get(value), []);

  return { fetchOptions, optionFor };
}
