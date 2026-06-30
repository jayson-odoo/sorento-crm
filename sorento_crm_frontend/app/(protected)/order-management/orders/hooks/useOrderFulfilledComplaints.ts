import { useQuery } from '@tanstack/react-query';
import type { FulfilledComplaint } from '../services/orderFulfilmentService';
import { mockOrderFulfilledComplaints } from '../__mocks__/orderFulfilledComplaints';

/**
 * PHASE 1 STUB — returns mock fixtures (no backend call). Phase 2 swaps the
 * queryFn for `getOrderFulfilledComplaints(orderId)` from
 * services/orderFulfilmentService; the component contract stays identical.
 */
export function useOrderFulfilledComplaints(orderId: string | null) {
  return useQuery<FulfilledComplaint[]>({
    queryKey: ['order-fulfilled-complaints', orderId],
    enabled: !!orderId,
    queryFn: async () => {
      await new Promise((resolve) => setTimeout(resolve, 150));
      return mockOrderFulfilledComplaints(orderId as string);
    },
  });
}
