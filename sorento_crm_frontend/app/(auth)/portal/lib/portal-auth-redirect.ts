/**
 * Where a portal form goes when loading its record is refused for the session, not for the
 * record: no / expired portal session (401) or a session of another contact than the record's
 * owner (403 OWNER_MISMATCH). Both land on the deep-link slug's OTP verify page, carrying the
 * type and id so verify returns the user to that exact record. One rule for every form, so a
 * View link in a WhatsApp message behaves the same whichever record it opens.
 *
 * Returns null for any other error, which the form handles itself (for example, not found).
 */
import { PortalOwnerMismatchError, PortalUnauthorizedError } from './portal-client';
import { portalVerifyPath } from './portal-paths';

export function portalSessionRedirectPath(
  error: unknown,
  opts: { slug?: string | null; type: string; id?: string | null },
): string | null {
  if (!(error instanceof PortalUnauthorizedError || error instanceof PortalOwnerMismatchError)) {
    return null;
  }
  return portalVerifyPath({ slug: opts.slug, reason: 'expired', type: opts.type, id: opts.id });
}
