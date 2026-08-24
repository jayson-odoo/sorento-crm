import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  CUSTOMER_NEIGHBOURS_PATH,
  getCustomers,
  getCustomer,
  createCustomer,
  updateCustomer,
  deleteCustomer,
} from '../services/customerService';
import type { CustomerFormData } from '../types/customer.types';

/**
 * Prev/next neighbours of a customer within the active filtered+sorted list set.
 * Serializes the list query (search/sort) with `buildDataGridParams` - the same
 * serialization the list page uses - so the backend honours filters identically.
 * `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useCustomerNeighbours(
  customerId: string | null,
  listParams: DataGridApiFetchParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams);
  return useRecordNeighbours(CUSTOMER_NEIGHBOURS_PATH, customerId, params);
}

export function useCustomers(params: DataGridApiFetchParams & { status?: string }) {
  return useQuery({
    queryKey: ['customers', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.status],
    queryFn: () => getCustomers(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCustomer(id: string | null) {
  return useQuery({
    queryKey: ['customer', id],
    queryFn: () => {
      if (!id) throw new Error('Customer ID is required');
      return getCustomer(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CustomerFormData) => createCustomer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      toast.success('Customer created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create customer'),
  });
}

export function useUpdateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CustomerFormData> }) => updateCustomer(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['customer'] });
      toast.success('Customer updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update customer'),
  });
}

export function useDeleteCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCustomer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      toast.success('Customer deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete customer'),
  });
}
