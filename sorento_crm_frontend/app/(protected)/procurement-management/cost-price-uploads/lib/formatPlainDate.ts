import { formatDateInMalaysia } from '@/lib/helpers';

/**
 * `YYYY-MM-DD` (a cost list's `start_date`/`end_date`, a change set's validity) has no time
 * of day, so it is a calendar date, never an instant - `formatDateTimeInMalaysia` is for
 * naive-UTC TIMESTAMPS and would risk shifting the day at a timezone boundary. Parsed and
 * read as a calendar day (never local `new Date(str)`, which reads a bare date as local midnight)
 * so a viewer in any timezone reads the same day the server stored, as `dd/mm/yyyy`.
 */
export function formatPlainDate(date: string | null | undefined): string | null {
  if (!date) return null;
  if (!/^\d{4}-\d{2}-\d{2}/.test(date)) return date;
  return formatDateInMalaysia(date.slice(0, 10)) || date;
}
