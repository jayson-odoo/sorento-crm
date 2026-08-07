import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { SortingState } from '@tanstack/react-table';
import {
  createDoFromSalesOrder,
  createSalesOrder,
  deleteSalesOrder,
  getSalesOrder,
  getSalesOrders,
  updateSalesOrder,
} from '../services/salesOrderService';
import type { SalesOrderFormData } from '../types/scm.types';

interface UseSalesOrdersParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  status: string | null;
  priority: string | null;
  /** Where the order came from: 'inquiry' | 'upload' | 'manual'. Null for all. */
  source?: string | null;
}

export function useSalesOrders(params: UseSalesOrdersParams) {
  return useQuery({
    queryKey: ['scm', 'sales-orders', params],
    queryFn: () =>
      getSalesOrders({
        pageIndex: params.pageIndex,
        pageSize: params.pageSize,
        sortField: params.sorting?.[0]?.id,
        sortDir: params.sorting?.[0]?.desc ? 'desc' : 'asc',
        searchQuery: params.searchQuery,
        status: params.status,
        priority: params.priority,
        source: params.source ?? null,
      }),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** One sales order, for the detail page. Mirrors `usePurchaseOrder`. */
export function useSalesOrder(id: string | null) {
  return useQuery({
    queryKey: ['scm', 'sales-orders', 'detail', id],
    queryFn: () => getSalesOrder(id as string),
    enabled: !!id,
    staleTime: 5_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreateSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SalesOrderFormData) => createSalesOrder(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scm', 'sales-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'net-position'] });
      toast.success('Sales order created');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create sales order'),
  });
}

export function useUpdateSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SalesOrderFormData }) =>
      updateSalesOrder(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scm', 'sales-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'net-position'] });
      toast.success('Sales order updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update sales order'),
  });
}

export function useDeleteSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSalesOrder(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scm', 'sales-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'net-position'] });
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete sales order'),
  });
}

export function useCreateDoFromSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => createDoFromSalesOrder(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['scm', 'sales-orders'] });
      qc.invalidateQueries({ queryKey: ['scm', 'net-position'] });
      qc.invalidateQueries({ queryKey: ['scm', 'rollups'] });
      toast.success(`Delivery order ${res.do_number} created`);
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create delivery order'),
  });
}
