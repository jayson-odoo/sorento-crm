/**
 * Single source of truth for the NextAuth session-token cookie name.
 *
 * auth-options.ts renames the session cookie with NEXTAUTH_COOKIE_SUFFIX so two
 * local instances (localhost:3000 vs :3001) don't clobber each other's login
 * (browsers scope cookies by host, ignoring port). Anything that reads the
 * cookie directly via `getToken({ cookieName })` MUST use the same name — else
 * it falls back to the default `next-auth.session-token`, fails to find the
 * suffixed cookie, and returns null. That manifested as: NextAuth session valid
 * but `/api/auth/token` 401s → every FastAPI call 401s after a hard refresh.
 */
export function sessionTokenCookieName(): string {
  const suffix = process.env.NEXTAUTH_COOKIE_SUFFIX
    ? `.${process.env.NEXTAUTH_COOKIE_SUFFIX}`
    : '';
  const secure = (process.env.NEXTAUTH_URL ?? '').startsWith('https://');
  const prefix = secure ? '__Secure-' : '';
  return `${prefix}next-auth.session-token${suffix}`;
}
