'use client';

/**
 * The customers a price tag request prints for (PRICETAG-REQUEST-LAYOUT, owner 10 Nov): one
 * request, several customers, picked as removable chips over the debtor lookup the single
 * select used to read. A customer no longer in that lookup (an older request) keeps its chip.
 */
import { useMemo } from 'react';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import type {
  DebtorOption,
  RequestCustomer,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import { customerKey } from '@/lib/dealer-kit/request-customers';

interface Props {
  id?: string;
  value: RequestCustomer[];
  options: DebtorOption[];
  onChange: (customers: RequestCustomer[]) => void;
  disabled?: boolean;
}

export function RequestCustomersSelect({ id, value, options, onChange, disabled }: Props) {
  // A picked customer the lookup no longer lists stays an option, so its chip keeps its name.
  const choices = useMemo<SearchableMultiSelectOption[]>(() => {
    const listed = options.map((d) => ({ value: d.code, label: d.name, description: d.code }));
    const codes = new Set(options.map((d) => d.code));
    const unlisted = value
      .filter((c) => !codes.has(customerKey(c)))
      .map((c) => ({ value: customerKey(c), label: c.name, description: c.code ?? undefined }));
    return [...listed, ...unlisted];
  }, [options, value]);
  return (
    <SearchableMultiSelect
      id={id}
      value={value.map(customerKey)}
      options={choices}
      disabled={disabled}
      placeholder="Search customers..."
      wrapOptions
      onChange={(keys) => {
        const known = new Map<string, RequestCustomer>();
        for (const c of value) known.set(customerKey(c), c);
        for (const d of options) known.set(d.code, { code: d.code, name: d.name });
        onChange(keys.flatMap((key) => (known.has(key) ? [known.get(key)!] : [])));
      }}
    />
  );
}
