import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import {
  getItemClasses,
  getItemClass,
  createItemClass,
  updateItemClass,
} from '../services/itemClassService';
import type { ItemClassFormData } from '../types/item-class.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/** One key for the list and the detail pager, so a step reads the cached page. */
export function itemClassesListQueryKey(params: DataGridApiFetchParams): QueryKey {
  return ['item-classes', params.pageIndex, params.pageSize, params.sorting, params.searchQuery];
}

function paramsFromUrl(params: ListPagerParams): DataGridApiFetchParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
  };
}

/** The pager's two hooks into the item classes list. */
export const itemClassesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    itemClassesListQueryKey(paramsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getItemClasses(paramsFromUrl(params)),
};

export function useItemClasses(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: itemClassesListQueryKey(params),
    queryFn: () => getItemClasses(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useItemClass(id: string | null) {
  return useQuery({
    queryKey: ['item-class', id],
    queryFn: () => {
      if (!id) throw new Error('Item class id is required');
      return getItemClass(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateItemClass() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ItemClassFormData) => createItemClass(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['item-classes'] });
      queryClient.invalidateQueries({ queryKey: ['item-class-select'] });
      toast.success('Item class created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create item class'),
  });
}

export function useUpdateItemClass() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ItemClassFormData> }) =>
      updateItemClass(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['item-classes'] });
      queryClient.invalidateQueries({ queryKey: ['item-class'] });
      queryClient.invalidateQueries({ queryKey: ['item-class-select'] });
      toast.success('Item class updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update item class'),
  });
}
