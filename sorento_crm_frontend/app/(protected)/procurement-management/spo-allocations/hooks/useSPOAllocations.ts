import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getSPOAllocation,
  createSPOAllocation,
  updateSPOAllocation,
  deleteSPOAllocation,
} from '../services/spoAllocationService';
import type { SPOAllocationFormData } from '../types/spoAllocation.types';

// The bare list, the two grouped-by-* lists and their bulk delete were the
// standalone allocation list's hooks - retired with it (plan Q12/Q13, review S3):
// the document list + form view (`SPOAllocationsList`, `SPODocumentDetail`) read
// `hooks/useSPODocuments.ts` instead. What stays is what `SPOAllocationForm.tsx`
// (Create/Edit SPO Allocation) and the document form view's Save still call.

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

// No success toast on these two (review B2): the document form view's Save calls
// either mutation once PER CHANGED LINE (`Promise.allSettled`, `SPODocumentDetail`),
// and a toast per line would drown its own single closing sentence - the same
// reasoning `useUpdateAttachment` follows for `AttachmentsInFolderPanel`'s bulk
// move. `onError` stays: naming which line failed is worth one toast each.

export function useUpdateSPOAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Omit<Partial<SPOAllocationFormData>, 'warehouse_id' | 'supplier_id' | 'expected_date'> & {
        warehouse_id?: string | null;
        supplier_id?: string | null;
        expected_date?: string | null;
      };
    }) => updateSPOAllocation(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
      queryClient.invalidateQueries({ queryKey: ['spo-allocation'] });
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
      queryClient.invalidateQueries({ queryKey: ['spo-allocation'] });
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete SPO allocation'),
  });
}

