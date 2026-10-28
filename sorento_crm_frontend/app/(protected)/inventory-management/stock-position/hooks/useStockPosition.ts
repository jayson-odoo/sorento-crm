import { useQuery } from '@tanstack/react-query';
import type { DataGridParamsInput } from '@/lib/api-client';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { getStockPosition } from '../services/stockPositionService';
import type { StockPositionFilters } from '../services/stockPosition.types';

export const STOCK_POSITION_KEY = 'stock-position';

export function useStockPosition(params: DataGridParamsInput, filters: StockPositionFilters) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [STOCK_POSITION_KEY, params, filters],
    queryFn: () => getStockPosition(params, filters),
    staleTime: 60_000,
  });
}
