import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * Warehouses as a searchable select, for the Stock location cell (captain, 19 Aug 2026).
 *
 * Keyed by CODE, not id: `ProjectSalesOrderLine.stock_location` (D17) is a free-text column
 * with no `warehouse_id` FK, so the value this feature writes and reads back IS the
 * warehouse code, exactly what a person already types on the AutoCount side.
 */
export async function fetchWarehouseOptions(query: string): Promise<SearchableSelectOption[]> {
  const response = await getWarehouses({
    pageIndex: 0,
    pageSize: 50,
    sorting: [{ id: 'warehouse_code', desc: false }],
    searchQuery: query,
    is_active: true,
  });
  return (response.data ?? []).map((warehouse) => ({
    value: warehouse.warehouse_code,
    label: warehouse.warehouse_name
      ? `${warehouse.warehouse_code} - ${warehouse.warehouse_name}`
      : warehouse.warehouse_code,
    searchText: `${warehouse.warehouse_code} ${warehouse.warehouse_name ?? ''}`,
  }));
}
