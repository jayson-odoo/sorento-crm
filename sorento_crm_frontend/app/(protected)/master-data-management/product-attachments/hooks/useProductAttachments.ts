import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getProductAttachments,
  getProductAttachment,
  createProductAttachment,
  updateProductAttachment,
  deleteProductAttachment,
  getProductAttachmentsByProduct,
} from '../services/productAttachmentService';
import type { ProductAttachment, ProductAttachmentFormData } from '../types/productAttachment.types';

export function useProductAttachments(params: DataGridApiFetchParams & { product_id?: string; attachment_id?: string }) {
  return useQuery({
    queryKey: ['product-attachments', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.product_id, params.attachment_id],
    queryFn: () => getProductAttachments(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useProductAttachment(id: string | null) {
  return useQuery({
    queryKey: ['product-attachment', id],
    queryFn: () => getProductAttachment(id!),
    enabled: !!id,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreateProductAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProductAttachmentFormData) => createProductAttachment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product'] });
      toast.success('Product attachment created successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to create product attachment');
    },
  });
}

export function useUpdateProductAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ProductAttachmentFormData> }) => updateProductAttachment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['product-attachment'] });
      // The per-product list is what the product's Attachments tab reads, and choosing the
      // product photo (`is_primary`) writes through here. Without this the badge stays on the
      // old row until a reload.
      queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product'] });
      toast.success('Product attachment updated successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update product attachment');
    },
  });
}

export function useDeleteProductAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProductAttachment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-attachments'] });
      queryClient.invalidateQueries({ queryKey: ['product-attachment'] });
      queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product'] });
      toast.success('Product attachment deleted successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete product attachment');
    },
  });
}

export function useProductAttachmentsByProduct(productId: string | null) {
  return useQuery({
    queryKey: ['product-attachments-by-product', productId],
    queryFn: () => getProductAttachmentsByProduct(productId!),
    enabled: !!productId,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
