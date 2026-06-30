import type { FulfilmentOrder } from '../services/complaintFulfilmentService';

/**
 * PHASE 1 MOCK FIXTURES — Fulfilment Delivery Orders section.
 * Delete in Phase 2 once `useComplaintFulfilmentOrders` is wired onto
 * `getComplaintFulfilmentOrders`.
 *
 * Scenario picked deterministically off the complaintId so navigating between
 * complaints exercises every state (multi-DO incl. delivered + pending +
 * cancelled, and the empty case) without a backend.
 */

// Multiple linked DOs: one delivered, one pending (in transit), one cancelled.
const RICH_FIXTURE: FulfilmentOrder[] = [
  {
    order_id: 'mock-do-0001',
    order_number: 'REPPS2605-0012',
    status: 'delivered',
    status_label: 'Picked Up / In Transit',
    actual_delivery_date: '2026-06-24T08:30:00Z',
    is_cancelled: false,
    items: [
      { product_code: 'SOR-TAP-3001', product_type: 'Basin Tap', qty: 2 },
      { product_code: 'SOR-HOSE-110', product_type: 'Flexible Hose', qty: 4 },
    ],
  },
  {
    order_id: 'mock-do-0002',
    order_number: 'REPPS2605-0018',
    status: 'pending',
    status_label: 'Pending',
    actual_delivery_date: null,
    is_cancelled: false,
    items: [{ product_code: 'SOR-SINK-880', product_type: 'Kitchen Sink', qty: 1 }],
  },
  {
    order_id: 'mock-do-0003',
    order_number: 'REPPS2605-0009',
    status: 'cancelled',
    status_label: 'Cancelled',
    actual_delivery_date: null,
    is_cancelled: true,
    items: [{ product_code: 'SOR-MIX-450', product_type: 'Shower Mixer', qty: 1 }],
  },
];

// A single delivered DO — the simple "all delivered → fulfilled" happy path.
const SINGLE_DELIVERED_FIXTURE: FulfilmentOrder[] = [
  {
    order_id: 'mock-do-0100',
    order_number: 'REPPS2606-0003',
    status: 'delivered',
    status_label: 'Picked Up / In Transit',
    actual_delivery_date: '2026-06-28T10:15:00Z',
    is_cancelled: false,
    items: [{ product_code: 'SOR-TAP-3001', product_type: 'Basin Tap', qty: 1 }],
  },
];

const SCENARIOS: FulfilmentOrder[][] = [
  RICH_FIXTURE,
  [], // empty — "No replacement delivery order linked yet."
  SINGLE_DELIVERED_FIXTURE,
];

/** Deterministic scenario pick so each complaint shows a stable mock state. */
export function mockComplaintFulfilmentOrders(complaintId: string): FulfilmentOrder[] {
  const seed = complaintId
    .split('')
    .reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return SCENARIOS[seed % SCENARIOS.length];
}
