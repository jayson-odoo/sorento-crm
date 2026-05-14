/**
 * Admin → contact (public portal) impersonation. Mints a portal token that
 * skips the OTP verification gate so an admin can enter the portal as a
 * contact for debugging / support.
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

function _adapt(api: ApiResponse): ContactImpersonationSession {
  return {
    sessionId: api.session_id,
    startedAt: api.started_at,
    portalUrl: api.portal_url,
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
