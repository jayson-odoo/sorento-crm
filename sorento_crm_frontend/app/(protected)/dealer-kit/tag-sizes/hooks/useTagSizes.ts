'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createTagSize,
  deleteTagSize,
  listTagSizes,
  updateTagSize,
  type TagSizeInput,
  type TagSizeRecord,
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
 * PHASE 1: an immediate delete with a client-side Undo (re-create the same
 * row) - `useDeferredRowAction`'s server-parked countdown needs a backend
 * action handler this table does not have until Phase 2 registers
 * `tag_size_preset.delete` (`app/services/record_actions.py`, the same shape
 * `tag_template.delete` already has). Both callers of this hook - the listing
 * page's row menu and the tag-size control's saved-size `x` - swap to
 * `useDeferredRowAction` in Phase 2, so this hook is deleted rather than kept
 * around as a second delete path.
 */
export function useDeleteTagSize() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (row: TagSizeRecord) => deleteTagSize(row.id).then(() => row),
    onSuccess: (row) => {
      queryClient.invalidateQueries({ queryKey: [TAG_SIZES_QUERY_KEY] });
      toast(`"${row.name}" deleted`, {
        action: {
          label: 'Undo',
          onClick: () => {
            createTagSize({
              name: row.name,
              width_mm: row.width_mm,
              height_mm: row.height_mm,
            })
              .then(() => {
                queryClient.invalidateQueries({ queryKey: [TAG_SIZES_QUERY_KEY] });
              })
              .catch(() => {
                toast.error('Could not restore this tag size');
              });
          },
        },
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
