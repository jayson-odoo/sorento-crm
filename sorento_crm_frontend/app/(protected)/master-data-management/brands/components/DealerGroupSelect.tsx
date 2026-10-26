'use client';

import { useState } from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getCompaniesSelect, getMyCompanyContext } from '@/app/(protected)/system-management/companies/services/companyService';

async function fetchCompanyOptions(query: string) {
  try {
    const needle = query.trim().toLowerCase();
    let companies: { id: string; name: string; code: string }[];
    try {
      companies = await getCompaniesSelect();
    } catch {
      // The full list is superadmin-only; anyone else picks from the companies the header switcher offers.
      companies = (await getMyCompanyContext()).companies;
    }
    return companies
      .filter((c) => !needle || `${c.name} ${c.code}`.toLowerCase().includes(needle))
      .map((c) => ({ value: c.id, label: c.name, description: c.code }));
  } catch {
    // Neither source answered; the stored company is still shown by name.
    return [];
  }
}

/**
 * The company whose dealers get a brand from the access-sheet upload (BULK-CONTACT-ACCESS U21).
 * Clearable; `onChange` gets null when cleared, never an empty string. `storedName` labels the
 * stored value, so a caller who cannot list companies still reads it.
 */
export function DealerGroupSelect({
  value,
  storedName,
  onChange,
}: {
  value: string | null;
  storedName?: string | null;
  onChange: (id: string | null) => void;
}) {
  const [picked, setPicked] = useState<{ value: string; label: string } | null>(null);
  const selectedOption = !value
    ? undefined
    : picked?.value === value
      ? picked
      : storedName
        ? { value, label: storedName }
        : undefined;
  return (
    <SearchableSelect
      value={value ?? ''}
      onChange={(next) => onChange(next || null)}
      onOptionChange={(option) => setPicked(option ? { value: option.value, label: option.label } : null)}
      fetchOptions={fetchCompanyOptions}
      selectedOption={selectedOption}
      placeholder="No dealer group"
      aria-label="Dealer group"
      clearable
    />
  );
}
