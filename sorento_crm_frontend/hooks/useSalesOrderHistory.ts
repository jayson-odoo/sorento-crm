import { useQuery } from '@tanstack/react-query';
import {
  getProjectSalesOrderHistory,
  getScmSalesOrderHistory,
} from '@/services/salesOrderHistoryService';

/** STANDARD-HISTORY wave 2: a sales order's History read, project or SCM. Refetched each time a
 * view opens, so what was just done is on it. */
export function useSalesOrderHistory(source: 'project' | 'scm', id: string | undefined) {
  return useQuery({
    queryKey: ['sales-order-history', source, id],
    queryFn: () =>
      source === 'scm' ? getScmSalesOrderHistory(id as string) : getProjectSalesOrderHistory(id as string),
    enabled: Boolean(id),
    refetchOnMount: 'always',
  });
}
