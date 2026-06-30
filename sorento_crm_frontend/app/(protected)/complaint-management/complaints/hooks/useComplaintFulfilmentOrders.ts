import { useQuery } from '@tanstack/react-query';
import type { FulfilmentOrder } from '../services/complaintFulfilmentService';
import { mockComplaintFulfilmentOrders } from '../__mocks__/complaintFulfilmentOrders';

/**
 * PHASE 1 STUB — returns mock fixtures (no backend call). Phase 2 swaps the
 * queryFn for `getComplaintFulfilmentOrders(complaintId)` from
 * services/complaintFulfilmentService; the component contract stays identical.
 */
export function useComplaintFulfilmentOrders(complaintId: string | null) {
  return useQuery<FulfilmentOrder[]>({
    queryKey: ['complaint-fulfilment-orders', complaintId],
    enabled: !!complaintId,
    queryFn: async () => {
      // Tiny delay so the loading state is exercisable in the prototype.
      await new Promise((resolve) => setTimeout(resolve, 150));
      return mockComplaintFulfilmentOrders(complaintId as string);
    },
  });
}
