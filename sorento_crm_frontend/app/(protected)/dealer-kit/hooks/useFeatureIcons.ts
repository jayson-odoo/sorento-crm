'use client';

/**
 * Feature icons (PRICETAG-DESIGNER-GAPS item 3): the "Show when" spec vocabulary and mutation.
 * UI -> these hooks -> assetService / tagDataService. The canvas reads the icons through `useKitLibrary`.
 */
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { kitLibraryClient } from '@/lib/dealer-kit/kit-library-cache';
import {
  setAssetShowWhen,
  type AssetShowWhenBody,
  type KitAsset,
} from '../services/assetService';
import { listSpecKeys } from '../services/tagDataService';

/**
 * The spec vocabulary the Show when editor offers, from the dealer-kit route (behind the
 * editor's own permission), never the master-data registry route.
 */
export function useFeatureIconSpecKeys() {
  return useQuery({
    queryKey: ['dealer-kit', 'spec-keys'],
    queryFn: () => listSpecKeys(),
    staleTime: 60_000,
  });
}

export function useSetAssetShowWhen() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetShowWhenBody }) =>
      setAssetShowWhen(id, body),
    onSuccess: (asset: KitAsset) => {
      // The canvas reads the library through its own cache (`useKitLibrary`).
      void kitLibraryClient.invalidateQueries({ queryKey: ['dealer-kit', 'library', 'assets'] });
      void kitLibraryClient.invalidateQueries({ queryKey: ['dealer-kit', 'library', 'icons'] });
      toast.success(asset.show_when_spec_key ? `${asset.name} rule saved` : `${asset.name} rule cleared`);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to save the show when rule');
    },
  });
}
