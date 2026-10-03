'use client';

import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { Button } from '@/components/ui/button';
import { useContactAccessTypes } from '../../contact-access-types/hooks/useContactAccessTypes';
import {
  getCustomer,
  searchCustomersSelect,
} from '@/app/(protected)/order-management/customers/services/customerService';
import { getContact, getContacts } from '../[id]/services/contactService';
import type { ContactAccessFilters as Filters } from '../lib/listQuery';

/**
 * CONTACT-BULK-ACCESS (UAC A2.3): the contacts list's access filters. Each is a clearable
 * `SearchableSelect`; the list owns the state and carries it in the URL (`listQuery.ts`).
 *
 * The customer and "access differs from" picks store an id; after a reload only the id is
 * in the URL, so their trigger label is read back from the record (never shown as an id).
 */

const YES_NO = (yes: string, no: string): SearchableSelectOption[] => [
  { value: 'yes', label: yes },
  { value: 'no', label: no },
];

const TIER_OPTIONS: SearchableSelectOption[] = [
  { value: 'dealer', label: 'Dealer' },
  { value: 'office', label: 'Office' },
  { value: 'end_user', label: 'End user' },
  { value: 'none', label: '(no tier)' },
];

const contactLabel = (c: { name?: string | null; phone_number: string }) =>
  c.name ? `${c.name} (${c.phone_number})` : c.phone_number;

interface Props {
  value: Filters;
  onChange: (next: Filters) => void;
}

export default function ContactAccessFilters({ value, onChange }: Props) {
  const { data: accessTypes = [] } = useContactAccessTypes();
  const [customerOption, setCustomerOption] = useState<SearchableSelectOption | undefined>();
  const [differsOption, setDiffersOption] = useState<SearchableSelectOption | undefined>();

  const set = (field: keyof Filters) => (v: string) => onChange({ ...value, [field]: v || null });

  // Label read-back for an id restored from the URL.
  const customerLabel = useQuery({
    queryKey: ['contact-filter-customer-label', value.customerId],
    queryFn: async () => {
      const c = await getCustomer(value.customerId as string);
      return `${c.customer_code} - ${c.customer_name}`;
    },
    enabled: !!value.customerId && customerOption?.value !== value.customerId,
    staleTime: Infinity,
    retry: 0,
  });
  const differsLabel = useQuery({
    queryKey: ['contact-filter-differs-label', value.accessDiffersFrom],
    queryFn: async () => contactLabel(await getContact(value.accessDiffersFrom as string)),
    enabled: !!value.accessDiffersFrom && differsOption?.value !== value.accessDiffersFrom,
    staleTime: Infinity,
    retry: 0,
  });

  const fetchCustomers = useCallback(
    async (query: string) =>
      (await searchCustomersSelect(query, 0)).map((o) => ({ value: o.value, label: o.label })),
    [],
  );
  const fetchContacts = useCallback(async (query: string) => {
    const page = await getContacts(
      { pageIndex: 0, pageSize: 50, sorting: [{ id: 'name', desc: false }], searchQuery: query },
      {},
    );
    return page.data.map((c) => ({ value: c.id, label: contactLabel(c) }));
  }, []);

  const selected = (
    id: string | null | undefined,
    option: SearchableSelectOption | undefined,
    read: { data?: string; isError: boolean },
    unreadable: string,
  ): SearchableSelectOption | undefined => {
    if (!id) return undefined;
    if (option?.value === id) return option;
    return { value: id, label: read.data ?? (read.isError ? unreadable : 'Loading...') };
  };

  const active = Object.values(value).some(Boolean);
  const cls = 'w-full sm:w-44';

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="contact-access-filters">
      <SearchableSelect
        className={cls}
        value={value.accessType ?? ''}
        onChange={set('accessType')}
        options={accessTypes.map((t) => ({ value: t.code, label: t.name }))}
        placeholder="Access type: any"
        clearable
      />
      <SearchableSelect
        className={cls}
        value={value.tier ?? ''}
        onChange={set('tier')}
        options={TIER_OPTIONS}
        placeholder="Tier: any"
        clearable
      />
      <SearchableSelect
        className={cls}
        value={value.cost ?? ''}
        onChange={set('cost')}
        options={YES_NO('Cost visible', 'Cost hidden')}
        placeholder="Cost: any"
        clearable
      />
      <SearchableSelect
        className={cls}
        value={value.escalation ?? ''}
        onChange={set('escalation')}
        options={YES_NO('Escalation allowed', 'Escalation blocked')}
        placeholder="Escalation: any"
        clearable
      />
      <SearchableSelect
        className={cls}
        value={value.packingList ?? ''}
        onChange={set('packingList')}
        options={YES_NO('Packing list allowed', 'Packing list not allowed')}
        placeholder="Packing list: any"
        clearable
      />
      <SearchableSelect
        className={cls}
        value={value.stock ?? ''}
        onChange={set('stock')}
        options={YES_NO('Stock checks allowed', 'Stock checks blocked')}
        placeholder="Stock checks: any"
        clearable
      />
      <SearchableSelect
        className="w-full sm:w-56"
        value={value.customerId ?? ''}
        onChange={set('customerId')}
        onOptionChange={(opt) => setCustomerOption(opt ?? undefined)}
        selectedOption={selected(value.customerId, customerOption, customerLabel, 'Selected customer')}
        fetchOptions={fetchCustomers}
        placeholder="Customer: any"
        emptyMessage="No customers match."
        clearable
      />
      <SearchableSelect
        className="w-full sm:w-64"
        value={value.accessDiffersFrom ?? ''}
        onChange={set('accessDiffersFrom')}
        onOptionChange={(opt) => setDiffersOption(opt ?? undefined)}
        selectedOption={selected(value.accessDiffersFrom, differsOption, differsLabel, 'Selected contact')}
        fetchOptions={fetchContacts}
        placeholder="Access differs from: any"
        emptyMessage="No contacts match."
        clearable
      />
      {active ? (
        <Button variant="ghost" size="sm" onClick={() => onChange({})}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}
