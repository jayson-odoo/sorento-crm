'use client';

import { useCallback, useState } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Button } from '@/components/ui/button';
import { joinMulti, multiChipLabel, splitMulti } from '@/lib/list-filters/multiValue';
import { useContactAccessTypes } from '../../contact-access-types/hooks/useContactAccessTypes';
import { searchCustomersSelect } from '@/app/(protected)/order-management/customers/services/customerService';
import { getContact, getContacts } from '../[id]/services/contactService';
import { customerFilterLabel, customerFilterLabelKey } from '../lib/customerFilterLabel';
import { PACKING_LIST_REGION_OPTIONS } from '@/lib/packing-list-regions';
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

/**
 * FILTER-MULTISELECT: the names of the customers a Customer filter holds, one per id, never an id.
 * Each id reads through the shared label key, so the options the picker fetched (cached below) and the
 * toolbar chip answer from the same entries, and an id restored from the URL is read back once.
 */
export function useCustomerFilterNames(customerIds: string[]): string[] {
  const results = useQueries({
    queries: customerIds.map((id) => ({
      queryKey: customerFilterLabelKey(id),
      queryFn: () => customerFilterLabel(id),
      staleTime: Infinity,
      retry: 0,
    })),
  });
  return customerIds.map((_, i) => results[i]?.data ?? 'Selected customer');
}

/** A multi-select trigger that names itself like its single siblings: "Tier: Dealer, Office". */
function multiTrigger(title: string, chosen: { label: string }[]) {
  return chosen.length ? (
    <span className="block truncate" title={chosen.map((o) => o.label).join(', ')}>
      {multiChipLabel(title, chosen.map((o) => o.label))}
    </span>
  ) : (
    <span className="text-muted-foreground">{title}: any</span>
  );
}

interface Props {
  value: Filters;
  onChange: (next: Filters) => void;
  /** The Filters popover owns Clear filters for all of its controls. */
  hideClear?: boolean;
}

export default function ContactAccessFilters({ value, onChange, hideClear = false }: Props) {
  const { data: accessTypes = [] } = useContactAccessTypes();
  const queryClient = useQueryClient();
  const [differsOption, setDiffersOption] = useState<SearchableSelectOption | undefined>();

  const set = (field: keyof Filters) => (v: string) => onChange({ ...value, [field]: v || null });

  const setMulti = (field: keyof Filters) => (ids: string[]) =>
    onChange({ ...value, [field]: joinMulti(ids) || null });
  const customerIds = splitMulti(value.customerId);
  const customerNames = useCustomerFilterNames(customerIds);
  const differsLabel = useQuery({
    queryKey: ['contact-filter-differs-label', value.accessDiffersFrom],
    queryFn: async () => contactLabel(await getContact(value.accessDiffersFrom as string)),
    enabled: !!value.accessDiffersFrom && differsOption?.value !== value.accessDiffersFrom,
    staleTime: Infinity,
    retry: 0,
  });

  const fetchCustomers = useCallback(
    async (query: string) => {
      // Every granted company, each option tagged with its company (codes repeat across them).
      const options = (await searchCustomersSelect(query, 0, { companyScope: 'grants' })).map((o) => ({
        value: o.value,
        label: o.label,
      }));
      // Remember the names of what was offered, so a pick is named at once (chip and trigger).
      for (const o of options) queryClient.setQueryData(customerFilterLabelKey(o.value), o.label);
      return options;
    },
    [queryClient],
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
    read: { data?: string },
    fallback: string,
  ): SearchableSelectOption | undefined => {
    if (!id) return undefined;
    if (option?.value === id) return option;
    // Until the read-back answers (or if it cannot), a neutral name stands in: never the id.
    return { value: id, label: read.data ?? fallback };
  };

  const active = Object.values(value).some(Boolean);
  const cls = 'w-full';

  return (
    // Phones: a one-column grid (`minmax(0,1fr)`), so a long chosen label truncates instead of
    // widening the toolbar past the screen; from `sm` up the fixed-width triggers wrap in a row.
    <div
      className="grid w-full min-w-0 grid-cols-1 gap-2"
      data-testid="contact-access-filters"
    >
      <SearchableMultiSelect
        triggerClassName={cls}
        value={splitMulti(value.accessType)}
        onChange={setMulti('accessType')}
        options={accessTypes.map((t) => ({ value: t.code, label: t.name }))}
        placeholder="Access type: any"
        renderTriggerLabel={(chosen) => multiTrigger('Access type', chosen)}
        clearable
      />
      <SearchableMultiSelect
        triggerClassName={cls}
        value={splitMulti(value.tier)}
        onChange={setMulti('tier')}
        options={TIER_OPTIONS}
        placeholder="Tier: any"
        renderTriggerLabel={(chosen) => multiTrigger('Tier', chosen)}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.cost ?? ''}
        onChange={set('cost')}
        options={YES_NO('Cost visible', 'Cost hidden')}
        placeholder="Cost: any"
        renderTriggerLabel={(opt) => `Cost: ${opt.label}`}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.ai ?? ''}
        onChange={set('ai')}
        options={YES_NO('AI replies allowed', 'AI replies blocked')}
        placeholder="AI replies: any"
        renderTriggerLabel={(opt) => `AI replies: ${opt.label}`}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.escalation ?? ''}
        onChange={set('escalation')}
        options={YES_NO('Escalation allowed', 'Escalation blocked')}
        placeholder="Escalation: any"
        renderTriggerLabel={(opt) => `Escalation: ${opt.label}`}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.packingList ?? ''}
        onChange={set('packingList')}
        options={YES_NO('Packing list allowed', 'Packing list not allowed')}
        placeholder="Packing list: any"
        renderTriggerLabel={(opt) => `Packing list: ${opt.label}`}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.stock ?? ''}
        onChange={set('stock')}
        options={YES_NO('Stock checks allowed', 'Stock checks blocked')}
        placeholder="Stock checks: any"
        renderTriggerLabel={(opt) => `Stock checks: ${opt.label}`}
        clearable
      />
      <SearchableSelect
        triggerClassName={cls}
        truncateTriggerLabel
        value={value.region ?? ''}
        onChange={set('region')}
        options={PACKING_LIST_REGION_OPTIONS}
        placeholder="Region: any"
        renderTriggerLabel={(opt) => `Region: ${opt.label}`}
        clearable
      />
      <SearchableMultiSelect
        triggerClassName="w-full"
        value={customerIds}
        onChange={setMulti('customerId')}
        selectedOptions={customerIds.map((id, i) => ({ value: id, label: customerNames[i] }))}
        fetchOptions={fetchCustomers}
        placeholder="Customer: any"
        renderTriggerLabel={(chosen) => multiTrigger('Customer', chosen)}
        emptyMessage="No customers match."
        clearable
      />
      <SearchableSelect
        triggerClassName="w-full"
        truncateTriggerLabel
        value={value.accessDiffersFrom ?? ''}
        onChange={set('accessDiffersFrom')}
        onOptionChange={(opt) => setDiffersOption(opt ?? undefined)}
        selectedOption={selected(value.accessDiffersFrom, differsOption, differsLabel, 'Selected contact')}
        fetchOptions={fetchContacts}
        placeholder="Access differs from: any"
        renderTriggerLabel={(opt) => `Access differs from: ${opt.label}`}
        emptyMessage="No contacts match."
        clearable
      />
      {active && !hideClear ? (
        <Button variant="ghost" size="sm" onClick={() => onChange({})}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}
