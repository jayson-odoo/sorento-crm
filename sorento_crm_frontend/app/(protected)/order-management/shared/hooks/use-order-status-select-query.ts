import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';

export interface OrderStatusSelectOption {
  id: string;
  status_code: string;
  status_name: string;
}

export const useOrderStatusSelectQuery = () => {
  const fetchOrderStatusList = async (): Promise<OrderStatusSelectOption[]> => {
    const response = await apiFetch('/api/v1/order-management/order-statuses/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading order statuses. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['order-status-select'],
    queryFn: fetchOrderStatusList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
};
