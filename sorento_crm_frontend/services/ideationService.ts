import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Ideation embed-session service.
 *
 * BACKEND CONTRACT (Slice D — live; `useIdeationEmbedSession` now calls this).
 * Keys back to UAC AC-42 / PLAN §5.3 (embed SSO).
 *
 *   POST /api/v1/integrations/ideation/embed-session
 *   Request body:  { idea_id?: string }         // omit for the board; pass for a detail view
 *   Response 200:  { iframe_url: string,        // e.g. "{shared_service}/embed/ideas" or "/embed/ideas/{id}"
 *                    token: string,             // embed token (typ="embed"); passed to the iframe, never logged
 *                    expires_at: string }       // ISO 8601
 *
 * The BE mints a signed assertion for the logged-in user, POSTs it to
 * {ideation_shared_service_url}/embed/session, and returns the embed token + iframe URL.
 * On failure (shared-service down / misconfigured) the endpoint returns a non-2xx and the
 * FE shows an explicit error+retry state (AC-44) — never a blank iframe, never leaked secrets.
 */

export interface IdeationEmbedSession {
  iframe_url: string;
  token: string;
  expires_at: string;
}

export async function getIdeationEmbedSession(
  ideaId?: string,
): Promise<IdeationEmbedSession> {
  const res = await apiFetch('/api/v1/integrations/ideation/embed-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ideaId ? { idea_id: ideaId } : {}),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to open the Ideas workspace'));
  return res.json();
}
