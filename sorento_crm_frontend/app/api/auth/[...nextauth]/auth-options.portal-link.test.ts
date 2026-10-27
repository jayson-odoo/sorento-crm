/**
 * PORTAL-P1-SESSION-LINK: the `phone-otp` provider also accepts the one-time secret the portal's
 * verify-otp returned (`portal_link_secret`) and exchanges it at `/api/v1/auth/portal-link`. No new provider.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Authorize = (c: Record<string, string> | undefined, req: unknown) => Promise<unknown>;
type ProviderShape = { id: string; options?: { id?: string; authorize?: Authorize } };

const fetchMock = vi.fn();

const LOGIN = {
  token: 'api-session-token',
  id: 'u1',
  email: null,
  name: 'Sales Person',
  avatar: null,
  status: 'ACTIVE',
  role_id: 'r1',
  role_name: 'Salesperson',
  role_ids: ['r1'],
  home_path: '/portal/c/SLUG',
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

async function phoneOtpAuthorize(): Promise<Authorize> {
  vi.resetModules();
  vi.stubEnv('FASTAPI_INTERNAL_URL', 'http://localhost:8101');
  const options = (await import('./auth-options')).default;
  const provider = (options.providers as ProviderShape[]).find(
    (p) => (p.options?.id ?? p.id) === 'phone-otp',
  );
  return provider!.options!.authorize!;
}

describe('phone-otp authorize with a portal_link_secret', () => {
  it('posts only the secret to /auth/portal-link and returns the session user', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(LOGIN), { status: 200 }));
    const authorize = await phoneOtpAuthorize();
    const user = (await authorize(
      { portal_link_secret: 'PLS123' },
      { headers: { 'x-forwarded-for': '203.0.113.7' } },
    )) as Record<string, unknown>;

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('http://localhost:8101/api/v1/auth/portal-link');
    expect((init as RequestInit).method).toBe('POST');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ portal_link_secret: 'PLS123' });
    expect((init as RequestInit).headers).toMatchObject({ 'X-Forwarded-For': '203.0.113.7' });
    expect(user.apiToken).toBe('api-session-token');
    expect(user.id).toBe('u1');
    expect(user.homePath).toBe('/portal/c/SLUG');
  });

  it('a refusal throws the same error shape as a wrong code', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Portal link sign-in refused.' }), { status: 401 }),
    );
    const authorize = await phoneOtpAuthorize();
    await expect(authorize({ portal_link_secret: 'PLS123' }, { headers: {} })).rejects.toThrow(
      JSON.stringify({ code: 401, message: 'Portal link sign-in refused.' }),
    );
  });

  it('a phone + code sign-in still goes to /auth/phone/verify', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(LOGIN), { status: 200 }));
    const authorize = await phoneOtpAuthorize();
    await authorize({ phone: '+60123456789', code: '123456' }, { headers: {} });
    expect(String(fetchMock.mock.calls[0][0])).toBe('http://localhost:8101/api/v1/auth/phone/verify');
  });

  it('neither a secret nor phone + code is refused before any fetch', async () => {
    const authorize = await phoneOtpAuthorize();
    await expect(authorize({}, { headers: {} })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
