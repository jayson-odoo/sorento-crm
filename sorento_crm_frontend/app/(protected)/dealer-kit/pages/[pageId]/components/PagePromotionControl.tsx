'use client';

import { useEffect, useState } from 'react';

import { SearchableSelect } from '@/components/common/SearchableSelect';

// The same fetcher the brochure image picker filters by, reused rather than
// copied: two option sources would be two ideas of what searching promotions
// means.
import { useBrochureImagePromotionOptions } from '../../../brochure-images/hooks/useBrochureImages';
import { PROMOTION_PAGE_SIZE } from '../../../services/brochureImageService';
import type { PagePromotionLink } from '../../../services/dealerKitService';
import { useSetPagePromotion } from '../hooks/usePagePromotion';

export interface PagePromotionControlProps {
  pageId: string;
  /** The promotion currently linked, or null for list prices only. */
  promotionId: string | null;
  /** Its name, resolved by the backend. Null when the promotion has no description. */
  promotionLabel: string | null;
}

/** What a promotion with no description of its own is called on screen. */
const UNTITLED = 'Untitled promotion';

export function PagePromotionControl({
  pageId,
  promotionId,
  promotionLabel,
}: PagePromotionControlProps) {
  // Saved state, not a draft: it moves only when the backend confirms. An
  // optimistic value here would leave a failed save looking as though it
  // worked, which is exactly how a decision gets silently discarded.
  const [link, setLink] = useState<PagePromotionLink>({ promotionId, promotionLabel });
  useEffect(() => {
    setLink({ promotionId, promotionLabel });
  }, [promotionId, promotionLabel]);

  const { fetchOptions, optionFor } = useBrochureImagePromotionOptions();
  const { mutate, isPending } = useSetPagePromotion(pageId);

  const selectedOption = link.promotionId
    ? // Prefer an option already fetched (it carries the product count), and
      // fall back to the label the page arrived with so the trigger never has
      // to render an id.
      optionFor(link.promotionId) ?? {
        value: link.promotionId,
        label: link.promotionLabel?.trim() || UNTITLED,
      }
    : undefined;

  const handleChange = (value: string) => {
    const next = value || null;
    // Re-picking what is already linked is not a change worth a write.
    if (next === link.promotionId) return;
    mutate(next, { onSuccess: (saved) => setLink(saved) });
  };

  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="shrink-0 text-xs text-muted-foreground">Prices from</span>
      <SearchableSelect
        id="dk-page-promotion"
        size="sm"
        value={link.promotionId ?? ''}
        onChange={handleChange}
        // Server-searched and paged: there are hundreds of promotions, so a
        // static list would cap this at one page and hide the rest.
        fetchOptions={fetchOptions}
        paginated
        pageSize={PROMOTION_PAGE_SIZE}
        selectedOption={selectedOption}
        // Says what the reader gets, so an empty control reads as finished
        // rather than unanswered.
        placeholder="List prices only"
        clearable
        disabled={isPending}
        triggerClassName="w-56"
      />
    </div>
  );
}
