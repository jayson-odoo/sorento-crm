'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';

interface SupplierOption {
  id: string;
  supplier_code: string;
  supplier_name: string;
}

interface SupplierComboboxProps {
  value: string;
  onChange: (value: string) => void;
  suppliers: SupplierOption[];
  supplierFallback?: { id: string; supplier_code: string; supplier_name: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/** Thin domain wrapper over the standard SearchableSelect (label format + saved-value fallback). */
export function SupplierCombobox({
  value,
  onChange,
  suppliers = [],
  supplierFallback,
  placeholder = 'Select supplier',
  disabled,
  className,
}: SupplierComboboxProps) {
  const options = [
    ...suppliers,
    ...(supplierFallback && value && !suppliers.some((s) => s.id === supplierFallback.id)
      ? [supplierFallback]
      : []),
  ];

  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No supplier found."
      triggerClassName={className}
      options={options.map((s) => ({
        value: s.id,
        label: `${s.supplier_name} (${s.supplier_code})`,
        searchText: `${s.supplier_code} ${s.supplier_name}`,
      }))}
    />
  );
}
