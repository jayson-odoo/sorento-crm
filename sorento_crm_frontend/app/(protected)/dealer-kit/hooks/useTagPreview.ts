'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { TagPreviewLineInput } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { previewTags } from '../services/tagDataService';

/** One line of the staff tag preview (what the template draws for it, from the server). */
export function useTagPreview(line: TagPreviewLineInput, enabled: boolean) {
  return useQuery({
    queryKey: [
      'tag-preview',
      line.product_id,
      line.combo_id,
      line.tag_template_id,
      line.price_type,
      // COMBO-SETTINGS-UX: the preview's picks change what is drawn.
      line.parts,
    ],
    // The header mode only fills a line with no type of its own; this line always carries one.
    queryFn: () => previewTags(line.price_type ?? 'list', [line]),
    enabled,
    // Combo, template and prices change on other screens; a preview is cheap to redraw.
    staleTime: 0,
    // A new pick keeps the tag on screen until the redraw lands, rather than a skeleton flash.
    placeholderData: keepPreviousData,
  });
}
