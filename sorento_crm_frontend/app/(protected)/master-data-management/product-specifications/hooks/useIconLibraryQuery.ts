'use client';

/**
 * The Dealer Kit icon library, for the feature icons a spec value carries (Values and words tab).
 * Behind `dealer_kit.library.manage` like the library itself, so the caller passes `enabled` from
 * that permission; without it the tab names icons from the registry row and offers no picker.
 */
import { useQuery } from '@tanstack/react-query';
import { listAssets, type KitAsset } from '@/app/(protected)/dealer-kit/services/assetService';

export const ICON_LIBRARY_QUERY_KEY = ['dealer-kit', 'icon-library'] as const;

export function useIconLibraryQuery(enabled: boolean) {
  return useQuery<KitAsset[]>({
    queryKey: ICON_LIBRARY_QUERY_KEY,
    queryFn: () => listAssets({ kind: 'icon', limit: 1000 }),
    enabled,
    staleTime: 60_000,
  });
}
