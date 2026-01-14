import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';

export interface CustomerSelectOption {
  id: string;
  customer_code: string;
  customer_name: string;
}

export const useCustomerSelectQuery = () => {
  const fetchCustomerList = async (): Promise<CustomerSelectOption[]> => {
    const response = await apiFetch('/api/v1/order-management/customers/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading customers. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['customer-select'],
    queryFn: fetchCustomerList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
};
