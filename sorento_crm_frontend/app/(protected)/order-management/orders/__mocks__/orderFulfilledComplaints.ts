import type { FulfilledComplaint } from '../services/orderFulfilmentService';

/**
 * PHASE 1 MOCK FIXTURES — DO detail "Fulfils complaints" block.
 * Delete in Phase 2 once `useOrderFulfilledComplaints` is wired onto
 * `getOrderFulfilledComplaints`.
 *
 * Scenario picked deterministically off the orderId so navigating between DOs
 * exercises both the linked (one + many) and the empty state without a backend.
 */

const MULTI_FIXTURE: FulfilledComplaint[] = [
  { complaint_id: 'mock-cmp-0042', complaint_number: 'CMP26-0042' },
  { complaint_id: 'mock-cmp-0051', complaint_number: 'CMP26-0051' },
];

const SINGLE_FIXTURE: FulfilledComplaint[] = [
  { complaint_id: 'mock-cmp-0042', complaint_number: 'CMP26-0042' },
];

const SCENARIOS: FulfilledComplaint[][] = [
  SINGLE_FIXTURE,
  [], // empty — "This delivery order is not linked to any complaint."
  MULTI_FIXTURE,
];

/** Deterministic scenario pick so each DO shows a stable mock state. */
export function mockOrderFulfilledComplaints(orderId: string): FulfilledComplaint[] {
  const seed = orderId.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return SCENARIOS[seed % SCENARIOS.length];
}
