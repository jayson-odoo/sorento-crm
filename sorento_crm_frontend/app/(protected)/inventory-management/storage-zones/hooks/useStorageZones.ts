import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getStorageZonesTree, getStorageZone, createStorageZone, updateStorageZone, deleteStorageZone, moveStorageZone } from '../services/storageZoneService';
import type { StorageZoneFormData } from '../types/storageZone.types';

export function useStorageZonesTree(warehouseId?: string) {
  return useQuery({
    queryKey: ['storage-zones-tree', warehouseId],
    queryFn: () => getStorageZonesTree(warehouseId),
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });
}

export function useStorageZone(id: string | null) {
  return useQuery({
    queryKey: ['storage-zone', id],
    queryFn: () => {
      if (!id) throw new Error('Storage zone ID is required');
      return getStorageZone(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateStorageZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StorageZoneFormData) => createStorageZone(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-zones-tree'] });
      toast.success('Storage zone created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create storage zone'),
  });
}

export function useUpdateStorageZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<StorageZoneFormData> }) => updateStorageZone(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-zones-tree'] });
      queryClient.invalidateQueries({ queryKey: ['storage-zone'] });
      toast.success('Storage zone updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update storage zone'),
  });
}

export function useDeleteStorageZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStorageZone(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-zones-tree'] });
      toast.success('Storage zone deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete storage zone'),
  });
}

export function useMoveStorageZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, warehouseId, displayOrder }: { id: string; warehouseId: string; displayOrder: number }) =>
      moveStorageZone(id, warehouseId, displayOrder),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-zones-tree'] });
      toast.success('Storage zone moved successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to move storage zone'),
  });
}
