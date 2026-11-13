/**
 * PASSKEY-LOGIN AC-46 (layering) with the backend shapes of AC-03, AC-10,
 * AC-20..AC-23, AC-26, AC-27, AC-30, AC-33: `services/passkeyService.ts` is the
 * one place the passkey routes are called, and every refusal reaches the
 * caller as the backend's own message (through `extractApiError`).
 *
 * The signed-out calls (status, sign-in options) may go through plain `fetch`
 * (the sign-in page has no bearer yet, see `phoneSigninService.ts`) and the
 * signed-in ones through `apiFetch`; both channels land on the same mock so the
 * test pins the route, not the transport.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn();

vi.mock('@/lib/api', () => ({
  apiFetch: (...a: unknown[]) => fetchMock(...a),
}));

import {
  fetchMyPasskeys,
  fetchPasskeyRegistrationOptions,
  fetchPasskeySignInOptions,
  fetchPasskeyStatus,
  fetchUserPasskeys,
  registerPasskey,
  renamePasskey,
  sendPasskeyReauthCode,
  setUserPasskeyEnabled,
} from './passkeyService';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function respondWith(body: unknown, status = 200) {
  fetchMock.mockImplementation(async () => json(body, status));
}

function lastCall(): { path: string; method: string; body: unknown } {
  const [url, init] = fetchMock.mock.calls.at(-1) as [unknown, RequestInit | undefined];
  const path = new URL(String(url), 'http://x').pathname;
  const method = String(init?.method ?? 'GET').toUpperCase();
  const raw = init?.body;
  return { path, method, body: typeof raw === 'string' && raw ? JSON.parse(raw) : undefined };
}

const PASSKEY = {
  id: 'pk-1',
  name: 'Safari on iPhone',
  created_at: '2026-11-12T09:42:00',
  last_used_at: null,
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', (...a: unknown[]) => fetchMock(...a));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('passkeyService - sign in (AC-03, AC-10)', () => {
  it('fetchPasskeyStatus GETs /auth/passkey/status and returns the body', async () => {
    respondWith({ enabled: true });
    await expect(fetchPasskeyStatus()).resolves.toEqual({ enabled: true });
    expect(lastCall()).toMatchObject({ path: '/api/v1/auth/passkey/status', method: 'GET' });
  });

  it('fetchPasskeySignInOptions POSTs /auth/passkey/options and returns challenge + options', async () => {
    const payload = { challenge_id: 'ch-1', options: { challenge: 'abc', rpId: 'localhost' } };
    respondWith(payload);
    await expect(fetchPasskeySignInOptions()).resolves.toEqual(payload);
    expect(lastCall()).toMatchObject({ path: '/api/v1/auth/passkey/options', method: 'POST' });
  });

  it('fetchPasskeySignInOptions rejects with the backend message on refusal', async () => {
    respondWith({ detail: 'Too many attempts. Try again in a minute.' }, 429);
    await expect(fetchPasskeySignInOptions()).rejects.toThrow(
      'Too many attempts. Try again in a minute.',
    );
  });
});

describe('passkeyService - own passkeys (AC-20..AC-23, AC-26, AC-27)', () => {
  it('fetchMyPasskeys GETs /auth/passkeys', async () => {
    respondWith([PASSKEY]);
    await expect(fetchMyPasskeys()).resolves.toEqual([PASSKEY]);
    expect(lastCall()).toMatchObject({ path: '/api/v1/auth/passkeys', method: 'GET' });
  });

  it('sendPasskeyReauthCode POSTs /auth/passkeys/reauth-code', async () => {
    respondWith({ sent_to: '+60•••6789', expires_in_seconds: 600, resend_in_seconds: 60 });
    await sendPasskeyReauthCode();
    expect(lastCall()).toMatchObject({ path: '/api/v1/auth/passkeys/reauth-code', method: 'POST' });
  });

  it('fetchPasskeyRegistrationOptions POSTs the password proof', async () => {
    const payload = { challenge_id: 'reg-1', options: { challenge: 'xyz' } };
    respondWith(payload);
    await expect(fetchPasskeyRegistrationOptions({ password: 'hunter22' })).resolves.toEqual(
      payload,
    );
    expect(lastCall()).toEqual({
      path: '/api/v1/auth/passkeys/register/options',
      method: 'POST',
      body: { password: 'hunter22' },
    });
  });

  it('fetchPasskeyRegistrationOptions POSTs the phone code proof', async () => {
    respondWith({ challenge_id: 'reg-2', options: {} });
    await fetchPasskeyRegistrationOptions({ phone_code: '123456' });
    expect(lastCall().body).toEqual({ phone_code: '123456' });
  });

  it('fetchPasskeyRegistrationOptions rejects with the REAUTH_FAILED message', async () => {
    respondWith({ code: 'REAUTH_FAILED', message: 'That password is not right.' }, 401);
    await expect(fetchPasskeyRegistrationOptions({ password: 'wrong' })).rejects.toThrow(
      'That password is not right.',
    );
  });

  it('registerPasskey POSTs challenge_id + credential (+ name) to /auth/passkeys', async () => {
    respondWith(PASSKEY, 201);
    const credential = { id: 'cred-1', rawId: 'cred-1', type: 'public-key', response: {} };
    await expect(registerPasskey('reg-1', credential as never, 'My Mac')).resolves.toEqual(
      PASSKEY,
    );
    expect(lastCall()).toEqual({
      path: '/api/v1/auth/passkeys',
      method: 'POST',
      body: { challenge_id: 'reg-1', credential, name: 'My Mac' },
    });
  });

  it('registerPasskey rejects with the backend message on a 409', async () => {
    respondWith({ detail: 'This passkey is already registered.' }, 409);
    await expect(registerPasskey('reg-1', { id: 'c' } as never)).rejects.toThrow(
      'This passkey is already registered.',
    );
  });

  it('renamePasskey PATCHes /auth/passkeys/{id} with the name', async () => {
    respondWith({ ...PASSKEY, name: 'Work phone' });
    await renamePasskey('pk-1', 'Work phone');
    expect(lastCall()).toEqual({
      path: '/api/v1/auth/passkeys/pk-1',
      method: 'PATCH',
      body: { name: 'Work phone' },
    });
  });
});

describe('passkeyService - admin (AC-30, AC-33)', () => {
  it('fetchUserPasskeys GETs /user-management/users/{id}/passkeys', async () => {
    respondWith([PASSKEY]);
    await expect(fetchUserPasskeys('user-1')).resolves.toEqual([PASSKEY]);
    expect(lastCall()).toMatchObject({
      path: '/api/v1/user-management/users/user-1/passkeys',
      method: 'GET',
    });
  });

  it('setUserPasskeyEnabled PATCHes /user-management/users/{id}/passkey-enabled', async () => {
    respondWith({ user_id: 'user-1', passkey_enabled: true });
    await expect(setUserPasskeyEnabled('user-1', true)).resolves.toEqual({
      user_id: 'user-1',
      passkey_enabled: true,
    });
    expect(lastCall()).toEqual({
      path: '/api/v1/user-management/users/user-1/passkey-enabled',
      method: 'PATCH',
      body: { enabled: true },
    });
  });

  it('setUserPasskeyEnabled rejects with the backend message on a 403', async () => {
    respondWith({ detail: 'You do not have permission to edit users.' }, 403);
    await expect(setUserPasskeyEnabled('user-1', false)).rejects.toThrow(
      'You do not have permission to edit users.',
    );
  });
});
