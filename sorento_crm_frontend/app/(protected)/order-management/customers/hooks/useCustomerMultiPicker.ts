import { useCallback, useMemo, useRef, useState } from 'react';
import type { SearchableMultiSelectOption } from '@/components/common/SearchableMultiSelect';
import { searchCustomersSelect, type CustomerSelectOption } from '../services/customerService';

/**
 * State behind a `SearchableMultiSelect` over customers, shared by the contact card's
 * "Link customers" and the sales agent tab's "Assign customers".
 *
 * `fetchOptions` returns the first page of a server search (a narrower query is how the user
 * reaches the rest). `SearchableMultiSelect.onChange` only hands back ids, so every option
 * ever fetched is remembered: a ticked customer keeps its label after a new search replaces
 * the list. `isDisabled` options are shown but cannot be ticked (already linked / already assigned).
 */
export function useCustomerMultiPicker(isDisabled: (option: CustomerSelectOption) => boolean) {
  const [selected, setSelected] = useState<string[]>([]);
  const known = useRef(new Map<string, SearchableMultiSelectOption>());
  const isDisabledRef = useRef(isDisabled);
  isDisabledRef.current = isDisabled;

  const fetchOptions = useCallback(async (query: string) => {
    const page = await searchCustomersSelect(query, 0);
    return page.map((row) => {
      const option: SearchableMultiSelectOption = {
        value: row.value,
        label: row.label,
        description: row.description,
        disabled: isDisabledRef.current(row),
      };
      known.current.set(option.value, option);
      return option;
    });
  }, []);

  const selectedOptions = useMemo(
    () =>
      selected.flatMap((id) => {
        const option = known.current.get(id);
        return option ? [option] : [];
      }),
    [selected],
  );

  const clear = useCallback(() => setSelected([]), []);

  return { selected, setSelected, selectedOptions, fetchOptions, clear };
}
