import { extractApiError } from '@/lib/api-client';
import type { NonCancellableRefusal } from '../types/project.types';

/** The `code` the backend refuses a cancel or reduction of a non-cancellable line with. */
export const NON_CANCELLABLE_CODE = 'non_cancellable_line';

/** A 409 `non_cancellable_line`: the message plus the lines it names and who may override. */
export class NonCancellableRefusalError extends Error {
  readonly details: NonCancellableRefusal;

  constructor(message: string, details: NonCancellableRefusal) {
    super(message);
    this.name = 'NonCancellableRefusalError';
    this.details = details;
  }
}

/** True for a refusal the caller may retry with a reason (the dialog's cue). */
export function isOverridableRefusal(error: unknown): error is NonCancellableRefusalError {
  return error instanceof NonCancellableRefusalError && error.details.can_override;
}

/**
 * The error for a failed response: a `NonCancellableRefusalError` for the 409 above, else the
 * plain message `extractApiError` gives. The response is cloned so the shared extractor still
 * gets an unread body.
 */
export async function refusalAwareError(response: Response, fallback: string): Promise<Error> {
  // Only a 409 can be the refusal, so only then is the body read twice.
  const clone =
    response.status === 409 && typeof response.clone === 'function' ? response.clone() : null;
  const message = await extractApiError(response, fallback);
  if (clone) {
    try {
      const body = (await clone.json()) as {
        code?: unknown;
        details?: Partial<NonCancellableRefusal> | null;
      };
      if (body?.code === NON_CANCELLABLE_CODE) {
        return new NonCancellableRefusalError(message, {
          can_override: Boolean(body.details?.can_override),
          lines: Array.isArray(body.details?.lines) ? body.details.lines : [],
        });
      }
    } catch {
      // No JSON body: the plain message stands.
    }
  }
  return new Error(message);
}

/**
 * The refusals a Confirm all reports per order (`ok:false` with `error_code`), merged into one
 * overridable refusal, or null when none is overridable. confirm_many catches per order, so
 * these never arrive as an HTTP 409.
 */
export function overridableRefusalOf(
  results: ReadonlyArray<{
    ok?: boolean;
    error_code?: string | null;
    error_details?: Record<string, unknown> | null;
  }>,
): NonCancellableRefusal | null {
  const lines: NonCancellableRefusal['lines'] = [];
  let found = false;
  for (const entry of results) {
    if (entry.ok || entry.error_code !== NON_CANCELLABLE_CODE) continue;
    const details = entry.error_details as Partial<NonCancellableRefusal> | null | undefined;
    if (!details?.can_override) continue;
    found = true;
    if (Array.isArray(details.lines)) lines.push(...details.lines);
  }
  return found ? { can_override: true, lines } : null;
}
