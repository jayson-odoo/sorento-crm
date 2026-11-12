import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  createTechnician,
  deleteTechnician,
  getTechnicians,
  updateTechnician,
  type TechniciansListParams,
} from '../services/technicianService';
import type { TechnicianFormValues } from '../types/technician.types';

export function useTechnicians(params: TechniciansListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      'technicians',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.employment_type?.join(',') ?? '',
      params.is_active?.join(',') ?? '',
    ],
    queryFn: () => getTechnicians(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useTechnicianMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['technicians'] });
    void queryClient.invalidateQueries({ queryKey: ['technicians-select'] });
  };
  const create = useMutation({
    mutationFn: (values: TechnicianFormValues) => createTechnician(values),
    onSuccess: () => {
      refresh();
      toast.success('Technician created');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create the technician'),
  });
  const update = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Partial<TechnicianFormValues> & { is_active?: boolean } }) =>
      updateTechnician(id, values),
    onSuccess: () => {
      refresh();
      toast.success('Technician updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update the technician'),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteTechnician(id),
    onSuccess: () => {
      refresh();
      toast.success('Technician deleted');
    },
    // The server refuses a technician that is on a job; the countdown button shows that message.
    onError: (e: Error) => toast.error(e.message || 'Failed to delete the technician'),
  });
  return { create, update, remove };
}
