import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  addAccessoryPicture,
  createAccessory,
  deleteAccessoryImage,
  deleteAccessoryPicture,
  getAccessories,
  listOwnerAccessories,
  orderAccessoryPictures,
  patchAccessoryPicture,
  replaceOwnerAccessories,
  updateAccessory,
  uploadAccessoryImage,
  type PictureColour,
} from '../services/accessoryService';
import { entryRef } from '../types/accessory.types';
import type {
  AccessoryEntry,
  AccessoryOwnerKind,
  AccessoryWrite,
} from '../types/accessory.types';

export const ACCESSORIES_KEY = ['accessories'];
export const ownerAccessoriesKey = (kind: AccessoryOwnerKind, id: string | undefined) => [
  'owner-accessories',
  kind,
  id,
];

export function useAccessories(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...ACCESSORIES_KEY, params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getAccessories(params),
    retry: 1,
  });
}

export function useCreateAccessory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (write: AccessoryWrite) => createAccessory(write),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
      toast.success('Accessory added');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add the accessory'),
  });
}

export function useUpdateAccessory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, write }: { id: string; write: Partial<AccessoryWrite> }) =>
      updateAccessory(id, write),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
      queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
      toast.success('Accessory saved');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save the accessory'),
  });
}

export function useAccessoryImage() {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
    queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
  };
  const upload = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => uploadAccessoryImage(id, file),
    onSuccess: refresh,
    onError: (error: Error) => toast.error(error.message || 'Failed to upload the picture'),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteAccessoryImage(id),
    onSuccess: refresh,
    onError: (error: Error) => toast.error(error.message || 'Failed to remove the picture'),
  });
  return {
    uploadMutateAsync: upload.mutateAsync,
    deleteMutateAsync: remove.mutateAsync,
    busy: upload.isPending || remove.isPending,
  };
}

/** Several coloured pictures per accessory: add, recolour, remove, reorder. */
export function useAccessoryPictures() {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
    queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
  };
  const fail = (fallback: string) => (error: Error) => toast.error(error.message || fallback);
  const add = useMutation({
    mutationFn: ({ id, file, colour }: { id: string; file: File; colour?: Partial<PictureColour> }) =>
      addAccessoryPicture(id, file, colour),
    onSuccess: refresh,
    onError: fail('Failed to upload the picture'),
  });
  const patch = useMutation({
    mutationFn: ({ id, imageId, colour }: { id: string; imageId: string; colour: Partial<PictureColour> }) =>
      patchAccessoryPicture(id, imageId, colour),
    onSuccess: refresh,
    onError: fail('Failed to save the colour'),
  });
  const remove = useMutation({
    mutationFn: ({ id, imageId }: { id: string; imageId: string }) => deleteAccessoryPicture(id, imageId),
    onSuccess: refresh,
    onError: fail('Failed to remove the picture'),
  });
  const order = useMutation({
    mutationFn: ({ id, ids }: { id: string; ids: string[] }) => orderAccessoryPictures(id, ids),
    onSuccess: refresh,
    onError: fail('Failed to reorder the pictures'),
  });
  return {
    addMutateAsync: add.mutateAsync,
    patchMutateAsync: patch.mutateAsync,
    removeMutateAsync: remove.mutateAsync,
    orderMutateAsync: order.mutateAsync,
    busy: add.isPending || patch.isPending || remove.isPending || order.isPending,
  };
}

/** The ordered list on a product or a combo. */
export function useOwnerAccessories(kind: AccessoryOwnerKind, id: string | undefined) {
  return useQuery({
    queryKey: ownerAccessoriesKey(kind, id),
    queryFn: () => listOwnerAccessories(kind, id as string),
    enabled: !!id,
  });
}

/**
 * Replace the whole ordered list. Optimistic: the cache shows the new order at once and
 * is put back if the server refuses.
 */
export function useReplaceOwnerAccessories(kind: AccessoryOwnerKind, id: string) {
  const queryClient = useQueryClient();
  const key = ownerAccessoriesKey(kind, id);
  return useMutation({
    mutationFn: ({ next }: { next: AccessoryEntry[] }) =>
      replaceOwnerAccessories(
        kind,
        id,
        next.map(entryRef),
      ),
    onMutate: async ({ next }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<AccessoryEntry[]>(key);
      queryClient.setQueryData<AccessoryEntry[]>(key, next);
      return { previous };
    },
    onError: (error: Error, _vars, context) => {
      queryClient.setQueryData(key, context?.previous);
      toast.error(error.message || 'Failed to save the accessories');
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(key, saved);
      queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
      queryClient.invalidateQueries({ queryKey: ['product-combos'] });
    },
  });
}
