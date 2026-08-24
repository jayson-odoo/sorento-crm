'use client';

import { useEffect, useRef } from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';

interface ProductOption {
  id: string;
  product_code: string;
  product_name?: string;
}

interface ProductComboboxProps {
  value: string;
  onChange: (value: string) => void;
  products: ProductOption[];
  productFallback?: { id: string; product_code: string; product_name?: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Server-side search callback, debounced 300ms, so the parent can refetch from
   *  `/products?query=...` rather than relying on the local slice. */
  onSearch?: (query: string) => void;
}

/**
 * Thin domain wrapper over the standard SearchableSelect: owns the product label format,
 * the saved-value fallback, and the debounce in front of the parent's server refetch.
 */
export function ProductCombobox({
  value,
  onChange,
  products = [],
  productFallback,
  placeholder = 'Select product',
  disabled,
  className,
  onSearch,
}: ProductComboboxProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  // 300ms balances responsiveness against backend hit rate while typing - the standard
  // component reports every keystroke, so the debounce lives here.
  const handleSearch = (query: string) => {
    if (!onSearch) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onSearch(query), 300);
  };

  const options = [
    ...products,
    // Keep the saved product selectable even when it is absent from the current page.
    ...(productFallback && value && !products.some((p) => p.id === productFallback.id)
      ? [productFallback]
      : []),
  ];

  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No product found."
      triggerClassName={className}
      onSearchChange={onSearch ? handleSearch : undefined}
      options={options.map((p) => ({
        value: p.id,
        label: `${p.product_code}${p.product_name ? ` - ${p.product_name}` : ''}`,
        searchText: `${p.product_code} ${p.product_name ?? ''}`,
      }))}
      renderTriggerLabel={(opt) => {
        const p = options.find((o) => o.id === opt.value);
        if (!p) return opt.label;
        return `${p.product_code}${p.product_name && p.product_name !== p.product_code ? ` - ${p.product_name}` : ''}`;
      }}
    />
  );
}
