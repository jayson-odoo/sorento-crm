import { formatDateTimeInMalaysia } from '@/lib/helpers';

/**
 * What the "Last activity" column says.
 *
 * The stamp itself, never a relative label. "today" and "3d ago" cannot be compared
 * between two rows, cannot be quoted to anyone, and quietly change meaning depending on
 * when the page happened to be loaded: a list left open overnight goes on claiming
 * "today" about yesterday.
 *
 * Returns null when there has been no activity, so the caller renders its own empty
 * state rather than a formatted zero.
 */
export function describeLastActivity(
  lastActivityAt: string | null | undefined,
): string | null {
  if (!lastActivityAt) return null;
  const formatted = formatDateTimeInMalaysia(lastActivityAt);
  // formatDateTimeInMalaysia hands back an empty string for an unparseable input, which
  // would render as a blank cell that looks like a bug rather than like missing data.
  return formatted || null;
}
