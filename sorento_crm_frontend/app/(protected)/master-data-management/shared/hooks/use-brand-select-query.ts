import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import type { Brand } from '@/app/(protected)/master-data-management/products/types/product.types';

export const useBrandSelectQuery = () => {
  const fetchBrandList = async (): Promise<Brand[]> => {
    const response = await apiFetch('/api/v1/master-data/brands/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading brands. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['brand-select'],
    queryFn: fetchBrandList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnReconnect: false,
    retry: 1,
  });
};
