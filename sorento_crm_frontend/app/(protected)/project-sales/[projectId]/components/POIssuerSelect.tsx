'use client';

import * as React from 'react';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { listParties } from '../../_shared/services/projectService';

const PAGE_SIZE = 50;

/**
 * "Issued by" on a purchase order: a searchable, clearable party select that searches the
 * SERVER (name and code), a page at a time, so the 1,977th party is as reachable as the
 * first. One component for the PO header card and the PO intake confirm screen.
 *
 * `issuerName` is the current issuer's name as the record carries it, so the box names it
 * even when it is not on a fetched page. The parties list is asked only when a person opens
 * or searches the box, never just to find a name.
 */
export function POIssuerSelect({
  id,
  value,
  issuerName,
  onChange,
  disabled,
}: {
  id: string;
  value: string | null | undefined;
  issuerName?: string | null;
  onChange: (partyId: string | null) => void;
  disabled?: boolean;
}) {
  const fetchOptions = React.useCallback(
    async (query: string, pageIndex: number) => {
      const result = await listParties({
        query: query.trim() || undefined,
        page: pageIndex + 1,
        limit: PAGE_SIZE,
      });
      return (result.data ?? []).map((party) => ({
        value: party.id,
        label: party.name,
        description: party.party_type.replace(/_/g, ' '),
      }));
    },
    [],
  );

  const label = issuerName || 'Selected party';

  return (
    <SearchableSelect
      id={id}
      value={value ?? ''}
      onChange={(next) => onChange(next || null)}
      clearable
      disabled={disabled}
      fetchOptions={fetchOptions}
      paginated
      pageSize={PAGE_SIZE}
      selectedOption={value ? { value, label } : undefined}
      placeholder="-"
      emptyMessage="No parties match"
    />
  );
}
