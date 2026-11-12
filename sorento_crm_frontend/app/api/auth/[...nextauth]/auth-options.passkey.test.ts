/**
 * PASSKEY-LOGIN AC-42: a NextAuth Credentials provider `id: 'passkey'` posts
 * `{ challenge_id, credential }` to `/api/v1/auth/passkey/verify` (with the
 * browser's X-Forwarded-For, like the other sign-in providers) and returns the
 * same `User` shape as the credentials provider, `apiToken` = `token`.
 *
 * The page calls `signIn('passkey', { challengeId, credential: JSON.stringify(...) })`,
 * so the credential reaches `authorize` as a JSON string and goes to the
 * backend as the parsed AuthenticationResponseJSON object.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Authorize = (c: Record<string, string> | undefined, req: unknown) => Promise<unknown>;
type ProviderShape = { id: string; options?: { id?: string; authorize?: Authorize } };

const fetchMock = vi.fn();

const CREDENTIAL = {
  id: 'cred-1',
  rawId: 'cred-1',
  type: 'public-key',
  response: { clientDataJSON: 'a', authenticatorData: 'b', signature: 'c', userHandle: 'd' },
  clientExtensionResults: {},
};

const LOGIN_RESPONSE = {
  id: 'user-1',
  email: 'staff.one@example.test',
  name: 'Staff One',
  avatar: null,
  status: 'ACTIVE',
  role_id: 'role-1',
  role_ids: ['role-1'],
  role_name: 'Sales',
  token: 'opaque-session-token',
  home_path: '/dashboard',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

async function passkeyProvider(): Promise<ProviderShape | undefined> {
  vi.resetModules();
  vi.stubEnv('FASTAPI_INTERNAL_URL', 'http://localhost:8101');
  const options = (await import('./auth-options')).default;
  return (options.providers as ProviderShape[]).find((p) => (p.options?.id ?? p.id) === 'passkey');
}

async function authorize(): Promise<Authorize> {
  const provider = await passkeyProvider();
  expect(provider, 'no NextAuth provider with id "passkey"').toBeDefined();
  return provider!.options!.authorize!;
}

describe('NextAuth passkey provider (AC-42)', () => {
  it('is registered with id "passkey"', async () => {
    expect(await passkeyProvider()).toBeDefined();
  });

  it('posts challenge_id + credential to /api/v1/auth/passkey/verify with X-Forwarded-For', async () => {
    fetchMock.mockResolvedValue(json(LOGIN_RESPONSE));
    const run = await authorize();
    await run(
      { challengeId: 'ch-1', credential: JSON.stringify(CREDENTIAL) },
      { headers: { 'x-forwarded-for': '6.6.6.6, 203.0.113.7' } },
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('http://localhost:8101/api/v1/auth/passkey/verify');
    expect((init as RequestInit).method).toBe('POST');
    expect((init as RequestInit).headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-Forwarded-For': '6.6.6.6, 203.0.113.7',
    });
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      challenge_id: 'ch-1',
      credential: CREDENTIAL,
    });
  });

  it('returns the same User shape as the credentials provider, apiToken = token', async () => {
    fetchMock.mockResolvedValue(json(LOGIN_RESPONSE));
    const run = await authorize();
    const user = await run(
      { challengeId: 'ch-1', credential: JSON.stringify(CREDENTIAL) },
      { headers: {} },
    );
    expect(user).toMatchObject({
      id: 'user-1',
      email: 'staff.one@example.test',
      name: 'Staff One',
      status: 'ACTIVE',
      roleId: 'role-1',
      roleIds: ['role-1'],
      roleName: 'Sales',
      apiToken: 'opaque-session-token',
      homePath: '/dashboard',
    });
  });

  it('throws the backend PASSKEY_FAILED message as the JSON error the page parses', async () => {
    fetchMock.mockResolvedValue(
      json(
        { code: 'PASSKEY_FAILED', message: "That passkey didn't work. Sign in another way." },
        401,
      ),
    );
    const run = await authorize();
    const err = await run(
      { challengeId: 'ch-1', credential: JSON.stringify(CREDENTIAL) },
      { headers: {} },
    ).then(
      () => null,
      (e: Error) => e,
    );
    expect(err).toBeInstanceOf(Error);
    const parsed = JSON.parse((err as Error).message);
    expect(parsed).toMatchObject({
      code: 401,
      message: "That passkey didn't work. Sign in another way.",
    });
  });
});
