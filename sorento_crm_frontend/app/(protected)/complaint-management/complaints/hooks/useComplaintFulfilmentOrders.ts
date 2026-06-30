import { useQuery } from '@tanstack/react-query';
import {
  getComplaintFulfilmentOrders,
  type FulfilmentOrder,
} from '../services/complaintFulfilmentService';

/**
 * Replacement / fulfilment Delivery Orders linked to a complaint.
 * See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
 */
export function useComplaintFulfilmentOrders(complaintId: string | null) {
  return useQuery<FulfilmentOrder[]>({
    queryKey: ['complaint-fulfilment-orders', complaintId],
    enabled: !!complaintId,
    queryFn: () => getComplaintFulfilmentOrders(complaintId as string),
  });
}
