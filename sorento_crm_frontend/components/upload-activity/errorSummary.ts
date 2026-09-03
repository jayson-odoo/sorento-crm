/**
 * Reduces a possibly multi-line error/traceback to something a single
 * drawer row can render safely truncated on one line.
 *
 * A failed import job's `job_error` can be a full Python traceback
 * ("Traceback (most recent call last): File \"...\" ... ValueError: ...").
 * The old design wrapped that verbatim onto two lines - fine for a short
 * RQ failure string, but a real traceback rendered as one unbroken line
 * that overflowed the drawer and pushed the row's status icon off the
 * edge. This picks the last non-empty line instead - the exception
 * itself, not the traceback header - so the row always fits.
 */
const MAX_LENGTH = 200;

export function errorSummary(text: string): string {
  if (!text) return text;
  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const last = lines.length > 0 ? lines[lines.length - 1] : text;
  return last.length > MAX_LENGTH ? `${last.slice(0, MAX_LENGTH)}…` : last;
}
