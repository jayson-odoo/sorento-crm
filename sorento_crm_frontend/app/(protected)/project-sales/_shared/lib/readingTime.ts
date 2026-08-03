/**
 * How long a document read took, said the way a person would say it.
 *
 * Reading a ten page scan is minutes of waiting with nothing on screen but a spinner.
 * Telling the reviewer afterwards what it actually cost is what stops the next upload
 * feeling like it has hung, so the phrasing matters more than the precision: nobody
 * needs "134,812 ms", they need "2m 15s".
 */
export function formatReadingTime(ms: number | null | undefined): string | null {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return null;

  const totalSeconds = Math.round(ms / 1000);
  // Under a second is real but unsayable in seconds, and rounding it to "0s" reads as
  // a bug rather than as fast.
  if (totalSeconds < 1) return 'under a second';
  if (totalSeconds < 60) return `${totalSeconds}s`;

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`;
}

/** The same duration as a sentence, for a caption under a finished read. */
export function describeReadingTime(ms: number | null | undefined): string | null {
  const formatted = formatReadingTime(ms);
  return formatted === null ? null : `Read in ${formatted}`;
}
