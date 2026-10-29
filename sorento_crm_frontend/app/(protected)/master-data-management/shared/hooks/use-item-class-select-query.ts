import { useQuery } from '@tanstack/react-query';
import { getItemClassSelect } from '@/app/(protected)/master-data-management/item-classes/services/itemClassService';
import type { ItemClassSelectItem } from '@/app/(protected)/master-data-management/item-classes/types/item-class.types';

/**
 * Active item classes. With `brandId`, only the classes some product of that brand carries.
 * Throws on failure (never-stuck rule) so the picker says "could not load" instead of empty.
 */
export const useItemClassSelectQuery = (brandId?: string) => {
  return useQuery<ItemClassSelectItem[]>({
    queryKey: ['item-class-select', brandId ?? null],
    queryFn: () => getItemClassSelect(brandId),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnReconnect: false,
    retry: 1,
  });
};
