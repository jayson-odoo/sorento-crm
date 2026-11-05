'use client';

/**
 * Feature icons (PRICETAG-DESIGNER-GAPS item 3): the rule-carrying icon library and the
 * "Show when" mutation. UI -> these hooks -> assetService.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { iconsFromAssets } from '@/lib/dealer-kit/feature-icons';
import {
  listAssets,
  setAssetShowWhen,
  type AssetShowWhenBody,
  type KitAsset,
} from '../services/assetService';

export const featureIconLibraryKey = ['dealer-kit-assets', 'icon'] as const;

/** The library's icons: rows (for URLs) and the rule-carrying ones as `FeatureIcon`s. */
export function useFeatureIconLibrary(enabled = true) {
  const query = useQuery({
    queryKey: featureIconLibraryKey,
    queryFn: () => listAssets({ kind: 'icon', limit: 100 }),
    enabled,
    staleTime: 60_000,
  });
  const rows = query.data ?? [];
  return { ...query, rows, icons: iconsFromAssets(rows) };
}

export function useSetAssetShowWhen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetShowWhenBody }) =>
      setAssetShowWhen(id, body),
    onSuccess: (asset: KitAsset) => {
      void queryClient.invalidateQueries({ queryKey: ['dealer-kit-assets'] });
      toast.success(asset.show_when_spec_key ? `${asset.name} rule saved` : `${asset.name} rule cleared`);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to save the show when rule');
    },
  });
}
