/**
 * Contact -> customers links - feature service.
 *
 * Layering: ContactCustomersSection -> hooks (useContactCustomers) -> THIS service -> lib/api.
 *
 * Backend contract (PLAN-contact-customers-29sep D2), read `user_management.contacts.view`,
 * write `user_management.contacts.edit`:
 *   GET   /api/v1/user-management/contacts/{contact_id}/customers
 *           -> { data: ContactCustomerLink[], suggested: SuggestedCustomer[] }
 *           `data` ordered by created_at; `suggested` at most 5 phone-matched, unlinked.
 *   POST  /api/v1/user-management/contacts/{contact_id}/customers
 *           body { customer_id, is_primary?: false } -> 201 ContactCustomerLink
 *           Idempotent on the pair. Unknown or out-of-scope customer, unknown contact: 404.
 *   PATCH /api/v1/user-management/contacts/{contact_id}/customers/{customer_id}
 *           body { is_primary } -> 200 ContactCustomerLink. true demotes the other primary in
 *           that company, false clears. Unlinked pair: 404.
 *   Unlink has NO route: it is the pending action `contact_customer_link.unlink`, entity type
 *   `contact_customer_link`, entity id = the LINK id (`ContactCustomerLink.id`), reversible
 *   window, permission `user_management.contacts.edit`. Parked by `useDeferredRowAction`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface ContactCustomerLink {
  /** The link row id. Never rendered; it is the unlink action's entity id. */
  id: string;
  customer_id: string;
  customer_code: string;
  customer_name: string;
  is_active: boolean;
  is_primary: boolean;
  source: string;
  sales_agent_id: string | null;
  sales_agent_code: string | null;
  sales_agent_name: string | null;
  created_at: string;
}

export interface SuggestedCustomer {
  customer_id: string;
  customer_code: string;
  customer_name: string;
  phone_number: string | null;
  sales_agent_code: string | null;
  sales_agent_name: string | null;
}

export interface ContactCustomers {
  data: ContactCustomerLink[];
  suggested: SuggestedCustomer[];
}

const base = (contactId: string) => `/api/v1/user-management/contacts/${contactId}/customers`;

// ---- service -----------------------------------------------------------------------------

export async function getContactCustomers(contactId: string): Promise<ContactCustomers> {
  const response = await apiFetch(base(contactId));
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load customers'));
  }
  const body: Partial<ContactCustomers> = await response.json();
  return { data: body.data ?? [], suggested: body.suggested ?? [] };
}

export async function linkContactCustomer(
  contactId: string,
  customerId: string,
  isPrimary = false,
): Promise<ContactCustomerLink> {
  const response = await apiFetch(base(contactId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId, is_primary: isPrimary }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to link customer'));
  }
  return response.json();
}

export async function setContactCustomerPrimary(
  contactId: string,
  customerId: string,
  isPrimary: boolean,
): Promise<ContactCustomerLink> {
  const response = await apiFetch(`${base(contactId)}/${customerId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_primary: isPrimary }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update primary customer'));
  }
  return response.json();
}
