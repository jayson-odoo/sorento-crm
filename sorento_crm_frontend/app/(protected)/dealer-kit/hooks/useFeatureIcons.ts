'use client';

/**
 * Feature icons (PRICETAG-DESIGNER-GAPS item 3): the "Show when" mutation.
 * UI -> this hook -> assetService. The canvas reads the icons through `useKitLibrary`.
 */
import { useMutation } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { kitLibraryClient } from '@/lib/dealer-kit/kit-library-cache';
import {
  setAssetShowWhen,
  type AssetShowWhenBody,
  type KitAsset,
} from '../services/assetService';

export function useSetAssetShowWhen() {
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetShowWhenBody }) =>
      setAssetShowWhen(id, body),
    onSuccess: (asset: KitAsset) => {
      // The canvas reads the library through its own cache (`useKitLibrary`).
      void kitLibraryClient.invalidateQueries({ queryKey: ['dealer-kit', 'library', 'assets'] });
      toast.success(asset.show_when_spec_key ? `${asset.name} rule saved` : `${asset.name} rule cleared`);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to save the show when rule');
    },
  });
}
