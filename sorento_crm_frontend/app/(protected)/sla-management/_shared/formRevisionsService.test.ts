/**
 * formRevisionsService - "does this form type get a Revisions tab" (UAC H2,
 * round 6). The happy path plus the error path going through the shared
 * `extractApiError`, per the repo rule against hand-rolled
 * `response.json().catch(() => ({}))`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '@/lib/api';
import { getRevisionEnabledMap } from './formRevisionsService';

const apiFetchMock = vi.mocked(apiFetch);

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => vi.clearAllMocks());

describe('getRevisionEnabledMap', () => {
  it('hits the enabled-map endpoint and returns the types map', async () => {
    apiFetchMock.mockResolvedValueOnce(
      ok({ types: { stock_inquiry: true, purchase_request: false } }),
    );

    const result = await getRevisionEnabledMap();

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/v1/forms-management/revision-configs/enabled',
    );
    expect(result).toEqual({ stock_inquiry: true, purchase_request: false });
  });

  it('defaults to an empty map when the payload carries no types key', async () => {
    apiFetchMock.mockResolvedValueOnce(ok({}));

    expect(await getRevisionEnabledMap()).toEqual({});
  });

  it('surfaces the backend detail through extractApiError on failure', async () => {
    apiFetchMock.mockResolvedValueOnce(
      fail(500, { detail: 'Revision settings unavailable' }),
    );

    await expect(getRevisionEnabledMap()).rejects.toThrow(
      'Revision settings unavailable',
    );
  });

  it('falls back to the generic message when the error body has no usable detail', async () => {
    apiFetchMock.mockResolvedValueOnce(fail(400, {}));

    await expect(getRevisionEnabledMap()).rejects.toThrow(
      'Failed to load revision settings',
    );
  });
});
