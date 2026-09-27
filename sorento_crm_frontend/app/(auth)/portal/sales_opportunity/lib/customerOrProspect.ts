/**
 * The portal's "Customer or prospect" field (UAC S2-15) - shared by
 * `SalesOpportunityPortalForm` (create) and `SalesOpportunityPortalDetail` (edit in place,
 * Phase 3 fix2 should-fix 5), so the two never carry two copies of this rule. Mirrors the CRM's
 * own `app/(protected)/sales/opportunities/lib/customerOrProspect.ts`, over the system
 * `SearchableSelect` in `fetchOptions` mode rather than the portal's own `AsyncCombobox`.
 */
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { getPortalCustomerOptions } from '../../lib/sales-opportunity-service';

export const PROSPECT_PREFIX = 'prospect:';
export const BLOCKED_VALUE = '__blocked__';

/**
 * F3: an empty query with zero customers means the agent has none linked - the honest thing
 * to say, not a bare "No results found." A non-empty query with zero customers always comes
 * back with a prospect (or blocked) option in the list instead, so that case never renders
 * this message at all.
 */
export const NO_CUSTOMERS_MESSAGE = 'You have no customers linked yet; type a name to add a prospect';

export async function fetchCustomerOrProspectOptions(query: string): Promise<SearchableSelectOption[]> {
  const result = await getPortalCustomerOptions(query);
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

/** The closed field's text: a picked prospect shows its name, not the "Add ..." option text. */
export function customerTriggerLabel(option: SearchableSelectOption): string {
  return option.value.startsWith(PROSPECT_PREFIX)
    ? option.value.slice(PROSPECT_PREFIX.length)
    : option.label;
}
