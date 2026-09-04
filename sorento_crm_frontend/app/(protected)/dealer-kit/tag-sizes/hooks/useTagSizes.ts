'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  createTagSize,
  listTagSizes,
  updateTagSize,
  type TagSizeInput,
} from '../../services/tagSizeService';

export const TAG_SIZES_QUERY_KEY = 'dealer-kit-tag-sizes';

export function useTagSizesQuery() {
  return useQuery({
    queryKey: [TAG_SIZES_QUERY_KEY],
    queryFn: listTagSizes,
  });
}

export function useCreateTagSize() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TagSizeInput) => createTagSize(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TAG_SIZES_QUERY_KEY] });
    },
  });
}

export function useUpdateTagSize() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<TagSizeInput> }) =>
      updateTagSize(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [TAG_SIZES_QUERY_KEY] });
    },
  });
}

/**
 * Delete = deferred action + Undo toast, no confirm dialog (D7): the row (or
 * dropdown option) dims/disables for the countdown, and the server commits
 * the SAME `tag_size_service.delete_preset` the listing's own DELETE route
 * calls (`app/services/record_actions.py`'s `tag_size_preset.delete`).
 * Shared by both callers - the listing page's row menu and the Tag Size
 * control's saved-size `x` - so the two cannot drift.
 */
export function useDeleteTagSizePreset() {
  return useDeferredRowAction({
    actionKey: 'tag_size_preset.delete',
    entityType: 'tag_size_preset',
    successMessage: 'Tag size deleted',
    invalidateKeys: [[TAG_SIZES_QUERY_KEY]],
  });
}
