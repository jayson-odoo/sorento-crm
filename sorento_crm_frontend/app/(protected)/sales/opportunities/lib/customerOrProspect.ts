/**
 * The "Customer or prospect" field's shared shape (UAC S2-15) - one search box that offers
 * a matching customer, an "Add ... as a new prospect" option when nothing matches, or a
 * disabled, explained option when the exact name belongs to another agent's customer.
 * Shared by `SalesOpportunityModal` (create) and `SalesOpportunityDetail` (edit in place,
 * Phase 3 fix B2), so the two never carry two copies of this rule.
 */
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { getSalesOpportunityCustomerOptions } from '../services/salesOpportunityService';

export const PROSPECT_PREFIX = 'prospect:';
export const BLOCKED_VALUE = '__blocked__';

export async function fetchCustomerOrProspectOptions(query: string): Promise<SearchableSelectOption[]> {
  const result = await getSalesOpportunityCustomerOptions(query);
  const options: SearchableSelectOption[] = result.items.map((item) => ({
    value: item.customer_id,
    label: `${item.customer_code} - ${item.customer_name}`,
  }));
  if (result.blocked) {
    options.push({ value: BLOCKED_VALUE, label: result.blocked.message, disabled: true });
  } else if (result.prospect) {
    options.push({
      value: `${PROSPECT_PREFIX}${result.prospect.name}`,
      label: `Add "${result.prospect.name}" as a new prospect`,
    });
  }
  return options;
}
