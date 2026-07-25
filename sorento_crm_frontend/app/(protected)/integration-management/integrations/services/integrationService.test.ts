import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createIntegration,
  deleteIntegration,
  getIntegrations,
  issueKey,
  revokeKey,
  rotateKey,
  updateIntegration,
} from './integrationService';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(async (_r: Response, fallback: string) => fallback),
}));

const { apiFetch } = await import('@/lib/api');
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}
function fail(status = 500) {
  return { ok: false, status, json: async () => ({}) } as unknown as Response;
}

beforeEach(() => mockFetch.mockReset());

describe('getIntegrations', () => {
  it('unwraps the data envelope', async () => {
    mockFetch.mockResolvedValue(ok({ data: [{ id: '1', name: 'esb' }] }));
    await expect(getIntegrations()).resolves.toHaveLength(1);
  });

  it('returns an empty list rather than undefined when the envelope is empty', async () => {
    // A bare `undefined` here would crash `.map` in the view rather than
    // rendering the empty state.
    mockFetch.mockResolvedValue(ok({}));
    await expect(getIntegrations()).resolves.toEqual([]);
  });

  it('throws an extracted message on failure', async () => {
    mockFetch.mockResolvedValue(fail());
    await expect(getIntegrations()).rejects.toThrow('Failed to load integrations');
  });
});

describe('updateIntegration', () => {
  it('omits credentials when not supplied, so the existing one is kept', async () => {
    // AC-AC-07: sending an empty credentials object would clear the stored
    // credential, which an operator would experience as an unexplained outage.
    mockFetch.mockResolvedValue(ok({ id: '1' }));
    await updateIntegration('1', { name: 'renamed' });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body).not.toHaveProperty('credentials_json');
    expect(mockFetch.mock.calls[0][1].method).toBe('PATCH');
  });

  it('sends credentials when explicitly supplied', async () => {
    mockFetch.mockResolvedValue(ok({ id: '1' }));
    await updateIntegration('1', { credentials_json: { k: 'v' } });

    expect(JSON.parse(mockFetch.mock.calls[0][1].body).credentials_json).toEqual({ k: 'v' });
  });
});

describe('key lifecycle', () => {
  it('issues a key against the right endpoint', async () => {
    mockFetch.mockResolvedValue(ok({ key: 'sk_abc', key_prefix: 'sk_abc' }));
    await issueKey('int-1');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/integrations/manage/int-1/keys');
  });

  it('defaults rotation to a 7-day grace window', async () => {
    // Long enough to cover a weekend and someone being away; the caller must
    // have time to migrate before the old key dies.
    mockFetch.mockResolvedValue(ok({ key: 'sk_new' }));
    await rotateKey('int-1');
    expect(JSON.parse(mockFetch.mock.calls[0][1].body).grace_days).toBe(7);
  });

  it('passes a zero grace window through for an immediate kill', async () => {
    // The leaked-key path: waiting seven days is not an acceptable response to
    // a secret that is already public.
    mockFetch.mockResolvedValue(ok({ key: 'sk_new' }));
    await rotateKey('int-1', 0);
    expect(JSON.parse(mockFetch.mock.calls[0][1].body).grace_days).toBe(0);
  });

  it('revokes a specific key under its integration', async () => {
    mockFetch.mockResolvedValue({ ok: true } as Response);
    await revokeKey('int-1', 'key-9');
    expect(mockFetch.mock.calls[0][0]).toBe(
      '/api/v1/integrations/manage/int-1/keys/key-9/revoke',
    );
  });

  it('surfaces a failure to revoke instead of resolving silently', async () => {
    // Silently swallowing this would leave an operator believing a leaked key
    // was dead when it is still live.
    mockFetch.mockResolvedValue(fail(403));
    await expect(revokeKey('int-1', 'key-9')).rejects.toThrow('Failed to revoke key');
  });
});

describe('create and delete', () => {
  it('posts the create payload', async () => {
    mockFetch.mockResolvedValue(ok({ id: '1' }));
    await createIntegration({ name: 'esb', type: 'autocount_esb' });
    expect(mockFetch.mock.calls[0][1].method).toBe('POST');
  });

  it('throws when delete is refused', async () => {
    mockFetch.mockResolvedValue(fail(403));
    await expect(deleteIntegration('1')).rejects.toThrow('Failed to delete integration');
  });
});
