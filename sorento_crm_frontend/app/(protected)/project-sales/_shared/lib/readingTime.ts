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

/**
 * How long a read that has NOT finished has been going, from the moment the worker picked
 * it up. Null when we do not know, which is every document uploaded before the backend
 * started recording it.
 *
 * A spinner with no number behind it is exactly what let a killed job sit on screen for
 * an afternoon looking busy. A length is something a person can judge: ten pages measured
 * at just under three minutes, so twenty minutes is visibly wrong and four is not.
 *
 * `startedAt` is the backend's naive UTC, stored and sent without a zone, so the Z is put
 * back before parsing. Parsing it as local time would read as eight hours in the future
 * here and produce no caption at all.
 */
export function describeWaitingFor(startedAt: string | null | undefined): string | null {
  if (!startedAt) return null;
  const started = Date.parse(startedAt.endsWith('Z') ? startedAt : `${startedAt}Z`);
  if (Number.isNaN(started)) return null;
  const seconds = Math.floor((Date.now() - started) / 1000);
  if (seconds < 0) return null;
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'} so far`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'} so far`;
}
