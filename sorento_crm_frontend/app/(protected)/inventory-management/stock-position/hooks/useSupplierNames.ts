import { useQueries } from '@tanstack/react-query';
import { getSupplier } from '@/app/(protected)/procurement-management/suppliers/services/supplierService';

/**
 * Names for chosen supplier ids the screen has no name for yet (a restored filter whose supplier
 * is on no row of this page and was never in the picker's pages), so the trigger names it rather
 * than saying "Selected supplier". Same cache key as `useSupplier`, so a name is fetched once.
 */
export function useSupplierNames(ids: string[]): Record<string, string> {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: ['supplier', id],
      queryFn: () => getSupplier(id),
      staleTime: 5 * 60_000,
      retry: 1,
    })),
    combine: (results) => {
      const names: Record<string, string> = {};
      results.forEach((r, i) => {
        if (r.data?.supplier_name) names[ids[i]] = r.data.supplier_name;
      });
      return names;
    },
  });
}
