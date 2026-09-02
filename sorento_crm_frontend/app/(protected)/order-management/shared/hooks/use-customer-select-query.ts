import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';

export interface CustomerSelectOption {
  id: string;
  customer_code: string;
  customer_name: string;
}

export type UseCustomerSelectQueryOptions = {
  /** When false, the query does not run (e.g. dialog closed). */
  enabled?: boolean;
};

export const useCustomerSelectQuery = (options?: UseCustomerSelectQueryOptions) => {
  const enabled = options?.enabled ?? true;

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

    const json = await response.json();
    if (Array.isArray(json)) return json as CustomerSelectOption[];
    const rows = (json as { data?: CustomerSelectOption[] })?.data;
    return Array.isArray(rows) ? rows : [];
  };

  return useQuery({
    queryKey: ['customer-select'],
    queryFn: fetchCustomerList,
    enabled,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnReconnect: false,
    retry: 1,
  });
};
