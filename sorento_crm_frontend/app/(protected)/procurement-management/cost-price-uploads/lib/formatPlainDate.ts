/**
 * `YYYY-MM-DD` (a cost list's `start_date`/`end_date`, a change set's validity) has no time
 * of day, so it is a calendar date, never an instant - `formatDateTimeInMalaysia` is for
 * naive-UTC TIMESTAMPS and would risk shifting the day at a timezone boundary. Parsed and
 * formatted in UTC (never local `new Date(str)`, which reads a bare date as local midnight)
 * so a viewer in any timezone reads the same day the server stored.
 */
export function formatPlainDate(date: string | null | undefined): string | null {
  if (!date) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!match) return date;
  const [, y, m, d] = match;
  const asDate = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(asDate);
}
