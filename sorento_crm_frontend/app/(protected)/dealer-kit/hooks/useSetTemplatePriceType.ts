'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { setTemplatePriceType } from '../services/tagTemplateService';
import type { TemplatePriceType } from '@/lib/dealer-kit/template-price-type';

/**
 * Set (or clear) a template's price type. The type decides which links fit a line, so the tag
 * template queries and both link caches are invalidated: a product page open elsewhere must not
 * keep the old type.
 */
export function useSetTemplatePriceType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, priceType }: { id: string; priceType: TemplatePriceType | null }) =>
      setTemplatePriceType(id, priceType),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tag-templates'] });
      void queryClient.invalidateQueries({ queryKey: ['product-tag-templates'] });
      void queryClient.invalidateQueries({ queryKey: ['combo-tag-templates'] });
    },
  });
}
