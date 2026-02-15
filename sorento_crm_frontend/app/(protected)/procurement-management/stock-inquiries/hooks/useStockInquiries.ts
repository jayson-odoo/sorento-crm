import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getStockInquiries,
  getStockInquiry,
  getStockInquiryNeighbours,
  createStockInquiry,
  updateStockInquiry,
  updateStockInquiryAndReply,
  deleteStockInquiry,
} from '../services/stockInquiryService';
import type { StockInquiryFormData } from '../types/stockInquiry.types';

export function useStockInquiries(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [
      'stock-inquiries',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getStockInquiries(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useStockInquiry(id: string | null) {
  return useQuery({
    queryKey: ['stock-inquiry', id],
    queryFn: () => {
      if (!id) throw new Error('Stock inquiry ID is required');
      return getStockInquiry(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useStockInquiryNeighbours(id: string | null) {
  return useQuery({
    queryKey: ['stock-inquiry-neighbours', id],
    queryFn: () => {
      if (!id) return { prev_id: null, next_id: null };
      return getStockInquiryNeighbours(id);
    },
    enabled: !!id,
    staleTime: 60 * 1000,
  });
}

export function useCreateStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: StockInquiryFormData) => createStockInquiry(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Stock inquiry created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create stock inquiry'),
  });
}

export function useUpdateStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<StockInquiryFormData>;
    }) => updateStockInquiry(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
      toast.success('Stock inquiry updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update stock inquiry'),
  });
}

export function useUpdateStockInquiryAndReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<StockInquiryFormData>;
    }) => updateStockInquiryAndReply(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      queryClient.invalidateQueries({ queryKey: ['stock-inquiry'] });
      toast.success('Reply sent to customer successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update and reply'),
  });
}

export function useDeleteStockInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteStockInquiry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-inquiries'] });
      toast.success('Stock inquiry deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete stock inquiry'),
  });
}
