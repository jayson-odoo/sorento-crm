import { useQuery } from '@tanstack/react-query';
import {
  getOrderFulfilledComplaints,
  type FulfilledComplaint,
} from '../services/orderFulfilmentService';

/**
 * Complaints a Delivery Order fulfils (reverse of the complaint detail
 * "Fulfilment Delivery Orders" section).
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 */
export function useOrderFulfilledComplaints(orderId: string | null) {
  return useQuery<FulfilledComplaint[]>({
    queryKey: ['order-fulfilled-complaints', orderId],
    enabled: !!orderId,
    queryFn: () => getOrderFulfilledComplaints(orderId as string),
  });
}
