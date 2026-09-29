/**
 * AC-ST211: the CRM to-do half of `stockAskService`. `apiFetch` is the seam; `extractApiError`
 * is real, because the message it produces is what the hook toasts. RED until the Phase 1
 * mock branch is removed (the functions currently answer from the in-memory store).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import { getCustomerAsksTodo, listAskAgents, updateSalesAsk } from './stockAskService';

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  } as unknown as Response;
}

const PAYLOAD = {
  today_start: '2026-09-28T16:00:00Z',
  open: [],
  done_today: [],
  truncated: false,
  agent: { code: 'SEAN I', name: 'Sean Ibrahim' },
};

beforeEach(() => {
  apiFetch.mockReset();
});

describe('getCustomerAsksTodo', () => {
  it('GETs /api/v1/sales/customer-asks/todo for my list and returns the payload', async () => {
    apiFetch.mockResolvedValue(jsonResponse(PAYLOAD));
    await expect(getCustomerAsksTodo()).resolves.toEqual(PAYLOAD);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/sales/customer-asks/todo');
  });

  it('adds agent_id for a chosen agent and for all', async () => {
    apiFetch.mockResolvedValue(jsonResponse(PAYLOAD));
    await getCustomerAsksTodo('agent-b');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/sales/customer-asks/todo?agent_id=agent-b');
    await getCustomerAsksTodo('all');
    expect(apiFetch.mock.calls[1][0]).toBe('/api/v1/sales/customer-asks/todo?agent_id=all');
  });

  it('throws the extracted API message', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'Not allowed to view every agent' }, { ok: false, status: 403 }));
    await expect(getCustomerAsksTodo('agent-b')).rejects.toThrow('Not allowed to view every agent');
  });

  it('throws the fallback when the body carries no message', async () => {
    apiFetch.mockResolvedValue(jsonResponse({}, { ok: false, status: 400 }));
    await expect(getCustomerAsksTodo()).rejects.toThrow(/\S/);
  });
});

describe('listAskAgents', () => {
  it('GETs /api/v1/sales/customer-asks/agents', async () => {
    const agents = [{ agent_id: 'a1', code: 'SEAN I', name: 'Sean Ibrahim', open: 4, needs_attention: 2 }];
    apiFetch.mockResolvedValue(jsonResponse(agents));
    await expect(listAskAgents()).resolves.toEqual(agents);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/sales/customer-asks/agents');
  });

  it('throws the extracted API message', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'Forbidden' }, { ok: false, status: 403 }));
    await expect(listAskAgents()).rejects.toThrow('Forbidden');
  });
});

describe('updateSalesAsk', () => {
  it('PATCHes /api/v1/sales/customer-asks/{id} with the JSON patch', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ id: 'ask-1', state: 'done' }));
    await expect(updateSalesAsk('ask-1', { state: 'done' })).resolves.toEqual({ id: 'ask-1', state: 'done' });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/sales/customer-asks/ask-1');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ state: 'done' });
  });

  it('throws the extracted API message', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'Stock ask not found' }, { ok: false, status: 404 }));
    await expect(updateSalesAsk('ask-9', { note: 'x' })).rejects.toThrow('Stock ask not found');
  });
});
