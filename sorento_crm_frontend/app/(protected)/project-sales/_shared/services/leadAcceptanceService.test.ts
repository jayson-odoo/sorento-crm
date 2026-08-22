/**
 * P1 - leadAcceptanceService.
 *
 * Pins the two things a screen cannot recover from on its own: the request the worklist
 * makes, and the fact that the route answers in phase 1's envelope while the contract
 * writes the flat one. Getting the envelope wrong loses the record count silently, which
 * looks like an empty page rather than a bug.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  assignLead,
  declineLead,
  listAwaitingAcceptance,
  nudgeLeadAssignee,
} from './leadAcceptanceService';

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

describe('listAwaitingAcceptance', () => {
  it('asks the project-sales lead route with the DataGrid params and the filters', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 25 }, empty: true }),
    );

    await listAwaitingAcceptance({
      pageIndex: 1,
      pageSize: 25,
      searchQuery: 'tower',
      owner_user_id: 'u-ali',
      min_hours: 24,
    });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/leads/awaiting-acceptance');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('query')).toBe('tower');
    expect(url.searchParams.get('owner_user_id')).toBe('u-ali');
    expect(url.searchParams.get('min_hours')).toBe('24');
    // The endpoint serves one order and takes no sort.
    expect(url.searchParams.get('sort')).toBeNull();
  });

  it('omits filters that are not set', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 25 } }),
    );

    await listAwaitingAcceptance({ pageIndex: 0, pageSize: 25 });

    const url = calledUrl();
    expect(url.searchParams.get('owner_user_id')).toBeNull();
    expect(url.searchParams.get('min_hours')).toBeNull();
    expect(url.searchParams.get('query')).toBeNull();
  });

  it('reads the record count out of the nested envelope the route returns', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({
        data: [{ id: 'l1', hours_since_assigned: 50 }],
        pagination: { total: 37, page: 2, limit: 25 },
        empty: false,
      }),
    );

    const result = await listAwaitingAcceptance({ pageIndex: 1, pageSize: 25 });

    expect(result.total).toBe(37);
    expect(result.page).toBe(2);
    expect(result.limit).toBe(25);
    expect(result.data).toHaveLength(1);
  });

  it('reads the flat envelope the contract writes, too', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], total: 12, page: 1, limit: 25 }),
    );

    const result = await listAwaitingAcceptance({ pageIndex: 0, pageSize: 25 });

    expect(result.total).toBe(12);
  });

  it('surfaces the server message rather than a generic failure', async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      status: 403,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'Not your leads to look at' }),
      text: async () => '',
      clone() {
        return this;
      },
    } as unknown as Response);

    await expect(
      listAwaitingAcceptance({ pageIndex: 0, pageSize: 25 }),
    ).rejects.toThrow('Not your leads to look at');
  });
});

describe('the handshake calls', () => {
  it('assigns with the owner and the note', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: 'l1' }));

    await assignLead('l1', { owner_user_id: 'u-ali', note: 'Tender closes Friday' });

    expect(calledUrl().pathname).toBe('/api/v1/project-sales/leads/l1/assign');
    expect(calledInit().method).toBe('POST');
    expect(JSON.parse(String(calledInit().body))).toEqual({
      owner_user_id: 'u-ali',
      note: 'Tender closes Friday',
    });
  });

  it('declines with the reason', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: 'l1' }));

    await declineLead('l1', 'Outside my area');

    expect(calledUrl().pathname).toBe('/api/v1/project-sales/leads/l1/decline');
    expect(JSON.parse(String(calledInit().body))).toEqual({ reason: 'Outside my area' });
  });

  it('nudges by re-assigning to the same person, which is what notifies them again', async () => {
    mockedFetch.mockResolvedValue(okResponse({ id: 'l1' }));

    await nudgeLeadAssignee('l1', 'u-ali', 'Tender closes Friday');

    expect(calledUrl().pathname).toBe('/api/v1/project-sales/leads/l1/assign');
    expect(JSON.parse(String(calledInit().body))).toEqual({
      owner_user_id: 'u-ali',
      note: 'Tender closes Friday',
    });
  });
});
