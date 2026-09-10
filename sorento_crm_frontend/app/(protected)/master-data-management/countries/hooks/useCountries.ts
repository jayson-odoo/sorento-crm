import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getCountries,
  getCountry,
  createCountry,
  updateCountry,
} from '../services/countryService';
import type { CountryFormData } from '../types/country.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useCountries(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['countries', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getCountries(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useCountry(id: string | null) {
  return useQuery({
    queryKey: ['country', id],
    queryFn: () => {
      if (!id) throw new Error('Country id is required');
      return getCountry(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateCountry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CountryFormData) => createCountry(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['countries'] });
      queryClient.invalidateQueries({ queryKey: ['country-select'] });
      toast.success('Country created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create country'),
  });
}

export function useUpdateCountry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CountryFormData> }) =>
      updateCountry(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['countries'] });
      queryClient.invalidateQueries({ queryKey: ['country'] });
      queryClient.invalidateQueries({ queryKey: ['country-select'] });
      toast.success('Country updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update country'),
  });
}
