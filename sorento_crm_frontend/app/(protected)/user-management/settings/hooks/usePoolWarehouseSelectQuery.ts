import { useQuery } from '@tanstack/react-query';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';

/**
 * Every active POOL warehouse - a bare code, no `-SUFFIX` group
 * (`PLAN-oi-request-cs-reserve.md` section 6c F1). The same reading the backend's own
 * PUT validation uses (`app/api/v1/user_management/settings.py`): a code containing a
 * hyphen is a group warehouse and is refused.
 *
 * No dedicated "list pools" endpoint exists - filtered client-side off the ordinary
 * warehouse list, the same as `useReserveRowOptions.ts`'s own site-pool resolution.
 */
export function usePoolWarehouseSelectQuery() {
  return useQuery({
    queryKey: ['pool-warehouse-select'],
    queryFn: async () => {
      const response = await getWarehouses({
        pageIndex: 0,
        pageSize: 200,
        sorting: [],
        is_active: true,
      });
      return (response.data ?? []).filter((warehouse) => !warehouse.warehouse_code.includes('-'));
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 1000 * 60 * 60,
    refetchOnReconnect: false,
    retry: 1,
  });
}
