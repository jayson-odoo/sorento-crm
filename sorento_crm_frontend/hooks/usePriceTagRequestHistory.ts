import { useQuery } from '@tanstack/react-query';
import { getPriceTagRequestHistory } from '@/services/priceTagRequestHistoryService';

export const priceTagRequestHistoryKey = (requestId: string | undefined) =>
  ['price-tag-request-history', requestId] as const;

/** STANDARD-HISTORY wave 5: a price tag request's History read. Mounted only while the tab is
 * open, and refetched each time it opens, so what was just done is on it. */
export function usePriceTagRequestHistory(requestId: string | undefined) {
  return useQuery({
    queryKey: priceTagRequestHistoryKey(requestId),
    queryFn: () => getPriceTagRequestHistory(requestId as string),
    enabled: Boolean(requestId),
    refetchOnMount: 'always',
  });
}
