/**
 * The branding an anonymous visitor is allowed to see before signing in.
 *
 * Contract, matching `app/api/v1/public/branding.py` exactly:
 *
 *   GET /api/v1/public/branding -> { signin_background_url: string | null }
 *
 * Same two departures from the app's ordinary services as the counter-sign page
 * (`app/(auth)/quotation-sign/services/quotationSignService.ts`), for the same reasons:
 *
 * 1. **Plain `fetch`, not `apiFetch`.** `apiFetch` mints a NextAuth bearer token for anything
 *    under `/api/v1/`. Nobody has a session on the sign-in page, and a staff member landing back
 *    on it after a timeout would otherwise send their own credential to a public endpoint.
 * 2. **A resolved base.** The dev rewrite in `next.config` only proxies `/api/v1/*` when
 *    `NEXT_PUBLIC_API_URL` is unset; where it IS set a bare relative URL resolves against the
 *    Next origin, which serves no such route.
 *
 * Everything here degrades to `null`, never to a thrown error: the background is decoration, and
 * a backend that is old, down or unreachable must still let somebody log in. A `null` puts the
 * designed default backdrop on screen, which is a complete answer rather than a failure state.
 */

const PATH = '/api/v1/public/branding';

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? configured.replace(/\/$/, '') : '';
}

export type SigninBranding = {
  /** Absolute URL of the admin-uploaded background, or null when none is set. */
  signinBackgroundUrl: string | null;
};

export const NO_SIGNIN_BRANDING: SigninBranding = { signinBackgroundUrl: null };

export async function getSigninBranding(): Promise<SigninBranding> {
  try {
    const response = await fetch(`${apiBase()}${PATH}`, { cache: 'no-store' });
    if (!response.ok) return NO_SIGNIN_BRANDING;
    const data = (await response.json()) as {
      signin_background_url?: string | null;
    };
    const url = data?.signin_background_url;
    return {
      signinBackgroundUrl:
        typeof url === 'string' && url.trim() ? url.trim() : null,
    };
  } catch {
    return NO_SIGNIN_BRANDING;
  }
}
