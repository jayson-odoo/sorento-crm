'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  attachCatalogPhotos,
  getCatalogPhotoReading,
  listCatalogPhotos,
  patchCatalogPhoto,
  uploadCatalogPhotoReading,
  type CatalogPhotoPatch,
  type CatalogPhotosParams,
} from '../services/catalogPhotoReadingService';

export const CATALOG_PHOTO_READING_KEY = 'catalog-photo-reading';

/** How often a reading that is still being read is asked about again. */
const READING_POLL_MS = 3000;

export function useCatalogPhotoReadingQuery(id: string) {
  return useQuery({
    queryKey: [CATALOG_PHOTO_READING_KEY, id],
    queryFn: () => getCatalogPhotoReading(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'queued' || status === 'reading' ? READING_POLL_MS : false;
    },
    staleTime: 0,
    retry: 1,
  });
}

export function useCatalogPhotosQuery(id: string, params: CatalogPhotosParams, enabled = true) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [CATALOG_PHOTO_READING_KEY, id, 'photos', params],
    queryFn: () => listCatalogPhotos(id, params),
    enabled: enabled && Boolean(id),
  });
}

export function useUploadCatalogPhotoReading() {
  return useMutation({ mutationFn: (file: File) => uploadCatalogPhotoReading(file) });
}

export function useCatalogPhotoMutations(id: string) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: [CATALOG_PHOTO_READING_KEY, id] });

  const patch = useMutation({
    mutationFn: ({ photoId, ...body }: CatalogPhotoPatch & { photoId: string }) =>
      patchCatalogPhoto(id, photoId, body),
    onSuccess: refresh,
    onError: (error: Error) => toast.error(error.message),
  });

  const attach = useMutation({
    mutationFn: () => attachCatalogPhotos(id),
    onSuccess: (result) => {
      toast.success(
        `Attached ${result.attached + result.replaced} photos to ${result.products} products. ${result.replaced} replaced, ${result.skipped} already on file.`,
      );
      return refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { patch, attach };
}
