/**
 * DEV-LOGIN-BYPASS frontend guard (documentation/plans/identity/PLAN-dev-login-bypass-03oct.md).
 *
 * Server-only: reads `DEV_AUTO_LOGIN`, which is deliberately NOT a `NEXT_PUBLIC_*` value so it
 * is never inlined into the browser bundle. Every check must hold (fail closed):
 *   1. `DEV_AUTO_LOGIN === 'true'`
 *   2. `NODE_ENV !== 'production'` - a production build cannot carry the bypass
 *   3. the browser's Host is `localhost`, `*.localhost` or `127.0.0.1`
 * The backend repeats its own guards; this is the outer layer, not the only one.
 */

type Env = Record<string, string | undefined>;

/** Flag + build mode only (no request). Decides whether the provider is registered at all. */
export function devLoginConfigured(env: Env = process.env): boolean {
  return env.DEV_AUTO_LOGIN === 'true' && env.NODE_ENV !== 'production';
}

/** `localhost`, `*.localhost` or `127.0.0.1`, with an optional numeric port. Mirrors the backend. */
export function isLocalHost(hostHeader: string | null | undefined): boolean {
  if (!hostHeader) return false;
  let host = hostHeader.trim().toLowerCase();
  if (host.startsWith('[')) return false;
  const colon = host.lastIndexOf(':');
  if (colon !== -1) {
    const port = host.slice(colon + 1);
    if (!/^\d+$/.test(port)) return false;
    host = host.slice(0, colon);
  }
  if (host === 'localhost' || host === '127.0.0.1') return true;
  if (host.endsWith('.localhost')) {
    const label = host.slice(0, -'.localhost'.length);
    return label.length > 0 && label.split('.').every((part) => /^[a-z0-9-]+$/.test(part));
  }
  return false;
}

/** Every frontend guard, for one request. */
export function devLoginAllowed(hostHeader: string | null | undefined, env: Env = process.env): boolean {
  return devLoginConfigured(env) && isLocalHost(hostHeader);
}

/** Read the Host header from either a Fetch `Headers` or NextAuth's plain header record. */
export function hostFromHeaders(headers: unknown): string | null {
  if (!headers) return null;
  if (typeof (headers as Headers).get === 'function') {
    return (headers as Headers).get('host');
  }
  const value = (headers as Record<string, string | string[] | undefined>).host;
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}
