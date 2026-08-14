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
 *   POST /api/v1/public/onboarding/parse        multipart { file }
 *        200 OnboardingParseResult - rows plus per-row problems. Writes nothing.
 *        422 not an Excel workbook.  429 per-IP rate limit.
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
  OnboardingParseResult,
  OnboardingPerson,
  OnboardingPersonPatch,
} from '@/components/common/onboarding/types';

const BASE_PATH = '/api/v1/public/onboarding';

/** A row on its way to the server: no ids, no lane state, no verdict. */
export interface OnboardingDraftRow {
  row_number: number;
  full_name: string;
  nick_name: string | null;
  phone_raw: string | null;
  email_raw: string | null;
  section_label: string | null;
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
    phone_raw: person.phone_raw,
    email_raw: person.email_raw,
    section_label: person.section_label,
    template_id: person.template_id,
    requester_note: person.requester_note,
    needs_system_account: person.needs_system_account,
    needs_respond_contact: person.needs_respond_contact,
    needs_agent_seat: person.needs_agent_seat,
  };
}

/** Apply a patch to a person row. Shared by both screens so an edit means one thing. */
export function applyPersonPatch(
  person: OnboardingPerson,
  patch: OnboardingPersonPatch,
): OnboardingPerson {
  return { ...person, ...patch };
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
  if (init.body && !(init.body instanceof FormData)) {
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

export async function parseSheet(token: string, file: File): Promise<OnboardingParseResult> {
  const form = new FormData();
  form.append('file', file);
  // No Content-Type header: fetch must set the multipart boundary itself.
  return request(
    token,
    '/parse',
    { method: 'POST', body: form },
    'Could not read that workbook.',
  );
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
