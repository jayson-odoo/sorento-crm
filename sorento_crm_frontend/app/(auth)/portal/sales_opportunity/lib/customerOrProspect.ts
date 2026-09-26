/**
 * The portal's "Customer or prospect" field (UAC S2-15) - shared by
 * `SalesOpportunityPortalForm` (create) and `SalesOpportunityPortalDetail` (edit in place,
 * Phase 3 fix2 should-fix 5), so the two never carry two copies of this rule. Mirrors the CRM's
 * own `app/(protected)/sales/opportunities/lib/customerOrProspect.ts` over the portal's own
 * `AsyncCombobox` and customer-options service.
 */
import {
  getPortalCustomerOptions,
  type PortalCustomerOptionItem,
} from '../../lib/sales-opportunity-service';

export const PROSPECT_PREFIX = 'prospect:';
export const BLOCKED_ID = '__blocked__';

export interface CustomerComboOption {
  id: string;
  label: string;
  disabled?: boolean;
  customerId?: string;
  prospectName?: string;
}

export async function fetchCustomerOrProspectOptions(q: string): Promise<CustomerComboOption[]> {
  const result = await getPortalCustomerOptions(q);
  const options: CustomerComboOption[] = result.items.map((item: PortalCustomerOptionItem) => ({
    id: item.customer_id,
    label: `${item.customer_code} - ${item.customer_name}`,
    customerId: item.customer_id,
  }));
  if (result.blocked) {
    options.push({ id: BLOCKED_ID, label: result.blocked.message, disabled: true });
  } else if (result.prospect) {
    options.push({
      id: `${PROSPECT_PREFIX}${result.prospect.name}`,
      label: `Add "${result.prospect.name}" as a new prospect`,
      prospectName: result.prospect.name,
    });
  }
  return options;
}
