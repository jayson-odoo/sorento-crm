import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  addAccessoryPicture,
  copyProductAccessories,
  createAccessory,
  deleteAccessoryImage,
  getAccessory,
  getAccessories,
  listOwnerAccessories,
  orderAccessoryPictures,
  replaceAccessoryColours,
  replaceOwnerAccessories,
  updateAccessory,
  uploadAccessoryImage,
} from '../services/accessoryService';
import { entryRef } from '../types/accessory.types';
import type {
  AccessoryColour,
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

/** An accessory's pictures: add and reorder (a picture carries no colour; removal is deferred). */
export function useAccessoryPictures() {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
    queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
  };
  const fail = (fallback: string) => (error: Error) => toast.error(error.message || fallback);
  const add = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => addAccessoryPicture(id, file),
    onSuccess: refresh,
    onError: fail('Failed to upload the picture'),
  });
  const order = useMutation({
    mutationFn: ({ id, ids }: { id: string; ids: string[] }) => orderAccessoryPictures(id, ids),
    onSuccess: refresh,
    onError: fail('Failed to reorder the pictures'),
  });
  return {
    addMutateAsync: add.mutateAsync,
    orderMutateAsync: order.mutateAsync,
    busy: add.isPending || order.isPending,
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
      replaceOwnerAccessories(kind, id, next.map(entryRef)),
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

/**
 * Removing a picture is a server-deferred action (`accessory_image.delete`): a countdown with Cancel,
 * no confirm dialog. `onCommitted` runs once the server has removed it.
 */
export function useDeleteAccessoryPicture(onCommitted?: () => void) {
  return useDeferredRowAction({
    actionKey: 'accessory_image.delete',
    entityType: 'accessory_image',
    successMessage: 'Picture removed',
    invalidateKeys: [ACCESSORIES_KEY, ['owner-accessories']],
    onCommitted,
  });
}

/** The accessory's pictures as the server holds them now (after a removal committed, whatever its order). */
export function useFreshAccessoryPictures() {
  const queryClient = useQueryClient();
  return useCallback(
    async (id: string) =>
      (
        await queryClient.fetchQuery({
          queryKey: ['accessory-pictures', id],
          queryFn: () => getAccessory(id),
          staleTime: 0,
        })
      ).images ?? [],
    [queryClient],
  );
}

/** Replace an accessory's ordered colours list (saved with the dialog's Save). */
export function useReplaceAccessoryColours() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, colours }: { id: string; colours: AccessoryColour[] }) =>
      replaceAccessoryColours(id, colours),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
      queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to save the colours'),
  });
}

/**
 * ACC-COPY-TO-PRODUCTS: `preview` is the dry run behind the confirm step, `copy` the write.
 * Every product's list is refetched after a copy, since any of them may have changed.
 */
export function useCopyProductAccessories(sourceId: string) {
  const queryClient = useQueryClient();
  const preview = useMutation({
    mutationFn: (targetIds: string[]) => copyProductAccessories(sourceId, targetIds, true),
    onError: (error: Error) => toast.error(error.message),
  });
  const copy = useMutation({
    mutationFn: (targetIds: string[]) => copyProductAccessories(sourceId, targetIds),
    onSuccess: (summary) => {
      queryClient.invalidateQueries({ queryKey: ['owner-accessories'] });
      queryClient.invalidateQueries({ queryKey: ACCESSORIES_KEY });
      const noun = summary.targets === 1 ? 'product' : 'products';
      toast.success(`Accessories copied to ${summary.targets} ${noun}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return { preview, copy };
}
