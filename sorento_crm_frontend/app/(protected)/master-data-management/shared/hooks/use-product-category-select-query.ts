import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import type { ProductCategory } from '@/app/(protected)/master-data-management/products/types/product.types';

export const useProductCategorySelectQuery = () => {
  const fetchCategoryList = async (): Promise<ProductCategory[]> => {
    const response = await apiFetch('/api/v1/master-data/product-categories/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading categories. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['product-category-select'],
    queryFn: fetchCategoryList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnReconnect: false,
    retry: 1,
  });
};
