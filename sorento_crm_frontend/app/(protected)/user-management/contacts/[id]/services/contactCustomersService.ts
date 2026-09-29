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
 *
 * CONTRACT ADDITION vs plan D2: `ContactCustomerLink` carries `id` (the link row id). The
 * unlink action addresses the link row and the UI holds nothing else it could use, so the
 * GET/POST/PATCH bodies must return it. The plan's field list omits it; S2 adds it.
 *
 * PHASE 1: `USE_MOCK` serves an in-memory store. Phase 2 flips it to false, deletes the mock
 * branch and `customerSelectMock.ts`. The unlink countdown always talks to the real
 * `/pending-actions` route, so on mocks it is refused until the action is registered in S2.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  findMockCustomer,
  mockCustomers,
} from '@/app/(protected)/order-management/customers/services/customerSelectMock';

const USE_MOCK = true;

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

// ---- mock store (deleted in S2) ----------------------------------------------------------

const mockLinks = new Map<string, ContactCustomerLink[]>();
const MOCK_SUGGEST_IDS = ['mock-customer-3', 'mock-customer-4'];

function toLink(customerId: string, isPrimary: boolean): ContactCustomerLink {
  const c = findMockCustomer(customerId);
  if (!c) throw new Error('Customer not found');
  return {
    id: `mock-link-${customerId}`,
    customer_id: c.id,
    customer_code: c.customer_code,
    customer_name: c.customer_name,
    is_active: c.is_active,
    is_primary: isPrimary,
    source: 'manual',
    sales_agent_id: c.sales_agent_id,
    sales_agent_code: c.sales_agent_code,
    sales_agent_name: c.sales_agent_name,
    created_at: new Date().toISOString(),
  };
}

function mockLinksFor(contactId: string): ContactCustomerLink[] {
  let links = mockLinks.get(contactId);
  if (!links) {
    links = [toLink('mock-customer-1', true), toLink('mock-customer-2', false)];
    mockLinks.set(contactId, links);
  }
  return links;
}

function mockGet(contactId: string): ContactCustomers {
  const links = mockLinksFor(contactId);
  const linked = new Set(links.map((l) => l.customer_id));
  // Refresh the agent columns: an agent assigned on the other surface shows here too.
  const fresh = links.map((l) => ({ ...toLink(l.customer_id, l.is_primary), id: l.id }));
  return {
    data: fresh,
    suggested: mockCustomers
      .filter((c) => MOCK_SUGGEST_IDS.includes(c.id) && !linked.has(c.id))
      .map((c) => ({
        customer_id: c.id,
        customer_code: c.customer_code,
        customer_name: c.customer_name,
        phone_number: c.phone_number,
        sales_agent_code: c.sales_agent_code,
        sales_agent_name: c.sales_agent_name,
      })),
  };
}

function setMockPrimary(links: ContactCustomerLink[], customerId: string, isPrimary: boolean) {
  for (const l of links) {
    if (l.customer_id === customerId) l.is_primary = isPrimary;
    else if (isPrimary) l.is_primary = false;
  }
}

// ---- service -----------------------------------------------------------------------------

export async function getContactCustomers(contactId: string): Promise<ContactCustomers> {
  if (USE_MOCK) return mockGet(contactId);
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
  if (USE_MOCK) {
    const links = mockLinksFor(contactId);
    let link = links.find((l) => l.customer_id === customerId);
    if (!link) {
      link = toLink(customerId, false);
      links.push(link);
    }
    if (isPrimary) setMockPrimary(links, customerId, true);
    return link;
  }
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
  if (USE_MOCK) {
    const links = mockLinksFor(contactId);
    const link = links.find((l) => l.customer_id === customerId);
    if (!link) throw new Error('Customer is not linked to this contact');
    setMockPrimary(links, customerId, isPrimary);
    return link;
  }
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
