/**
 * Admin → contact (public portal) impersonation. Mints a portal token that
 * skips the OTP verification gate so an admin can enter the portal as a
 * contact for debugging / support.
 *
 * **The portal URL is re-based onto the current origin.** The backend builds it from
 * `FRONTEND_BASE_URL`, a single server-side value that cannot be right for every reader:
 * an admin working on any other host or port is sent to the configured one, lands in a
 * DIFFERENT running app, and sees either a stale build or a login screen. The token is the
 * part that matters and it travels in the query string, so only the origin is replaced.
 *
 * The env value is deliberately left alone rather than pointed at whichever port is being
 * tested: it also builds the links sent to real contacts by email and WhatsApp, and those
 * must keep naming the deployed host.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/user-management/contact-impersonation';

export interface ContactImpersonationTarget {
  id: string;
  name: string | null;
  phone_number: string | null;
  space_id: string;
}

export interface ContactImpersonationSession {
  sessionId: string;
  startedAt: string;
  portalUrl: string;
  targetContact: ContactImpersonationTarget;
}

type ApiResponse = {
  session_id: string;
  started_at: string;
  portal_url: string;
  target_contact: ContactImpersonationTarget;
};

/**
 * Keep the path and query, take the origin from the browser.
 *
 * Falls back to the server's URL verbatim when it cannot be parsed or when there is no
 * window (SSR): a slightly wrong link beats no link, and the caller only opens it in
 * response to a click.
 */
export function rebaseOnCurrentOrigin(url: string): string {
  if (typeof window === 'undefined' || !url) return url;
  try {
    // A relative URL already carries no origin, so this resolves it against the current
    // one and there is nothing to replace.
    const parsed = new URL(url, window.location.origin);
    return `${window.location.origin}${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return url;
  }
}

function _adapt(api: ApiResponse): ContactImpersonationSession {
  return {
    sessionId: api.session_id,
    startedAt: api.started_at,
    portalUrl: rebaseOnCurrentOrigin(api.portal_url),
    targetContact: api.target_contact,
  };
}

export async function startContactImpersonation(contactId: string): Promise<ContactImpersonationSession> {
  const response = await apiFetch(`${BASE}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_id: contactId }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to start contact impersonation'));
  }
  return _adapt(await response.json());
}

export async function stopContactImpersonation(): Promise<void> {
  const response = await apiFetch(`${BASE}/stop`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to stop contact impersonation'));
  }
}

export async function fetchCurrentContactImpersonation(): Promise<ContactImpersonationSession | null> {
  const response = await apiFetch(`${BASE}/current`);
  if (!response.ok) return null;
  const body = (await response.json()) as ApiResponse | null;
  return body ? _adapt(body) : null;
}
