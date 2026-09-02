import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { toast } from 'sonner';
import type { SortingState } from '@tanstack/react-table';
import {
  getDeadStockDays,
  getDemandExplain,
  getDemandSeries,
  getNetPosition,
  getProducts,
  getRollups,
  getSuppliers,
  getWarehouseHealth,
  setDeadStockDays,
  type ProductsQuery,
  type ScmFilters,
} from '../services/scmDashboardService';
import type { HealthState } from '../types/scm.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

const baseOptions = {
  staleTime: 30_000,
  retry: 1,
} as const;

export function useScmRollups(filters: ScmFilters) {
  return useQuery({
    queryKey: ['scm', 'rollups', filters],
    queryFn: () => getRollups(filters),
    ...baseOptions,
  });
}

export function useWarehouseHealth(filters: ScmFilters) {
  return useQuery({
    queryKey: ['scm', 'warehouses', filters],
    queryFn: () => getWarehouseHealth(filters),
    ...baseOptions,
  });
}

export function useNetPosition(
  filters: ScmFilters,
  pagination: { pageIndex: number; pageSize: number },
  sorting: SortingState,
  searchQuery: string,
) {
  const sortField = sorting?.[0]?.id;
  const sortDir: 'asc' | 'desc' = sorting?.[0]?.desc ? 'desc' : 'asc';
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['scm', 'net-position', filters, pagination, sorting, searchQuery],
    queryFn: () =>
      getNetPosition({
        ...filters,
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sortField,
        sortDir,
        searchQuery,
      }),
    ...baseOptions,
  });
}

export function useSuppliers(filters: ScmFilters) {
  return useQuery({
    queryKey: ['scm', 'suppliers', filters],
    queryFn: () => getSuppliers(filters),
    ...baseOptions,
  });
}

/**
 * Drill-down product list for the "what's behind this number?" popups. Only
 * fetches while a drill target is open (`enabled`), so the numbers stay cheap.
 * `query` carries the popup's server-side search / sort / pagination; previous
 * data is kept while paging/searching so the table doesn't flash empty.
 */
export function useScmProducts(
  filters: ScmFilters,
  target: { status?: HealthState | null; warehouse?: string | null } | null,
  query: Omit<ProductsQuery, 'status' | 'warehouse'> = {},
) {
  return useQuery({
    queryKey: ['scm', 'products', filters, target, query],
    queryFn: () => getProducts(filters, { ...target, ...query }),
    enabled: !!target,
    placeholderData: keepPreviousData,
    ...baseOptions,
  });
}

/**
 * ~12-month DO-outflow trend for one SKU, fetched lazily when the Product row is
 * expanded (`enabled`). Previous data is kept across expand/collapse so the
 * sparkline doesn't flash. SKU is the human product code (never a UUID).
 */
export function useDemandSeries(
  sku: string,
  warehouse: string | null | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'demand-series', sku, warehouse ?? null],
    queryFn: () => getDemandSeries(sku, warehouse),
    enabled: enabled && !!sku,
    ...baseOptions,
  });
}

/**
 * The delivery orders + rate behind one product×warehouse avg-daily-demand,
 * fetched lazily when the drill popover opens (`enabled`). Takes the UUIDs the
 * drill row carries for this fetch only (never displayed). Idle until opened.
 */
export function useDemandExplain(
  productId: string | null | undefined,
  warehouseId: string | null | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['scm', 'demand-explain', productId ?? null, warehouseId ?? null],
    queryFn: () => getDemandExplain(productId as string, warehouseId),
    enabled: enabled && !!productId,
    ...baseOptions,
  });
}

/** Global dead-stock threshold (days) - drives the M1 "dead" status. */
export function useDeadStockDays() {
  return useQuery({
    queryKey: ['scm', 'config', 'dead-stock-days'],
    queryFn: getDeadStockDays,
    ...baseOptions,
  });
}

/**
 * Save the dead-stock threshold. On success: refresh the setting, then
 * invalidate every dashboard query so statuses / counts recompute against the
 * new window.
 */
export function useSaveDeadStockDays() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (days: number) => setDeadStockDays(days),
    onSuccess: (days) => {
      qc.setQueryData(['scm', 'config', 'dead-stock-days'], days);
      // Statuses/counts across rollups, warehouses, suppliers, net-position and
      // the drill-down popups all depend on the dead-stock window.
      for (const key of ['rollups', 'warehouses', 'suppliers', 'net-position', 'products']) {
        void qc.invalidateQueries({ queryKey: ['scm', key] });
      }
      toast.success(`Dead-stock threshold set to ${days} days`);
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to save dead-stock setting');
    },
  });
}
