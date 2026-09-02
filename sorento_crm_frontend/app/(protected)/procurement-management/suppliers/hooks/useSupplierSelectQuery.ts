import { useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { apiFetch } from '@/lib/api';
import type { Supplier } from '../types/supplier.types';

export const useSupplierSelectQuery = () => {
  const fetchSupplierList = async (): Promise<Supplier[]> => {
    const response = await apiFetch('/api/v1/procurement/suppliers/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading suppliers. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['supplier-select'],
    queryFn: fetchSupplierList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
};
