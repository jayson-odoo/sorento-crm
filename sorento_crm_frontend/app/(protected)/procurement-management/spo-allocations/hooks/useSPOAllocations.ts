import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getSPOAllocations,
  getSPOAllocationsGroupedByShipment,
  getSPOAllocation,
  createSPOAllocation,
  updateSPOAllocation,
  deleteSPOAllocation,
} from '../services/spoAllocationService';
import type {
  SPOAllocationFormData,
  ShipmentWithAllocationsGroup,
} from '../types/spoAllocation.types';
import type { GroupedByShipmentParams } from '../services/spoAllocationService';

export function useSPOAllocationsGroupedByShipment(params: GroupedByShipmentParams = {}) {
  return useQuery({
    queryKey: [
      'spo-allocations-grouped-by-shipment',
      params.page,
      params.limit,
      params.query,
      params.product_code,
      params.warehouse_id,
      params.receipt_status,
      params.sort,
      params.dir,
    ],
    queryFn: () => getSPOAllocationsGroupedByShipment(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSPOAllocations(
  params: DataGridApiFetchParams & {
    shipment_id?: string;
    warehouse_id?: string;
    receipt_status?: string;
  },
) {
  return useQuery({
    queryKey: [
      'spo-allocations',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.shipment_id,
      params.warehouse_id,
      params.receipt_status,
    ],
    queryFn: () => getSPOAllocations(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSPOAllocation(id: string | null) {
  return useQuery({
    queryKey: ['spo-allocation', id],
    queryFn: () => {
      if (!id) throw new Error('SPO allocation ID is required');
      return getSPOAllocation(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateSPOAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SPOAllocationFormData) => createSPOAllocation(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
      toast.success('SPO allocation created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create SPO allocation'),
  });
}

export function useUpdateSPOAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<SPOAllocationFormData>;
    }) => updateSPOAllocation(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
      queryClient.invalidateQueries({ queryKey: ['spo-allocation'] });
      toast.success('SPO allocation updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update SPO allocation'),
  });
}

export function useDeleteSPOAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSPOAllocation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
      toast.success('SPO allocation deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete SPO allocation'),
  });
}
