import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getHealthSummary } from './healthService';

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

const summary = {
  generated_at: '2026-06-30T12:00:00Z',
  email_outbox: { pending: 1, sent: 2, failed: 0, cancelled: 0, failed_last_24h: 0 },
  imports: { total_last_24h: 4, finished_last_24h: 3, failed_last_24h: 1, success_rate: 75 },
  scheduled_tasks: { total: 5, overdue: 0, last_run_failed: 0 },
  integrations: { channels: [] },
  audit_activity: { count_last_24h: 3, daily_trend: [] },
};

beforeEach(() => vi.clearAllMocks());

describe('getHealthSummary', () => {
  it('hits the /api/v1/system/health/summary endpoint', async () => {
    mockedFetch.mockResolvedValue(okResponse(summary));

    await getHealthSummary();

    expect(mockedFetch.mock.calls[0][0]).toBe('/api/v1/system/health/summary');
  });

  it('returns the parsed summary payload on success', async () => {
    mockedFetch.mockResolvedValue(okResponse(summary));

    const out = await getHealthSummary();
    expect(out.imports?.success_rate).toBe(75);
    expect(out.email_outbox?.pending).toBe(1);
  });

  it('throws an extracted API error message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(403, 'Permission required: system.health.view'));

    await expect(getHealthSummary()).rejects.toThrow('Permission required: system.health.view');
  });
});
