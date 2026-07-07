/**
 * useProducts Hook
 * 
 * Main CRUD hook for products using React Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  getProducts,
  getProduct,
  createProduct,
  updateProduct,
  deleteProduct,
  duplicateProduct,
  bulkUpdateProducts,
  bulkDeleteProducts,
  getPriceHistory,
  setVariantParent,
  unlinkVariant,
  resetVariantAuto,
  PRODUCT_NEIGHBOURS_PATH,
  type GetProductsParams,
} from '../services/productService';
import type {
  Product,
  ProductFormData,
  ProductDetail,
  PriceHistory,
} from '../types/product.types';

/**
 * Hook for fetching products list with pagination, sorting, and filtering
 */
export function useProducts(params: GetProductsParams) {
  return useQuery({
    queryKey: [
      'products',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.category_id,
      params.brand_id,
      params.status,
      params.price_min,
      params.price_max,
      params.item_type,
      params.variant_filter,
      params.discontinued_batch_id,
    ],
    queryFn: () => getProducts(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
}

/** List query the products detail nav forwards to the neighbours endpoint. */
export type ProductNeighboursListParams = DataGridApiFetchParams & {
  category_id?: string;
  brand_id?: string;
  status?: string;
  discontinued_batch_id?: string;
};

/**
 * Prev/next neighbours of a product within the active filtered+sorted list set.
 * Serializes the list query (search/sort + category/brand/status/discontinued
 * batch filters) with `buildDataGridParams` — the same serialization the list
 * page uses — so the backend honours filters identically. `page`/`limit` are
 * sent but ignored by the neighbours endpoint.
 */
export function useProductNeighbours(
  productId: string | null,
  listParams: ProductNeighboursListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, {
    category_id: listParams.category_id,
    brand_id: listParams.brand_id,
    status: listParams.status,
    discontinued_batch_id: listParams.discontinued_batch_id,
  });
  return useRecordNeighbours(PRODUCT_NEIGHBOURS_PATH, productId, params);
}

/**
 * Hook for fetching single product by ID
 */
export function useProduct(id: string | null) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => {
      if (!id) throw new Error('Product ID is required');
      return getProduct(id);
    },
    enabled: !!id,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

/**
 * Hook for fetching product price history
 */
export function useProductPriceHistory(id: string | null) {
  return useQuery({
    queryKey: ['product-price-history', id],
    queryFn: () => {
      if (!id) throw new Error('Product ID is required');
      return getPriceHistory(id);
    },
    enabled: !!id,
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 1,
  });
}

/**
 * Hook for creating a new product
 */
export function useCreateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProductFormData) => createProduct(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Product created successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to create product', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for updating a product
 */
export function useUpdateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ProductFormData> }) =>
      updateProduct(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', variables.id] });
      toast.success('Product updated successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update product', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for setting / changing a product's variant parent (manual curation).
 *
 * Reused for "Add variant" (attach a child): call with the CHILD's id as
 * `productId` and the current product's id as `parentId` — both ids are
 * invalidated so the parent detail's Variants list refreshes.
 */
export function useSetVariantParent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ productId, parentId }: { productId: string; parentId: string }) =>
      setVariantParent(productId, parentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', variables.productId] });
      if (variables.parentId) {
        queryClient.invalidateQueries({ queryKey: ['product', variables.parentId] });
      }
      toast.success('Variant parent updated', { position: 'top-center' });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to set variant parent', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for unlinking a product from its variant parent (manual curation).
 *
 * Reused for "Remove variant" (detach a child): call with the CHILD's id as
 * `productId` and the current product's id as `parentId` so the parent detail's
 * Variants list refreshes.
 */
export function useUnlinkVariant() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ productId }: { productId: string; parentId?: string }) =>
      unlinkVariant(productId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', variables.productId] });
      if (variables.parentId) {
        queryClient.invalidateQueries({ queryKey: ['product', variables.parentId] });
      }
      toast.success('Variant unlinked', { position: 'top-center' });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to unlink variant', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for resetting a manually-curated product back to automatic derivation.
 */
export function useResetVariantAuto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ productId }: { productId: string }) => resetVariantAuto(productId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['product', variables.productId] });
      toast.success('Reset to auto-linking', { position: 'top-center' });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to reset variant link', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for deleting a product
 */
export function useDeleteProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteProduct(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Product deleted successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete product', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for duplicating a product
 */
export function useDuplicateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, newProductCode }: { id: string; newProductCode: string }) =>
      duplicateProduct(id, newProductCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Product duplicated successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to duplicate product', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for bulk updating products
 */
export function useBulkUpdateProducts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      ids,
      updates,
    }: {
      ids: string[];
      updates: Partial<ProductFormData>;
    }) => bulkUpdateProducts(ids, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Products updated successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update products', {
        position: 'top-center',
      });
    },
  });
}

/**
 * Hook for bulk deleting products
 */
export function useBulkDeleteProducts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteProducts(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success('Products deleted successfully', {
        position: 'top-center',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete products', {
        position: 'top-center',
      });
    },
  });
}
