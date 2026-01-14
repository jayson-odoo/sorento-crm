import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPackingLists,
  getPackingList,
  createPackingList,
  updatePackingList,
  deletePackingList,
} from '../services/packingListService';
import type { PackingListFormData } from '../types/packingList.types';

export function usePackingLists(
  params: DataGridApiFetchParams & {
    supplier_id?: string;
    shipment_status?: string;
  },
) {
  return useQuery({
    queryKey: [
      'packing-lists',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.supplier_id,
      params.shipment_status,
    ],
    queryFn: () => getPackingLists(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function usePackingList(id: string | null) {
  return useQuery({
    queryKey: ['packing-list', id],
    queryFn: () => {
      if (!id) throw new Error('Packing list ID is required');
      return getPackingList(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreatePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PackingListFormData) => createPackingList(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      toast.success('Packing list created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create packing list'),
  });
}

export function useUpdatePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<PackingListFormData>;
    }) => updatePackingList(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      queryClient.invalidateQueries({ queryKey: ['packing-list'] });
      toast.success('Packing list updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update packing list'),
  });
}

export function useDeletePackingList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePackingList(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packing-lists'] });
      toast.success('Packing list deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete packing list'),
  });
}
