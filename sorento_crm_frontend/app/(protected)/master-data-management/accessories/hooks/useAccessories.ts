import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { listAccessoryTemplates } from '@/app/(protected)/dealer-kit/services/accessoryTemplateService';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  addAccessoryPicture,
  createAccessory,
  deleteAccessoryImage,
  getAccessory,
  getAccessories,
  listOwnerAccessories,
  orderAccessoryPictures,
  patchAccessoryPicture,
  replaceOwnerAccessories,
  updateAccessory,
  uploadAccessoryImage,
  type PictureColour,
} from '../services/accessoryService';
import { entryRef, withBoxStyle } from '../types/accessory.types';
import type {
  AccessoryEntry,
  OwnerAccessories,
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
  const order = useMutation({
    mutationFn: ({ id, ids }: { id: string; ids: string[] }) => orderAccessoryPictures(id, ids),
    onSuccess: refresh,
    onError: fail('Failed to reorder the pictures'),
  });
  return {
    addMutateAsync: add.mutateAsync,
    patchMutateAsync: patch.mutateAsync,
    orderMutateAsync: order.mutateAsync,
    busy: add.isPending || patch.isPending || order.isPending,
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
    mutationFn: ({ next, boxStyleId }: { next: AccessoryEntry[]; boxStyleId?: string | null }) =>
      boxStyleId === undefined
        ? replaceOwnerAccessories(kind, id, next.map(entryRef))
        : replaceOwnerAccessories(kind, id, next.map(entryRef), boxStyleId),
    onMutate: async ({ next, boxStyleId }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<OwnerAccessories>(key);
      // The list and the owner's box style travel in one answer, so one cache entry holds both.
      queryClient.setQueryData<OwnerAccessories>(
        key,
        withBoxStyle(next, boxStyleId === undefined ? previous?.box_style_id : boxStyleId),
      );
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

/** Saved accessories templates as picker options, read now and narrowed by what was typed. */
export async function fetchBoxStyleOptions(query: string) {
  const needle = query.trim().toLowerCase();
  // A picker that cannot load its choices offers none; it must not throw into the form.
  const templates = await listAccessoryTemplates().catch(() => []);
  return templates
    .filter((template) => !needle || template.name.toLowerCase().includes(needle))
    .map((template) => ({ value: template.id, label: template.name }));
}

/** Saved accessories templates as picker options. */
export function useBoxStyleOptions(enabled: boolean) {
  return useQuery({
    queryKey: ['dealer-kit-accessory-templates', 'options'],
    queryFn: async () =>
      (await listAccessoryTemplates()).map((template) => ({ value: template.id, label: template.name })),
    enabled,
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
