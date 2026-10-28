'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
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
  /**
   * Where the eligible set comes from. Defaults to the staff requestor-select endpoint; a
   * salesperson writing their own request reads the portal's set through My Requests.
   */
  loadOptions?: (q: string) => Promise<{ id: string; name: string }[]>;
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
  loadOptions,
}: RequestorContactSelectProps) {
  // A preselected value with no saved name (a limited user's own contact on a new form) is named
  // from the option list on load, so the combobox never shows the placeholder for it.
  const needsName = Boolean(loadOptions && value && !savedContactId);
  const loadRef = useRef(loadOptions);
  loadRef.current = loadOptions;
  const [preselected, setPreselected] = useState<{ id: string; name: string } | null>(null);
  useEffect(() => {
    if (!needsName || !value) return;
    let live = true;
    loadRef.current?.('')
      .then((items) => {
        const hit = items.find((i) => i.id === value);
        if (live && hit) setPreselected(hit);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [needsName, value]);
  const selectedOption = useMemo(() => {
    if (savedContactId) {
      return { value: savedContactId, label: savedContactName?.trim() || 'Selected contact' };
    }
    if (needsName && value && preselected?.id === value) return { value, label: preselected.name };
    return undefined;
  }, [savedContactId, savedContactName, needsName, value, preselected]);

  return (
    <SearchableSelect
      value={value ?? ''}
      onChange={(v) => onChange(v || null)}
      fetchOptions={async (q) => {
        const items = loadOptions
          ? await loadOptions(q)
          : (
              await getRequestorSelectOptions({
                q,
                includeIds: [submitterContactId, savedContactId],
              })
            ).items;
        return items.map((i) => ({ value: i.id, label: i.name }));
      }}
      selectedOption={selectedOption}
      clearable
      disabled={disabled}
      placeholder={placeholder}
      emptyMessage="No eligible requestors found."
    />
  );
}
