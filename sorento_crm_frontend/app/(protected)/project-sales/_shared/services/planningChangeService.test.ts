/**
 * P2 - planningChangeService.
 *
 * Pins the four routes against the exact paths, verbs and bodies the contract states
 * (`planningChangeService.ts` header doc block), and that a failure surfaces the server's own
 * message rather than a generic one.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  applyPlanningChanges,
  getPlanningChangeBatch,
  listPlanningChangeBatches,
  updatePlanningChangeRow,
} from './planningChangeService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

function calledUrl(): URL {
  return new URL(mockedFetch.mock.calls[0][0] as string, 'http://localhost');
}

function calledInit(): RequestInit {
  return mockedFetch.mock.calls[0][1] as RequestInit;
}

beforeEach(() => vi.clearAllMocks());

describe('listPlanningChangeBatches', () => {
  it('asks the flat-envelope route with the DataGrid params and the state filter', async () => {
    mockedFetch.mockResolvedValue(okResponse({ data: [], total: 0, page: 1, limit: 25 }));

    await listPlanningChangeBatches({ page: 2, limit: 25, query: 'JAN', state: 'pending' });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/planning-changes');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('query')).toBe('JAN');
    expect(url.searchParams.get('state')).toBe('pending');
  });

  it('omits state when not filtered', async () => {
    mockedFetch.mockResolvedValue(okResponse({ data: [], total: 0, page: 1, limit: 25 }));

    await listPlanningChangeBatches({});

    expect(calledUrl().searchParams.get('state')).toBeNull();
  });

  it('surfaces the server message on failure', async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'Backend is down' }),
      text: async () => '',
      clone() {
        return this;
      },
    } as unknown as Response);

    await expect(listPlanningChangeBatches({})).rejects.toThrow('Backend is down');
  });
});

describe('getPlanningChangeBatch', () => {
  it('hits the batch route by id', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: 'pcb-1', orders: [] }));

    await getPlanningChangeBatch('pcb-1');

    expect(calledUrl().pathname).toBe('/api/v1/project-sales/planning-changes/pcb-1');
  });
});

describe('updatePlanningChangeRow', () => {
  it('PUTs the one decision the row can hold', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: 'pcr-1', decision: 'keep' }));

    await updatePlanningChangeRow('pcb-1', 'pcr-1', { decision: 'keep' });

    expect(calledUrl().pathname).toBe(
      '/api/v1/project-sales/planning-changes/pcb-1/rows/pcr-1',
    );
    expect(calledInit().method).toBe('PUT');
    expect(JSON.parse(String(calledInit().body))).toEqual({ decision: 'keep' });
  });
});

describe('applyPlanningChanges', () => {
  it('POSTs the apply route for the batch', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ applied_orders: ['SO1'], failed_orders: [], already_applied: false }),
    );

    await applyPlanningChanges('pcb-1');

    expect(calledUrl().pathname).toBe('/api/v1/project-sales/planning-changes/pcb-1/apply');
    expect(calledInit().method).toBe('POST');
  });
});
