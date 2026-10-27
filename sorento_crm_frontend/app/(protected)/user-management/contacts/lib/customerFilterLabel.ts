import { searchCustomersSelect } from '@/app/(protected)/order-management/customers/services/customerService';

/** Query key shared by the Customer filter and its toolbar chip, so they read the label once. */
export const customerFilterLabelKey = (customerId: string | null | undefined) =>
  ['contact-filter-customer-label', customerId] as const;

/**
 * The label of a Customer filter restored from the URL. The contacts list is company-less, so the
 * customer may sit in another granted company: read it through the grants search, which tags it with
 * its company ("Mocha · 300-1001 - NAME"), not the company-scoped single-customer GET.
 */
export async function customerFilterLabel(customerId: string): Promise<string> {
  const [c] = await searchCustomersSelect('', 0, { companyScope: 'grants', customerId });
  if (!c) throw new Error('Customer not found');
  return c.label;
}
