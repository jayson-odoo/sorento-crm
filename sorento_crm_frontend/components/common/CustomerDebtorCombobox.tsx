'use client';

import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import type { DebtorLookupItem } from '@/app/(auth)/portal/lib/portal-client';

/**
 * The customer dropdown of the stock inquiry form, shared with the new product application so the
 * two cannot drift: company customers by name or code, with typed free text allowed unless
 * `pickOnly`. `lookup` is the form's own search (`client.lookupDebtors(q, 20, kind)`).
 */
export function CustomerDebtorCombobox({
  id,
  ariaLabel,
  value,
  onChange,
  lookup,
  pickOnly,
  placeholder,
  disabled,
}: {
  id?: string;
  ariaLabel?: string;
  value: string;
  /** The text now in the box, and the picked customer (undefined when the text was typed). */
  onChange: (value: string, item?: DebtorLookupItem) => void;
  lookup: (q: string) => Promise<DebtorLookupItem[]>;
  pickOnly?: boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div data-testid="customer-debtor-combobox">
      <AsyncCombobox<DebtorLookupItem>
        id={id}
        ariaLabel={ariaLabel}
        value={value}
        onChange={onChange}
        fetchOptions={lookup}
        allowFreeText={!pickOnly}
        optionValue={(o) => o.debtor_name}
        optionLabel={(o) => o.debtor_name}
        optionMeta={(o) => o.customer_code}
        placeholder={placeholder ?? 'Search debtors...'}
        disabled={disabled}
      />
    </div>
  );
}
