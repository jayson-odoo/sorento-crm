/**
 * A unique-enough token naming one click (a deferred action's batch id).
 *
 * `crypto.randomUUID` exists only in a SECURE context (https or localhost);
 * on a plain-http host, the tailnet URL among them, it is undefined and a
 * click that called it did nothing at all (crew browser pass, PR #2100).
 * The fallback only has to be unique within this tab, never unguessable.
 */
export function clickToken(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
