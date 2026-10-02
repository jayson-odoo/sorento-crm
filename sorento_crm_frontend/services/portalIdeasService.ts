/**
 * Public idea track page service (the customer's own idea, reached by its status token).
 *
 * PHASE 1: delegates to `portalIdeasService.mock.ts`. Phase 2 swaps each body for a plain
 * `fetch` (no session, the token is the credential, like `/portal/ticket-draft/[token]`).
 *
 * EXPECTED CONTRACT (PLAN-ideation-in-crm sections 11 and 13), all proxying the ss public routes:
 *
 *   getPortalIdea      GET  /api/v1/public/portal/ideas/{token}
 *       200 PortalIdea (ss `PublicIdeaStatusOut`: title, ideaNumber, statusLabel, statusColor,
 *           submittedAt, submitterFirstName, upvotes); 404 for an unknown token, which the page
 *           renders as its not-found state. Token shape `^[A-Za-z0-9_-]{16,64}$`.
 *   listPortalComments GET  /api/v1/public/portal/ideas/{token}/comments
 *       200 PortalIdeaComment[] oldest first, one reply level, deleted placeholders kept.
 *   postPortalComment  POST /api/v1/public/portal/ideas/{token}/comments  {body}
 *       201 PortalIdeaComment. The author is the idea's submitter (no name is sent). Rate-limited
 *       per token; a 429 reads as an Error with the server's message.
 *
 * ss answers with `Cache-Control: no-store`, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`
 * and the CRM keeps them.
 */
import * as mock from '@/services/portalIdeasService.mock';
import type { PortalIdea, PortalIdeaComment } from '@/types/ideas';

export { PortalIdeaNotFoundError } from '@/services/portalIdeasService.mock';

export const getPortalIdea = (token: string): Promise<PortalIdea> => mock.getPortalIdea(token);
export const listPortalComments = (token: string): Promise<PortalIdeaComment[]> =>
  mock.listPortalComments(token);
export const postPortalComment = (token: string, body: string): Promise<PortalIdeaComment> =>
  mock.postPortalComment(token, body);
