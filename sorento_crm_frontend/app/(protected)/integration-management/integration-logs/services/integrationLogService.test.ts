import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getIntegrationLogs } from './integrationLogService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

function calledUrl(): URL {
  return new URL(mockedFetch.mock.calls[0][0] as string, 'http://localhost');
}

const emptyEnvelope = { data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true };

beforeEach(() => vi.clearAllMocks());

describe('getIntegrationLogs — System Health drill-down params', () => {
  it('adds status, integration_channel and created_from to the request', async () => {
    mockedFetch.mockResolvedValue(okResponse(emptyEnvelope));

    await getIntegrationLogs({
      pageIndex: 0,
      pageSize: 50,
      status: 'failed',
      integration_channel: 'respond_io',
      created_from: '2026-07-05T09:00:00.000Z',
    });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/integrations/logs');
    expect(url.searchParams.get('status')).toBe('failed');
    expect(url.searchParams.get('integration_channel')).toBe('respond_io');
    expect(url.searchParams.get('created_from')).toBe('2026-07-05T09:00:00.000Z');
    expect(url.searchParams.get('page')).toBe('1');
    expect(url.searchParams.get('limit')).toBe('50');
  });

  it('omits the drill-down params when not supplied', async () => {
    mockedFetch.mockResolvedValue(okResponse(emptyEnvelope));

    await getIntegrationLogs({ pageIndex: 0, pageSize: 50 });

    const url = calledUrl();
    expect(url.searchParams.has('status')).toBe(false);
    expect(url.searchParams.has('integration_channel')).toBe(false);
    expect(url.searchParams.has('created_from')).toBe(false);
  });

  it('translates pageIndex to the 1-based page param and carries sorting', async () => {
    mockedFetch.mockResolvedValue(okResponse(emptyEnvelope));

    await getIntegrationLogs({
      pageIndex: 2,
      pageSize: 25,
      sorting: [{ id: 'created_at', desc: true }],
    });

    const url = calledUrl();
    expect(url.searchParams.get('page')).toBe('3');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('sort')).toBe('created_at');
    expect(url.searchParams.get('dir')).toBe('desc');
  });

  it('throws when the response is not ok', async () => {
    mockedFetch.mockResolvedValue({ ok: false } as Response);
    await expect(getIntegrationLogs({ pageIndex: 0, pageSize: 50 })).rejects.toThrow(
      /failed to fetch integration logs/i,
    );
  });
});
