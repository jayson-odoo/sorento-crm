/**
 * The one date formatter (UI v2 rule R1, UAC F-1). Every screen, PDF, export and chat line that
 * shows a date goes through these four functions; `lib/helpers.ts` date helpers delegate here.
 *
 * Input: `Date | string | number | null | undefined`.
 * - A naive string from the API ("2026-11-10T01:42:00", "2026-11-10 01:42:00.123456") is UTC.
 * - A string with `Z` or an offset is taken as written.
 * - A bare "YYYY-MM-DD" is a calendar day and is not shifted.
 * Output is Malaysia time (UTC+8). Empty or invalid input gives '' and never throws.
 */

export type DateInput = Date | string | number | null | undefined;

const MALAYSIA_TZ = 'Asia/Kuala_Lumpur';
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const ZONED = /(Z|[+-]\d{2}:?\d{2})$/i;

/** "2026-11-10 01:42:00.123456" -> "2026-11-10T01:42:00.123"; Safari rejects the space and >3 fraction digits. */
export function normaliseApiDateString(s: string): string {
  return s.replace(/^(\d{4}-\d{2}-\d{2}) (\d)/, '$1T$2').replace(/(\.\d{3})\d+/, '$1');
}

/** Parse an API value as an instant; Invalid Date when it cannot be read. */
export function toInstant(input: DateInput): Date {
  if (input == null) return new Date(NaN);
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);
  let s = String(input).trim();
  if (!s) return new Date(NaN);
  // A calendar day: midnight UTC lands on the same day in Malaysia (UTC+8).
  if (DATE_ONLY.test(s)) return new Date(`${s}T00:00:00Z`);
  s = normaliseApiDateString(s);
  return new Date(ZONED.test(s) ? s : `${s}Z`);
}

const DAY = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: MALAYSIA_TZ,
});

const TIME = new Intl.DateTimeFormat('en-GB', {
  hour: 'numeric',
  minute: '2-digit',
  hourCycle: 'h12',
  timeZone: MALAYSIA_TZ,
});

const TIME_SECONDS = new Intl.DateTimeFormat('en-GB', {
  hour: 'numeric',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h12',
  timeZone: MALAYSIA_TZ,
});

function valid(input: DateInput): Date | null {
  const d = toInstant(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** `10/11/2026` */
export function formatDate(input: DateInput): string {
  const d = valid(input);
  return d ? DAY.format(d) : '';
}

/** `9:42 am` (`9:42:05 am` with seconds) */
export function formatTime(input: DateInput, { seconds = false }: { seconds?: boolean } = {}): string {
  const d = valid(input);
  return d ? (seconds ? TIME_SECONDS : TIME).format(d) : '';
}

/** `10/11/2026, 9:42 am` */
export function formatDateTime(input: DateInput, opts: { seconds?: boolean } = {}): string {
  const d = valid(input);
  return d ? `${DAY.format(d)}, ${formatTime(d, opts)}` : '';
}

/** `01/01/2026 - 31/03/2026`; one end alone shows that end; neither end shows `fallback`. */
export function formatDateRange(start: DateInput, end: DateInput, fallback = ''): string {
  const from = formatDate(start);
  const to = formatDate(end);
  if (from && to) return `${from} - ${to}`;
  return from || to || fallback;
}
