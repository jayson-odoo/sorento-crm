/**
 * OCN-ORDER-CHANGE-NOTICE round 17b (security round 4, L7): the Customer Name picker asks the
 * server only from 2 characters on (the server lists no one below that), so focusing the empty
 * box never asks for every customer.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => api.fetch(...a) }));

import { lookupOrderChangeNoticeCustomers } from './orderChangeNoticeService';

beforeEach(() => {
  api.fetch.mockReset();
  api.fetch.mockResolvedValue(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
});

describe('lookupOrderChangeNoticeCustomers', () => {
  it('does not ask the server for an empty or one-character search', async () => {
    for (const q of ['', ' ', 'Z', ' Z ']) expect(await lookupOrderChangeNoticeCustomers(q)).toEqual([]);
    expect(api.fetch).not.toHaveBeenCalled();
  });

  it('asks the notice route from two characters on, trimmed', async () => {
    await lookupOrderChangeNoticeCustomers(' ZZ ');
    expect(api.fetch).toHaveBeenCalledWith('/api/v1/procurement/order-change-notices/lookups/customers?q=ZZ');
  });
});
