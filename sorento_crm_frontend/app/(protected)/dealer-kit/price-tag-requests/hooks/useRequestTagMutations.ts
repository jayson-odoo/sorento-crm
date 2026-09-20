'use client';

/**
 * Per-tag writes the designer's rail makes (r10 S6/S8).
 *
 * Both go through react-query mutations so the rail is UI -> hook -> service
 * like every other write here; the designer itself holds the request in local
 * state (Split, Remove and Revise already re-read it through `reloadRequest`),
 * so the caller applies the answer and these only settle the shared poll.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';

import {
  updateRequestTag,
  type PriceTagRequestTag,
  type PriceTagRequestTagUpdate,
} from '../../services/priceTagRequestService';
import { dismissTagDataUpdate } from '../../services/priceTagDataService';
import { tagDataChangesKey } from './useTagDataChanges';

/** `PATCH .../tags/{tagId}` - quantity, override, and since r10 `print_excluded`. */
export function useUpdateRequestTag(requestId: string) {
  return useMutation({
    mutationFn: ({ tagId, data }: { tagId: string; data: PriceTagRequestTagUpdate }) =>
      updateRequestTag(requestId, tagId, data),
  });
}

/**
 * r10 S8: Dismiss on an auto-updated tag. Clears the three "updated" columns
 * server-side; the data-changes poll is invalidated so a dot the diff was
 * still lighting goes with it.
 */
export function useDismissTagDataUpdate(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tagId: string) => dismissTagDataUpdate(requestId, tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: tagDataChangesKey(requestId) });
    },
  });
}

export type { PriceTagRequestTag };
