import { useQuery } from '@tanstack/react-query';
import {
  getCategoryOptions,
  getCustomerOptions,
  getOrderTypeOptions,
  getProductOptions,
  getSupplierOptions,
  getWarehouseOptions,
} from '../services/scmOptionsService';

const opts = { staleTime: 5 * 60_000, refetchOnWindowFocus: false, retry: 1 } as const;

export function useWarehouseOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'warehouses'], queryFn: getWarehouseOptions, ...opts });
}

export function useSupplierOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'suppliers'], queryFn: getSupplierOptions, ...opts });
}

export function useCategoryOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'categories'], queryFn: getCategoryOptions, ...opts });
}

export function useCustomerOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'customers'], queryFn: getCustomerOptions, ...opts });
}

export function useProductOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'products'], queryFn: getProductOptions, ...opts });
}

export function useOrderTypeOptions() {
  return useQuery({ queryKey: ['scm', 'opts', 'order-types'], queryFn: getOrderTypeOptions, ...opts });
}
