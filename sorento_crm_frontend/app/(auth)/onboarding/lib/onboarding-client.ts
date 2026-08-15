/**
 * The public onboarding intake API client (UAC AC-3.6).
 *
 * Every call is gated by the per-request intake token, sent as
 * `X-Onboarding-Token`. There is no account, no NextAuth session and no cookie:
 * this module is the whole auth story for the intake page. The token comes from
 * the URL path and is passed in explicitly rather than stashed in
 * localStorage - the link IS the credential, and a token cached from a previous
 * batch would answer for the wrong request.
 *
 *   GET  /api/v1/public/onboarding/me
 *        200 OnboardingIntakeContext - company, requester, expiry, status,
 *            template LABELS (never roles), and the rows saved so far.
 *        401 unknown / expired / revoked token.
 *
 *   PUT  /api/v1/public/onboarding/rows          { rows: OnboardingDraftRow[] }
 *        200 OnboardingIntakeContext - whole-list replace, keyed on row_number.
 *        409 once the request has left `sent`.
 *
 *   POST /api/v1/public/onboarding/submit        { requester_note }
 *        200 OnboardingIntakeContext with `editable: false`. The same token now
 *            serves the read-only status page.
 */

import type {
  OnboardingIntakeContext,
  OnboardingPerson,
} from '@/components/common/onboarding/types';

// Applying a patch is the same operation on both screens, so it now lives with
// the shared onboarding vocabulary. Re-exported here because this module is what
// the intake screen imports.
export { applyPersonPatch } from '@/components/common/onboarding/types';

const BASE_PATH = '/api/v1/public/onboarding';

/** A row on its way to the server: no ids, no lane state, no verdict. */
export interface OnboardingDraftRow {
  row_number: number;
  full_name: string;
  nick_name: string | null;
  role_label: string | null;
  phone_raw: string | null;
  email_raw: string | null;
  template_id: string | null;
  requester_note: string | null;
  needs_system_account: boolean;
  needs_respond_contact: boolean;
  needs_agent_seat: boolean;
}

export function toDraftRow(person: OnboardingPerson): OnboardingDraftRow {
  return {
    row_number: person.row_number,
    full_name: person.full_name,
    nick_name: person.nick_name,
    role_label: person.role_label,
    phone_raw: person.phone_raw,
    email_raw: person.email_raw,
    template_id: person.template_id,
    requester_note: person.requester_note,
    needs_system_account: person.needs_system_account,
    needs_respond_contact: person.needs_respond_contact,
    needs_agent_seat: person.needs_agent_seat,
  };
}

/**
 * The backend base URL.
 *
 * Absolute when `NEXT_PUBLIC_API_URL` is set; otherwise relative, so the Next
 * rewrite proxies `/api/v1/*` to FastAPI. Same resolution the contact portal
 * uses - see `app/(auth)/portal/lib/portal-client.ts`.
 */
function apiBase(): string {
  if (typeof process !== 'undefined') {
    const env = process.env?.NEXT_PUBLIC_API_URL;
    if (env) return env.replace(/\/$/, '');
  }
  return '';
}

function url(path: string): string {
  return `${apiBase()}${BASE_PATH}${path}`;
}

/** The server's message, or the fallback. Never a bare "Failed to fetch". */
async function errorFrom(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return body?.detail || body?.message || body?.error || fallback;
  } catch {
    return fallback;
  }
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit,
  fallback: string,
): Promise<T> {
  if (!token) throw new Error('This link is missing its token.');
  const headers = new Headers(init.headers || {});
  headers.set('X-Onboarding-Token', token);
  if (init.body) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(url(path), { ...init, headers });
  if (!response.ok) {
    throw new Error(await errorFrom(response, fallback));
  }
  return response.json();
}

export async function fetchIntakeContext(token: string): Promise<OnboardingIntakeContext> {
  return request(token, '/me', { method: 'GET' }, 'This link is no longer valid.');
}

export async function saveRows(
  token: string,
  rows: OnboardingDraftRow[],
): Promise<OnboardingIntakeContext> {
  return request(
    token,
    '/rows',
    { method: 'PUT', body: JSON.stringify({ rows }) },
    'Could not save these rows.',
  );
}

export async function submitIntake(
  token: string,
  requesterNote: string | null,
): Promise<OnboardingIntakeContext> {
  return request(
    token,
    '/submit',
    { method: 'POST', body: JSON.stringify({ requester_note: requesterNote }) },
    'Could not submit this batch.',
  );
}
