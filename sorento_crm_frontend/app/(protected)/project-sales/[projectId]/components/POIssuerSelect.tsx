'use client';

import * as React from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useProjectParties } from '../../_shared/hooks/useProjects';

/**
 * "Issued by" on a purchase order: the searchable, clearable party select. One component for
 * the PO header card and the PO intake confirm screen, so both offer the same parties.
 */
export function POIssuerSelect({
  id,
  value,
  onChange,
  disabled,
}: {
  id: string;
  value: string | null | undefined;
  onChange: (partyId: string | null) => void;
  disabled?: boolean;
}) {
  const parties = useProjectParties({ limit: 200 });
  return (
    <SearchableSelect
      id={id}
      value={value ?? ''}
      onChange={(next) => onChange(next || null)}
      clearable
      disabled={disabled}
      loadError={parties.error}
      onRetry={() => void parties.refetch()}
      options={(parties.data?.data ?? []).map((party) => ({
        value: party.id,
        label: party.name,
        description: party.party_type.replace(/_/g, ' '),
      }))}
      placeholder="-"
      emptyMessage="No parties on file"
    />
  );
}
