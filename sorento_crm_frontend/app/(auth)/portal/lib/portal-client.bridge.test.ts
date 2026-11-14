/**
 * SIGNIN-2FA-NOT-ROLE fix round 1 R1 (nothing hangs): `openPortalFromCrm(slug)`.
 *
 * - no staff Bearer (`getAuthToken()` from `@/lib/api` is null) -> null, and no fetch at all;
 * - a fetch that never answers -> null after 10 s, with the request ABORTED (not left hanging);
 * - 401 / 403 / 500 -> null;
 * - 200 -> `{ token, expires_at }`, from a POST to /api/v1/public/portal/session-from-crm carrying
 *   the Bearer and `{ slug }`.
 *
 * The 10 s bound is driven with vitest fake timers (setTimeout/clearTimeout), so the timeout must
 * be armed through `setTimeout` (e.g. an AbortController aborted from a setTimeout), not a
 * runtime-internal timer the fake clock cannot advance.
 *
 * Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getAuthTokenMock = vi.fn();
vi.mock('@/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api')>();
  return { ...original, getAuthToken: (...a: unknown[]) => getAuthTokenMock(...a) };
});

import { openPortalFromCrm } from './portal-client';

const SLUG = 'SLUG123456';
const fetchMock = vi.fn();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  getAuthTokenMock.mockResolvedValue('crm-bearer');
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('openPortalFromCrm', () => {
  it('no CRM session (getAuthToken null): null, and fetch is never called', async () => {
    getAuthTokenMock.mockResolvedValue(null);

    await expect(openPortalFromCrm(SLUG)).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('200: returns { token, expires_at } from a POST carrying the Bearer and the slug', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { token: 'PORTAL-TOK', expires_at: '2026-12-14T00:00:00' }),
    );

    await expect(openPortalFromCrm(SLUG)).resolves.toEqual({
      token: 'PORTAL-TOK',
      expires_at: '2026-12-14T00:00:00',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/api/v1/public/portal/session-from-crm');
    expect(init.method).toBe('POST');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer crm-bearer');
    expect(JSON.parse(String(init.body))).toEqual({ slug: SLUG });
  });

  it.each([401, 403, 500])('%i: null', async (status) => {
    fetchMock.mockResolvedValue(jsonResponse(status, { detail: 'nope' }));

    await expect(openPortalFromCrm(SLUG)).resolves.toBeNull();
  });

  it('a network error: null', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(openPortalFromCrm(SLUG)).resolves.toBeNull();
  });

  it('a fetch that never answers: null after 10 s, and the request is aborted', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    let signal: AbortSignal | undefined;
    // Never resolves on its own; only an abort ends it (as a real fetch does).
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () =>
          reject(new DOMException('The operation was aborted.', 'AbortError')),
        );
      });
    });

    let settled = false;
    let result: unknown = 'pending';
    const call = openPortalFromCrm(SLUG).then((r) => {
      settled = true;
      result = r;
    });

    // Let the getAuthToken await and the fetch call happen.
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(signal, 'the request must carry an AbortSignal').toBeDefined();

    await vi.advanceTimersByTimeAsync(9_000);
    expect(settled).toBe(false);

    await vi.advanceTimersByTimeAsync(1_500);
    // No `await call` here: on a hanging implementation that would hang the test itself.
    expect(settled, 'openPortalFromCrm must give up within 10 s').toBe(true);
    await call;
    expect(result).toBeNull();
    expect(signal?.aborted).toBe(true);
  });
});
