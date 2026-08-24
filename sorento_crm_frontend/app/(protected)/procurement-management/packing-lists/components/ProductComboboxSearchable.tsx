'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';

const PAGE_SIZE = 50;

export interface ProductOption {
  id: string;
  product_code: string;
  product_name?: string;
}

export interface ProductComboboxSearchableProps {
  value: string;
  onChange: (value: string) => void;
  /** Fetch products from API: (searchQuery, pageIndex) => Promise<{ data: ProductOption[] }> */
  fetchProducts: (query: string, pageIndex: number) => Promise<{ data: ProductOption[] }>;
  productFallback?: ProductOption | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

const itemLabel = (p: ProductOption) =>
  `${p.product_code}${p.product_name ? ` - ${p.product_name}` : ''}`;

/**
 * Server-searched, paginated product picker. Now a thin wrapper over the standard
 * SearchableSelect's async + paginated mode - the debounce, stale-response dropping and
 * page accumulation it used to hand-roll all live in the component.
 */
export function ProductComboboxSearchable({
  value,
  onChange,
  fetchProducts,
  productFallback,
  placeholder = 'Search or select product',
  disabled,
  className,
}: ProductComboboxSearchableProps) {
  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No product found."
      triggerClassName={className}
      paginated
      pageSize={PAGE_SIZE}
      fetchOptions={async (query, pageIndex) => {
        const { data } = await fetchProducts(query, pageIndex);
        return data.map((p) => ({
          value: p.id,
          label: itemLabel(p),
          searchText: `${p.product_code} ${p.product_name ?? ''}`,
        }));
      }}
      // The saved product is rarely in the first page, so without this the trigger
      // would show nothing when editing an existing row.
      selectedOption={
        productFallback && value === productFallback.id
          ? { value: productFallback.id, label: itemLabel(productFallback) }
          : undefined
      }
      renderTriggerLabel={(opt) => {
        const p = productFallback && productFallback.id === opt.value ? productFallback : null;
        if (!p) return opt.label;
        return `${p.product_code}${p.product_name && p.product_name !== p.product_code ? ` - ${p.product_name}` : ''}`;
      }}
    />
  );
}
