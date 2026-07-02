import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getActivityFeed } from './activityService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function jsonErrorResponse(status: number, detail: string): Response {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

function calledUrl(): string {
  return mockedFetch.mock.calls[0][0] as string;
}

const EMPTY = {
  items: [],
  actors: [],
  pagination: { page: 1, limit: 50, total: 0 },
};

beforeEach(() => vi.clearAllMocks());

describe('getActivityFeed', () => {
  it('hits /api/v1/audit/activity with 1-based page and limit', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));
    await getActivityFeed({ entity_types: [], page: 1, limit: 50 });

    const url = calledUrl();
    expect(url).toContain('/api/v1/audit/activity?');
    expect(url).toContain('page=1');
    expect(url).toContain('limit=50');
  });

  it('appends each selected entity type as a repeatable param', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));
    await getActivityFeed({
      entity_types: ['complaint', 'order'],
      page: 1,
      limit: 50,
    });

    const url = calledUrl();
    expect(url).toContain('entity_type=complaint');
    expect(url).toContain('entity_type=order');
  });

  it('maps action / user / date / q / trace filters onto query params', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));
    await getActivityFeed({
      entity_types: [],
      action: 'updated',
      user_id: 'user-9',
      date_from: '2026-06-01',
      date_to: '2026-06-30',
      q: '  SO-5567  ',
      trace_id: 'trace-abc',
    });

    const url = calledUrl();
    expect(url).toContain('action=updated');
    expect(url).toContain('user_id=user-9');
    expect(url).toContain('date_from=2026-06-01');
    expect(url).toContain('date_to=2026-06-30');
    expect(url).toContain('q=SO-5567'); // trimmed
    expect(url).toContain('trace_id=trace-abc');
  });

  it('omits filter params that are empty/undefined', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));
    await getActivityFeed({ entity_types: [], action: undefined, q: '' });

    const url = calledUrl();
    expect(url).not.toContain('action=');
    expect(url).not.toContain('user_id=');
    expect(url).not.toContain('entity_type=');
    expect(url).not.toContain('q=');
  });

  it('returns the parsed feed envelope on success', async () => {
    const envelope = {
      items: [
        {
          id: '1',
          entity_type: 'complaint',
          entity_label: 'Complaint CMP-1042',
          entity_href: '/complaint-management/complaints/abc',
          action: 'updated',
          actor_name: 'Jane Tan',
          changed_at: '2026-06-30T09:00:00Z',
          changes: [{ field: 'Status', from: 'Pending', to: 'Resolved' }],
          trace_id: null,
        },
      ],
      actors: [{ id: 'u1', name: 'Jane Tan' }],
      pagination: { page: 1, limit: 50, total: 1 },
    };
    mockedFetch.mockResolvedValue(okResponse(envelope));

    const out = await getActivityFeed({ entity_types: [] });
    expect(out.items).toHaveLength(1);
    expect(out.items[0].entity_label).toBe('Complaint CMP-1042');
    expect(out.actors[0].name).toBe('Jane Tan');
    expect(out.pagination.total).toBe(1);
  });

  it('throws an extracted API error message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(500, 'Boom in the activity feed'));
    await expect(getActivityFeed({ entity_types: [] })).rejects.toThrow(
      'Boom in the activity feed',
    );
  });
});
