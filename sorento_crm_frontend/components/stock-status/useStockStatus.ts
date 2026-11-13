import { useQuery } from '@tanstack/react-query';
import { getStockStatus } from './stockStatusService';

export const STOCK_STATUS_KEY = 'stock-status';

/**
 * AutoCount's figures for one item (`GET /api/v1/inventory/stock-status`): what the stock table
 * shows in Fulfilment Planning, the OI line expand, the project quotation and the stand-alone
 * page. Off until a product is known.
 */
export function useStockStatus(
  productId: string | null | undefined,
  enabled = true,
  /** `grants`: the OI grid reading a location that may be another granted company's. */
  companyScope?: 'grants',
) {
  return useQuery({
    queryKey: [STOCK_STATUS_KEY, productId, ...(companyScope ? [companyScope] : [])],
    queryFn: () =>
      companyScope
        ? getStockStatus(productId as string, null, companyScope)
        : getStockStatus(productId as string, null),
    enabled: enabled && Boolean(productId),
    staleTime: 60_000,
    retry: 1,
  });
}
