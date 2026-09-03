import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getPromotionAttachments,
  getPromotionAttachment,
  createPromotionAttachment,
  updatePromotionAttachment,
  deletePromotionAttachment,
  getPromotionAttachmentsByPromotion,
} from '../services/promotionAttachmentService';
import type { PromotionAttachment, PromotionAttachmentFormData } from '../types/promotionAttachment.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function usePromotionAttachments(params: DataGridApiFetchParams & { promotion_id?: string; attachment_id?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['promotion-attachments', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.promotion_id, params.attachment_id],
    queryFn: () => getPromotionAttachments(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function usePromotionAttachment(id: string | null) {
  return useQuery({
    queryKey: ['promotion-attachment', id],
    queryFn: () => getPromotionAttachment(id!),
    enabled: !!id,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useCreatePromotionAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PromotionAttachmentFormData) => createPromotionAttachment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion'] });
      toast.success('Promotion attachment created successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to create promotion attachment');
    },
  });
}

export function useUpdatePromotionAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PromotionAttachmentFormData> }) => updatePromotionAttachment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-attachment'] });
      toast.success('Promotion attachment updated successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update promotion attachment');
    },
  });
}

export function useDeletePromotionAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePromotionAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-attachment'] });
      queryClient.invalidateQueries({ queryKey: ['promotion-attachments-by-promotion'] });
      toast.success('Promotion attachment deleted successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete promotion attachment');
    },
  });
}

export function usePromotionAttachmentsByPromotion(promotionId: string | null) {
  return useQuery({
    queryKey: ['promotion-attachments-by-promotion', promotionId],
    queryFn: () => getPromotionAttachmentsByPromotion(promotionId!),
    enabled: !!promotionId,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}
