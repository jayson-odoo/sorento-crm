'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';

interface WarehouseOption {
  id: string;
  warehouse_code: string;
  warehouse_name: string | null;
}

interface WarehouseComboboxProps {
  value: string;
  onChange: (value: string) => void;
  warehouses: WarehouseOption[];
  warehouseFallback?: { id: string; warehouse_code: string; warehouse_name: string | null } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

const label = (w: WarehouseOption) =>
  w.warehouse_name ? `${w.warehouse_code} - ${w.warehouse_name}` : w.warehouse_code;

/**
 * Thin domain wrapper over the standard SearchableSelect: it owns the warehouse label
 * format and the saved-value fallback so its call sites don't each re-derive them.
 */
export function WarehouseCombobox({
  value,
  onChange,
  warehouses = [],
  warehouseFallback,
  placeholder = 'Select warehouse',
  disabled,
  className,
}: WarehouseComboboxProps) {
  const options = [
    ...warehouses,
    // The saved warehouse may be inactive/absent from the list; keep it selectable so
    // editing an existing row cannot silently blank it.
    ...(warehouseFallback && value && !warehouses.some((w) => w.id === warehouseFallback.id)
      ? [warehouseFallback]
      : []),
  ];

  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No warehouse found."
      triggerClassName={className}
      options={options.map((w) => ({
        value: w.id,
        label: label(w),
        searchText: `${w.warehouse_code} ${w.warehouse_name ?? ''}`,
      }))}
    />
  );
}
