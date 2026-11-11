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
  const clone = response.clone();
  const message = await extractApiError(response, fallback);
  if (response.status === 409) {
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
