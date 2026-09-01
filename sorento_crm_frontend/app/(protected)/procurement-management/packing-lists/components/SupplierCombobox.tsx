'use client';

import { useMemo } from 'react';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import { searchSuppliersForSelect } from '../../suppliers/services/supplierService';

interface SupplierOption {
  id: string;
  supplier_code: string;
  supplier_name: string;
}

interface SupplierComboboxProps {
  value: string;
  onChange: (value: string) => void;
  /**
   * Suppliers the page already holds. NOT the searchable list any more - only what resolves
   * an already-chosen value to a name without a round trip (a packing list's lines each name
   * their own factory, and every one of them has to read as a name straight away).
   */
  suppliers?: SupplierOption[];
  supplierFallback?: { id: string; supplier_code: string; supplier_name: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** One-line ellipsis trigger for fixed-width table cells. */
  truncateTriggerLabel?: boolean;
  /** Every optional select is clearable (ADR standard) - off by default so a REQUIRED
   *  supplier picker (every existing packing-list caller) does not grow a clear
   *  affordance it has no use for. */
  clearable?: boolean;
}

const asOption = (s: SupplierOption) => ({
  value: s.id,
  label: s.supplier_name,
  searchText: `${s.supplier_code} ${s.supplier_name}`,
});

/**
 * The factory picker on every packing-list screen: server-searched, labelled by NAME.
 *
 * SEARCHED ON THE SERVER (`searchSuppliersForSelect`). It used to be handed the one page
 * `/select` returns without a query - 100 rows of 194 - and filtered it in the browser, so
 * typing JINBAICHUAN on a new packing list answered "No supplier found." while the same
 * endpoint returned it the moment the query was passed through. Any master this big is
 * server-searched; a capped page filtered client-side is a picker that hides records.
 *
 * The label is the factory's NAME and nothing else (R18): the code is ours, the name is what
 * the operator calls the factory, and "(400-K029)" after every entry is noise on a list that
 * is read by name. `searchText` keeps the code, so typing a code still finds the supplier.
 */
export function SupplierCombobox({
  value,
  onChange,
  suppliers = [],
  supplierFallback,
  placeholder = 'Select supplier',
  disabled,
  className,
  truncateTriggerLabel,
  clearable = false,
}: SupplierComboboxProps) {
  // What the trigger shows for a value that is already set. The server list only holds what
  // the last search returned, so without this a saved supplier reads as an empty box until
  // somebody opens the picker and finds it again.
  const selectedOption = useMemo(() => {
    if (!value) return undefined;
    const known = [...suppliers, ...(supplierFallback ? [supplierFallback] : [])];
    const match = known.find((s) => s.id === value);
    return match ? asOption(match) : undefined;
  }, [value, suppliers, supplierFallback]);

  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      clearable={clearable}
      emptyMessage="No supplier found."
      triggerClassName={className}
      truncateTriggerLabel={truncateTriggerLabel}
      fetchOptions={(query) => searchSuppliersForSelect(query)}
      selectedOption={selectedOption}
    />
  );
}
