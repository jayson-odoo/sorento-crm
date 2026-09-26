/**
 * salesOpportunityService: the contract with /api/v1/sales/opportunities (plan 3.4, 3.7,
 * section 16; UAC S2-8, S2-12, S2-13, S2-15, S2-16).
 *
 * Paths, methods, bodies and query params are asserted directly (LESSONS-LEARNT: a key typo
 * is a silently dropped field on the backend, not an error).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  createSalesOpportunity,
  deleteSalesOpportunity,
  getSalesOpportunities,
  getSalesOpportunity,
  updateSalesOpportunity,
} from './salesOpportunityService';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('salesOpportunityService', () => {
  it('lists opportunities through buildDataGridParams, with the extra filters', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 20 }, empty: true }));

    await getSalesOpportunities({
      pageIndex: 0,
      pageSize: 20,
      sorting: [],
      searchQuery: '',
      statusId: 'st-1',
      salesAgentId: 'agent-1',
      customerId: 'cust-1',
      closeFrom: '2026-10-01',
      closeTo: '2026-10-31',
    });

    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('/api/v1/sales/opportunities?');
    const qs = new URLSearchParams(url.split('?')[1]);
    expect(qs.get('page')).toBe('1');
    expect(qs.get('limit')).toBe('20');
    expect(qs.get('status_id')).toBe('st-1');
    expect(qs.get('sales_agent_id')).toBe('agent-1');
    expect(qs.get('customer_id')).toBe('cust-1');
    expect(qs.get('close_from')).toBe('2026-10-01');
    expect(qs.get('close_to')).toBe('2026-10-31');
  });

  it('reads one opportunity', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'o1' }));
    await getSalesOpportunity('o1');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/opportunities/o1');
  });

  it('creates with the documented body, including lines in entered order', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'o1' }));
    await createSalesOpportunity({
      customer_id: 'cust-1',
      title: 'ZZT Opp',
      expected_amount: '1000',
      expected_close_date: '2026-11-01',
      lines: [{ product_id: 'p1', qty: 2 }],
    });
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/opportunities', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_id: 'cust-1',
        title: 'ZZT Opp',
        expected_amount: '1000',
        expected_close_date: '2026-11-01',
        lines: [{ product_id: 'p1', qty: 2 }],
      }),
    });
  });

  it('updates with a PATCH', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'o1' }));
    await updateSalesOpportunity('o1', { title: 'ZZT Renamed' });
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/opportunities/o1', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'ZZT Renamed' }),
    });
  });

  it('deletes with a DELETE', async () => {
    apiFetch.mockResolvedValue(ok({}));
    await deleteSalesOpportunity('o1');
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/sales/opportunities/o1', { method: 'DELETE' });
  });

  it('routes a server error message through extractApiError', async () => {
    apiFetch.mockResolvedValue(
      new Response(JSON.stringify({ message: 'A customer or a prospect is required.' }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await expect(
      createSalesOpportunity({
        title: 'ZZT',
        expected_amount: '1',
        expected_close_date: '2026-11-01',
      }),
    ).rejects.toThrow(/customer or a prospect/);
  });
});
