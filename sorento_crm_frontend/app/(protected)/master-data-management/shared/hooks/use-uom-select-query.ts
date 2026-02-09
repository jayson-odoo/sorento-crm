import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import type { UnitOfMeasure } from '@/app/(protected)/master-data-management/products/types/product.types';

export const useUOMSelectQuery = () => {
  const fetchUOMList = async (): Promise<UnitOfMeasure[]> => {
    const response = await apiFetch('/api/v1/master-data/units-of-measure/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading units of measure. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['uom-select'],
    queryFn: fetchUOMList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
};
