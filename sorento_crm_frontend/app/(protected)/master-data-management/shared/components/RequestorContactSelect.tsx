'use client';

import { useMemo } from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getRequestorSelectOptions } from '../services/requestorSelectService';

interface RequestorContactSelectProps {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  /** The row's submitting contact id - always eligible, per D6. */
  submitterContactId?: string | null;
  /** The currently-saved requestor id on the row (may have lost eligibility since). */
  savedContactId?: string | null;
  /** Name for the saved requestor so it renders even when not in a fetched page. */
  savedContactName?: string | null;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Contact picker for "Requested by" (purchase request / sponsorship form) and
 * "Salesperson" (stock inquiry). Async against the segment-gated requestor-select
 * endpoint; the submitter and the saved requestor are always selectable even when
 * outside the gated segment set. Names only - no UUIDs ever render.
 * See docs/plans/PLAN-requested-by-contact-routing.md §6.
 */
export function RequestorContactSelect({
  value,
  onChange,
  submitterContactId,
  savedContactId,
  savedContactName,
  placeholder = 'Select requestor',
  disabled,
}: RequestorContactSelectProps) {
  const selectedOption = useMemo(() => {
    if (!savedContactId) return undefined;
    return { value: savedContactId, label: savedContactName?.trim() || 'Selected contact' };
  }, [savedContactId, savedContactName]);

  return (
    <SearchableSelect
      value={value ?? ''}
      onChange={(v) => onChange(v || null)}
      fetchOptions={async (q) => {
        const res = await getRequestorSelectOptions({
          q,
          includeIds: [submitterContactId, savedContactId],
        });
        return res.items.map((i) => ({ value: i.id, label: i.name }));
      }}
      selectedOption={selectedOption}
      clearable
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No eligible requestors found."
    />
  );
}
