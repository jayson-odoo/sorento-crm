/**
 * Sends one browser crash report to `POST /api/v1/system/client-errors`
 * (CLIENT-ERROR-REPORT), so "The app could not start" has a recorded cause.
 *
 * Plain `fetch`, no `lib/api` import: the root error boundary calls this and must not
 * depend on the chunks that may have failed to load. Never throws; a report that
 * cannot be sent is dropped. A signed-out page has no token and sends nothing.
 */
import { buildSha, isChunkLoadError } from '@/lib/chunk-load-error';

export type ErrorBoundaryKind = 'global' | 'protected';

const MAX_MESSAGE = 2000;
const MAX_STACK = 8000;

// One report per error object, however many times the boundary's effect runs
// (React StrictMode runs it twice in dev; a re-render must not re-send).
const reported = new WeakSet<object>();

/**
 * The JS stack plus React's component stack when a boundary attached one
 * (components/common/ComponentStackBoundary). Safari's DOMException has no JS stack
 * at all, so the component stack is often the only pointer to what threw.
 */
function stackOf(error: Error & { componentStack?: string }): string | null {
  const parts: string[] = [];
  if (error?.stack) parts.push(String(error.stack));
  if (error?.componentStack) parts.push(`Component stack:${String(error.componentStack)}`);
  return parts.length ? parts.join('\n\n').slice(0, MAX_STACK) : null;
}

export function buildClientErrorReport(
  error: Error & { digest?: string; componentStack?: string },
  boundary: ErrorBoundaryKind,
) {
  return {
    boundary,
    name: String(error?.name ?? 'Error').slice(0, 128),
    message: String(error?.message ?? '').slice(0, MAX_MESSAGE),
    stack: stackOf(error),
    digest: error?.digest ?? null,
    // Path only: a query string can hold search terms, filters or link tokens.
    path: typeof window !== 'undefined' ? window.location.pathname : null,
    build_sha: buildSha(),
    is_chunk_error: isChunkLoadError(error),
    timestamp: new Date().toISOString(),
  };
}

export async function reportClientError(
  error: Error & { digest?: string },
  boundary: ErrorBoundaryKind,
): Promise<void> {
  if (!error || typeof error !== 'object' || reported.has(error)) return;
  reported.add(error);
  try {
    const base = process.env.NEXT_PUBLIC_BASE_PATH || '';
    const tokenRes = await fetch(`${base}/api/auth/token`, { credentials: 'same-origin' });
    if (!tokenRes.ok) return;
    const { token } = (await tokenRes.json()) as { token?: string };
    if (!token) return;
    const init: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(buildClientErrorReport(error, boundary)),
    };
    const url = `${base}/api/v1/system/client-errors`;
    // `keepalive` lets the report outlive a reload. Older Safari rejects a keepalive
    // request outright (TypeError) rather than ignoring the flag, so retry without
    // it. sendBeacon is no use here: it cannot carry the Authorization header.
    try {
      await fetch(url, { ...init, keepalive: true });
    } catch {
      await fetch(url, init);
    }
  } catch {
    // Reporting is best effort; the error screen must render regardless.
  }
}
