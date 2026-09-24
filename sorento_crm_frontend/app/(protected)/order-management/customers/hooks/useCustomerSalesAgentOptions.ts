import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCustomerSalesAgentsSelect } from '../services/customerService';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * Every sales agent as a `SearchableSelect` option, for the "Sales agent" field on the
 * customer form. `value` is the id - never shown, only used to address the write. `label`
 * is `code - name`, since a code alone means nothing to anyone who has not memorised the
 * mapping.
 */
export function useCustomerSalesAgentOptions() {
  const query = useQuery({
    queryKey: ['customer-sales-agents-select'],
    queryFn: getCustomerSalesAgentsSelect,
    staleTime: 5 * 60 * 1000,
  });

  // The server already orders by code (`sales_agent_service.list_active`); re-sorting here
  // would only be needed if a caller could not trust that.
  const options = useMemo<SearchableSelectOption[]>(
    () =>
      (query.data ?? []).map((a) => ({
        value: a.id,
        label: a.person_label ? `${a.sales_agent} - ${a.person_label}` : a.sales_agent,
        code: a.sales_agent,
      })),
    [query.data],
  );

  return { ...query, options };
}
