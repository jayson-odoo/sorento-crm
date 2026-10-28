/**
 * Admin → contact (public portal) impersonation. Mints a portal token that
 * skips the OTP verification gate so an admin can enter the portal as a
 * contact for debugging / support.
 */
import { apiFetch } from '@/lib/api';
import { impersonationStore } from '@/lib/impersonation-store';
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
  /** The linked active salesperson user, when there is one (PORTAL-P3-ROLE-MENU). */
  crmUserId: string | null;
  targetContact: ContactImpersonationTarget;
}

type ApiResponse = {
  session_id: string;
  started_at: string;
  portal_url: string;
  target_contact: ContactImpersonationTarget;
  crm_user_id?: string | null;
};

function _adapt(api: ApiResponse): ContactImpersonationSession {
  return {
    sessionId: api.session_id,
    startedAt: api.started_at,
    portalUrl: api.portal_url,
    crmUserId: api.crm_user_id ?? null,
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

/**
 * The contact linked to the user the CRM is currently viewed as (the `/api/v1/` URL carries the
 * impersonation header, so this answers for the target). Null when there is none.
 */
export async function fetchImpersonatedUserContactId(): Promise<string | null> {
  const response = await apiFetch('/api/v1/user-management/users/me');
  if (!response.ok) return null;
  const body = (await response.json()) as { id?: string; respond_contact_id?: string | null };
  // The header only applies while the view-as row is live: an answer as anyone else (the admin,
  // after the view-as ended) is not the target's contact.
  if (!body.id || body.id !== impersonationStore.getState()?.targetUser.id) return null;
  return body.respond_contact_id ?? null;
}
