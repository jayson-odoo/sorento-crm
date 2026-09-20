'use client';

/**
 * Per-tag writes the designer's rail makes (r10 S6).
 *
 * A react-query mutation so the rail is UI -> hook -> service like every
 * other write here; the designer itself holds the request in local state
 * (Split, Remove and Revise already re-read it through `reloadRequest`), so
 * the caller applies the answer.
 */
import { useMutation } from '@tanstack/react-query';

import {
  updateRequestTag,
  type PriceTagRequestTag,
  type PriceTagRequestTagUpdate,
} from '../../services/priceTagRequestService';

/** `PATCH .../tags/{tagId}` - quantity, override, and since r10 `print_excluded`. */
export function useUpdateRequestTag(requestId: string) {
  return useMutation({
    mutationFn: ({ tagId, data }: { tagId: string; data: PriceTagRequestTagUpdate }) =>
      updateRequestTag(requestId, tagId, data),
  });
}

export type { PriceTagRequestTag };
