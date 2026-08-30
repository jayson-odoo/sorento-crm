import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getCategoriesTree,
  getCategory,
  createCategory,
  updateCategory,
  moveCategory,
} from '../services/categoryService';
import type { CategoryFormData, CategoryTreeItem } from '../types/category.types';

export function useCategoriesTree() {
  return useQuery({
    queryKey: ['product-categories-tree'],
    queryFn: getCategoriesTree,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

export function useCategory(id: string | null) {
  return useQuery({
    queryKey: ['product-category', id],
    queryFn: () => {
      if (!id) throw new Error('Category ID is required');
      return getCategory(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CategoryFormData) => createCategory(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-categories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['product-category-select'] });
      toast.success('Category created successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to create category');
    },
  });
}

export function useUpdateCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CategoryFormData> }) =>
      updateCategory(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-categories-tree'] });
      queryClient.invalidateQueries({ queryKey: ['product-category'] });
      queryClient.invalidateQueries({ queryKey: ['product-category-select'] });
      toast.success('Category updated successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update category');
    },
  });
}

export function useMoveCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, parentId, displayOrder }: { id: string; parentId: string | null; displayOrder: number }) =>
      moveCategory(id, parentId, displayOrder),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-categories-tree'] });
      toast.success('Category moved successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to move category');
    },
  });
}
