import { randomId } from '@/lib/id';

/**
 * A unique token naming one click (a deferred action's batch id).
 *
 * `crypto.randomUUID` exists only in a SECURE context, so on a plain-http host
 * (the tailnet URL among them) a click that called it did nothing at all (crew
 * browser pass, PR #2100). `randomId` carries the fallback for every caller.
 */
export function clickToken(): string {
  return randomId();
}
