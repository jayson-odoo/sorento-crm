'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';

interface PackingListOption {
  id: string;
  shipment_number: string | null;
  shipping_container_number?: string | null;
}

interface PackingListComboboxProps {
  value: string;
  onChange: (value: string) => void;
  packingLists: PackingListOption[];
  packingListFallback?: {
    id: string;
    shipment_number: string | null;
    shipping_container_number?: string | null;
  } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

const label = (pl: PackingListOption) =>
  pl.shipping_container_number ?? pl.shipment_number ?? pl.id;

/** Thin domain wrapper over the standard SearchableSelect (label format + saved-value fallback). */
export function PackingListCombobox({
  value,
  onChange,
  packingLists = [],
  packingListFallback,
  placeholder = 'Select packing list',
  disabled,
  className,
}: PackingListComboboxProps) {
  const options = [
    ...packingLists,
    ...(packingListFallback &&
    value &&
    !packingLists.some((pl) => pl.id === packingListFallback.id)
      ? [packingListFallback]
      : []),
  ];

  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No packing list found."
      triggerClassName={className}
      options={options.map((pl) => ({
        value: pl.id,
        label: label(pl),
        searchText: `${pl.shipment_number ?? ''} ${pl.shipping_container_number ?? ''}`,
      }))}
    />
  );
}
