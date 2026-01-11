/**
 * useProductFilters Hook
 * 
 * Filter state management for products
 */

import { useState, useCallback, useMemo } from 'react';
import type { ProductFilters } from '../types/product.types';

export interface UseProductFiltersReturn {
  filters: ProductFilters;
  setCategoryId: (categoryId: string | undefined) => void;
  setBrandId: (brandId: string | undefined) => void;
  setStatus: (status: boolean | undefined) => void;
  setPriceRange: (min?: number, max?: number) => void;
  setSearch: (search: string | undefined) => void;
  setItemType: (itemType: string | undefined) => void;
  clearFilters: () => void;
  hasActiveFilters: boolean;
}

const initialFilters: ProductFilters = {};

/**
 * Hook for managing product filter state
 */
export function useProductFilters(): UseProductFiltersReturn {
  const [filters, setFilters] = useState<ProductFilters>(initialFilters);

  const setCategoryId = useCallback((categoryId: string | undefined) => {
    setFilters((prev) => ({
      ...prev,
      category_id: categoryId,
    }));
  }, []);

  const setBrandId = useCallback((brandId: string | undefined) => {
    setFilters((prev) => ({
      ...prev,
      brand_id: brandId,
    }));
  }, []);

  const setStatus = useCallback((status: boolean | undefined) => {
    setFilters((prev) => ({
      ...prev,
      is_active: status,
    }));
  }, []);

  const setPriceRange = useCallback((min?: number, max?: number) => {
    setFilters((prev) => ({
      ...prev,
      price_range: min !== undefined || max !== undefined
        ? { min, max }
        : undefined,
    }));
  }, []);

  const setSearch = useCallback((search: string | undefined) => {
    setFilters((prev) => ({
      ...prev,
      search: search || undefined,
    }));
  }, []);

  const setItemType = useCallback((itemType: string | undefined) => {
    setFilters((prev) => ({
      ...prev,
      item_type: itemType as any,
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(initialFilters);
  }, []);

  const hasActiveFilters = useMemo(() => {
    return !!(
      filters.category_id ||
      filters.brand_id ||
      filters.is_active !== undefined ||
      filters.price_range ||
      filters.search ||
      filters.item_type
    );
  }, [filters]);

  return {
    filters,
    setCategoryId,
    setBrandId,
    setStatus,
    setPriceRange,
    setSearch,
    setItemType,
    clearFilters,
    hasActiveFilters,
  };
}
