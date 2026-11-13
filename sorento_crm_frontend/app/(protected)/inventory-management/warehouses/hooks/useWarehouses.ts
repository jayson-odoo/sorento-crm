import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getWarehouses, getWarehouse, createWarehouse, updateWarehouse, bulkDeleteWarehouses } from '../services/warehouseService';
import type { Warehouse, WarehouseFormData } from '../types/warehouse.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function warehousesListQueryKey(params: DataGridApiFetchParams): QueryKey {
  return [
    'warehouses',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function warehousesListParamsFromUrl(params: ListPagerParams): DataGridApiFetchParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
  };
}

/** The pager's two hooks into the warehouses list. */
export const warehousesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    warehousesListQueryKey(warehousesListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getWarehouses(warehousesListParamsFromUrl(params)),
};

export function useWarehouses(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: warehousesListQueryKey(params),
    queryFn: () => getWarehouses(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useWarehouse(id: string | null) {
  return useQuery({
    queryKey: ['warehouse', id],
    queryFn: () => {
      if (!id) throw new Error('Warehouse ID is required');
      return getWarehouse(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: WarehouseFormData) => createWarehouse(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      toast.success('Warehouse created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create warehouse'),
  });
}

export function useUpdateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<WarehouseFormData> }) => updateWarehouse(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      queryClient.invalidateQueries({ queryKey: ['warehouse'] });
      toast.success('Warehouse updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update warehouse'),
  });
}

// There is deliberately no `useDeleteWarehouse`. Single delete is a deferred record
// action since S6b: the record page parks `warehouse.delete` and the countdown, the
// toast and the invalidation all belong to `useDeferredAction`. A hook that toasted
// as well would report every outcome twice, in two positions, and a 409 ("Warehouse
// has linked stock") would say the same thing to the user twice.
// Bulk delete keeps its hook because `WarehouseBulkDeleteDialog` is a plain `Dialog`
// that owns no mutation of its own, so there is nothing for this one to double up with.

export function useBulkDeleteWarehouses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteWarehouses(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      if (result.failed?.length) {
        toast.warning(
          `Deleted ${result.deleted_count}; ${result.failed.length} failed (likely have linked stock/zones).`,
        );
      } else {
        toast.success(`Deleted ${result.deleted_count} warehouse${result.deleted_count === 1 ? '' : 's'}`);
      }
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete warehouses'),
  });
}

/**
 * One ACTIVE warehouse by its exact code, resolving a free-text location code (an order
 * inquiry line's `stock_location`) to its row.
 *
 * The ACTIVE company is asked first, so a code there reads exactly as it always did. Only
 * when it holds no such code is the read widened to every company the caller is granted
 * (`company_scope=grants`), and `widened` says so: a line filed in one company can name a
 * location another granted company holds. Codes are unique within a company only, so the
 * active company's own row always wins over a same-code row elsewhere. `warehouse` is null
 * when no granted company holds the code.
 *
 * `getWarehouses` has no exact-code param, and a text search for a bare pool code (`BRW`)
 * also matches its own sub-locations (`BRW-AA`..`BRW-EE`), so the page is wide enough to
 * reach the exact row behind them. Under `['warehouses']`, so a warehouse edit refreshes it.
 */
export function useWarehouseByCode(code: string | null) {
  return useQuery({
    queryKey: ['warehouses', 'by-code', code],
    queryFn: async (): Promise<{ warehouse: Warehouse | null; widened: boolean }> => {
      const find = async (companyScope?: 'grants') => {
        const response = await getWarehouses({
          pageIndex: 0,
          pageSize: 50,
          sorting: [],
          searchQuery: code ?? '',
          is_active: true,
          ...(companyScope ? { companyScope } : {}),
        });
        return (response.data ?? []).find((warehouse) => warehouse.warehouse_code === code) ?? null;
      };
      const own = await find();
      if (own) return { warehouse: own, widened: false };
      const granted = await find('grants');
      return { warehouse: granted, widened: Boolean(granted) };
    },
    enabled: Boolean(code),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
