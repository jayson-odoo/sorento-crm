import { useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { apiFetch } from '@/lib/api';
import type { CountrySelectItem } from '@/app/(protected)/master-data-management/countries/types/country.types';

export const useCountrySelectQuery = () => {
  const fetchCountryList = async (): Promise<CountrySelectItem[]> => {
    const response = await apiFetch('/api/v1/master-data/countries/select');

    if (!response.ok) {
      toast.error(
        'Something went wrong while loading countries. Please try again.',
        {
          position: 'top-center',
        },
      );
      return [];
    }

    return response.json();
  };

  return useQuery({
    queryKey: ['country-select'],
    queryFn: fetchCountryList,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnReconnect: false,
    retry: 1,
  });
};
