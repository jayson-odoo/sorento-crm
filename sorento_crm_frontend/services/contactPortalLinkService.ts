import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface PortalLinkResponse {
  token: string;
  expires_at: string;
  portal_url: string;
  reused: boolean;
}

export interface PortalLinkSendResponse extends PortalLinkResponse {
  sent: true;
}

export async function getContactPortalLink(contactId: string): Promise<PortalLinkResponse> {
  const res = await apiFetch(`/api/v1/user-management/contacts/${contactId}/portal-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to get portal link'));
  return res.json();
}

export async function sendContactPortalLink(contactId: string): Promise<PortalLinkSendResponse> {
  const res = await apiFetch(`/api/v1/user-management/contacts/${contactId}/portal-link/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to send portal link'));
  return res.json();
}
