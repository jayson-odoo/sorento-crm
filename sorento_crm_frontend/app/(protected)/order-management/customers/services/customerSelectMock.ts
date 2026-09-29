/**
 * PHASE 1 MOCK (PLAN-contact-customers-29sep, S1). Deleted in S2 together with the `USE_MOCK`
 * switches in `customerService.ts`, `contactCustomersService.ts` and `salesAgentService.ts`.
 *
 * One in-memory customer book shared by the contact card and the sales agent tab, so a
 * customer assigned on one surface reads the same on the other while both run on mocks.
 */

export interface MockCustomer {
  id: string;
  customer_code: string;
  customer_name: string;
  phone_number: string | null;
  is_active: boolean;
  region: string | null;
  market_segment_code: string | null;
  sales_agent_id: string | null;
  sales_agent_code: string | null;
  sales_agent_name: string | null;
}

export const MOCK_AGENTS = [
  { id: 'mock-agent-1', code: 'AGT-01', name: 'Lim Wei Jie' },
  { id: 'mock-agent-2', code: 'AGT-02', name: 'Siti Aminah' },
] as const;

function agentFields(index: number | null) {
  if (index === null) {
    return { sales_agent_id: null, sales_agent_code: null, sales_agent_name: null };
  }
  const agent = MOCK_AGENTS[index];
  return {
    sales_agent_id: agent.id,
    sales_agent_code: agent.code,
    sales_agent_name: agent.name,
  };
}

export const mockCustomers: MockCustomer[] = [
  ['300-H001', 'Hanlim Trading Sdn Bhd', '0123456701', 'Klang Valley', 'retail', 0],
  ['300-H002', 'Hanlim Trading (Penang)', '0123456702', 'Northern', 'retail', 0],
  ['300-H003', 'Hanlim Builders Sdn Bhd', '0123456703', 'Johor', 'project', 1],
  ['300-K010', 'Kenanga Hardware', '0123456710', 'Klang Valley', 'retail', 1],
  ['300-M020', 'Maju Jaya Enterprise', '0123456720', 'Northern', 'retail', null],
  ['300-S030', 'Seri Utama Contractors', '0123456730', 'East Coast', 'project', 0],
  ['300-T040', 'Tiong Bahru Timber', null, 'Johor', 'retail', null],
  ['300-Z050', 'Zenith Interiors (closed)', '0123456750', null, null, 1],
].map(([code, name, phone, region, segment, agent], i) => ({
  id: `mock-customer-${i + 1}`,
  customer_code: code as string,
  customer_name: name as string,
  phone_number: phone as string | null,
  is_active: code !== '300-Z050',
  region: region as string | null,
  market_segment_code: segment as string | null,
  ...agentFields(agent as number | null),
}));

export function findMockCustomer(id: string): MockCustomer | undefined {
  return mockCustomers.find((c) => c.id === id);
}

export function assignMockCustomer(customerId: string, agentId: string | null): MockCustomer {
  const customer = findMockCustomer(customerId);
  if (!customer) throw new Error('Customer not found');
  const index = agentId ? MOCK_AGENTS.findIndex((a) => a.id === agentId) : -1;
  Object.assign(customer, agentFields(index >= 0 ? index : null));
  return customer;
}

/** The server-side search the real select does: code or name, `limit` rows from `offset`. */
export function searchMockCustomers(query: string, limit: number, offset: number): MockCustomer[] {
  const q = query.trim().toLowerCase();
  const hits = q
    ? mockCustomers.filter(
        (c) =>
          c.customer_code.toLowerCase().includes(q) || c.customer_name.toLowerCase().includes(q),
      )
    : mockCustomers;
  return hits.slice(offset, offset + limit);
}
