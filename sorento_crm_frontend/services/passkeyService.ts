/**
 * passkeyService - passkey sign-in and passkey management (PASSKEY-LOGIN).
 *
 * Signed out (the sign-in page has no bearer yet): plain `fetch`, same as
 * `phoneSigninService.ts`.
 *   GET  /api/v1/auth/passkey/status          -> { enabled }
 *   POST /api/v1/auth/passkey/options         -> { challenge_id, options }
 *   (verify goes through NextAuth's `passkey` provider, server-to-server)
 *
 * Signed in, the REAL user's own passkeys:
 *   GET   /api/v1/auth/passkeys                     -> PasskeyItem[]
 *   POST  /api/v1/auth/passkeys/reauth-code         -> { sent_to }
 *   POST  /api/v1/auth/passkeys/register/options    { password } | { phone_code } -> { challenge_id, options }
 *   POST  /api/v1/auth/passkeys                     { challenge_id, credential, name? } -> PasskeyItem
 *   PATCH /api/v1/auth/passkeys/{id}                { name } -> PasskeyItem
 *   Removal is the deferred record action `user_passkey.delete`.
 *
 * Admin:
 *   GET   /api/v1/user-management/users/{id}/passkeys        -> PasskeyItem[]
 *   PATCH /api/v1/user-management/users/{id}/passkey-enabled { enabled } -> { user_id, passkey_enabled }
 *
 * Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md
 */

import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
} from '@simplewebauthn/browser';

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface PasskeyItem {
  id: string;
  name: string;
  created_at: string | null;
  last_used_at: string | null;
}

export interface PasskeySignInOptions {
  challenge_id: string;
  options: PublicKeyCredentialRequestOptionsJSON;
}

export interface PasskeyRegistrationOptions {
  challenge_id: string;
  options: PublicKeyCredentialCreationOptionsJSON;
}

export type PasskeyProof = { password: string } | { phone_code: string };

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function fetchPasskeyStatus(): Promise<{ enabled: boolean }> {
  const res = await fetch(`${apiBase()}/api/v1/auth/passkey/status`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to check passkeys'));
  return res.json();
}

export async function fetchPasskeySignInOptions(): Promise<PasskeySignInOptions> {
  const res = await fetch(`${apiBase()}/api/v1/auth/passkey/options`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(await extractApiError(res, "That passkey didn't work. Sign in another way."));
  }
  return res.json();
}

export async function fetchMyPasskeys(): Promise<PasskeyItem[]> {
  const res = await apiFetch('/api/v1/auth/passkeys');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load passkeys'));
  return res.json();
}

export async function sendPasskeyReauthCode(): Promise<{ sent_to: string }> {
  const res = await apiFetch('/api/v1/auth/passkeys/reauth-code', { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to send the code'));
  return res.json();
}

export async function fetchPasskeyRegistrationOptions(
  proof: PasskeyProof,
): Promise<PasskeyRegistrationOptions> {
  const res = await apiFetch('/api/v1/auth/passkeys/register/options', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(proof),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start adding a passkey'));
  return res.json();
}

export async function registerPasskey(
  challengeId: string,
  credential: RegistrationResponseJSON,
  name?: string,
): Promise<PasskeyItem> {
  const body: Record<string, unknown> = { challenge_id: challengeId, credential };
  if (name) body.name = name;
  const res = await apiFetch('/api/v1/auth/passkeys', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to add the passkey'));
  return res.json();
}

export async function renamePasskey(id: string, name: string): Promise<PasskeyItem> {
  const res = await apiFetch(`/api/v1/auth/passkeys/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to rename the passkey'));
  return res.json();
}

export async function fetchUserPasskeys(userId: string): Promise<PasskeyItem[]> {
  const res = await apiFetch(`/api/v1/user-management/users/${userId}/passkeys`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load passkeys'));
  return res.json();
}

export async function setUserPasskeyEnabled(
  userId: string,
  enabled: boolean,
): Promise<{ user_id: string; passkey_enabled: boolean }> {
  const res = await apiFetch(`/api/v1/user-management/users/${userId}/passkey-enabled`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update passkey sign-in'));
  return res.json();
}
