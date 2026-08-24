export const throttle = (
  func: (...args: unknown[]) => void,
  limit: number,
): ((...args: unknown[]) => void) => {
  let lastFunc: ReturnType<typeof setTimeout> | null = null;
  let lastRan: number | null = null;

  return function (this: unknown, ...args: unknown[]) {
    if (lastRan === null) {
      func.apply(this, args);
      lastRan = Date.now();
    } else {
      if (lastFunc !== null) {
        clearTimeout(lastFunc);
      }
      lastFunc = setTimeout(
        () => {
          if (Date.now() - (lastRan as number) >= limit) {
            func.apply(this, args);
            lastRan = Date.now();
          }
        },
        limit - (Date.now() - (lastRan as number)),
      );
    }
  };
};

export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;

  return function (...args: Parameters<T>): void {
    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(() => {
      func(...args);
    }, wait);
  };
}

export function uid(): string {
  return (Date.now() + Math.floor(Math.random() * 1000)).toString();
}

export function getInitials(
  name: string | null | undefined,
  count?: number,
): string {
  if (!name || typeof name !== 'string') {
    return '';
  }

  const initials = name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase());

  return count && count > 0
    ? initials.slice(0, count).join('')
    : initials.join('');
}

export function toAbsoluteUrl(pathname: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_BASE_PATH;

  if (baseUrl && baseUrl !== '/') {
    return process.env.NEXT_PUBLIC_BASE_PATH + pathname;
  } else {
    return pathname;
  }
}

const DEFAULT_USER_AVATAR_PATH = '/media/avatars/300-2.png';

/**
 * Avatar src for <img>: full URLs (CloudFront, OAuth) unchanged; app-relative paths via toAbsoluteUrl.
 */
export function resolveUserAvatarSrc(
  avatar: string | null | undefined,
  fallback: string = DEFAULT_USER_AVATAR_PATH,
): string {
  const raw =
    avatar != null && String(avatar).trim()
      ? String(avatar).trim()
      : fallback;
  if (
    raw.startsWith('http://') ||
    raw.startsWith('https://') ||
    raw.startsWith('data:') ||
    raw.startsWith('blob:')
  ) {
    return raw;
  }
  const path = raw.startsWith('/') ? raw : `/${raw}`;
  return toAbsoluteUrl(path);
}

export function timeAgo(date: Date | string): string {
  const now = new Date();
  const inputDate = typeof date === 'string' ? new Date(date) : date;
  const diff = Math.floor((now.getTime() - inputDate.getTime()) / 1000);

  if (diff < 60) return 'just now';
  if (diff < 3600)
    return `${Math.floor(diff / 60)} minute${Math.floor(diff / 60) > 1 ? 's' : ''} ago`;
  if (diff < 86400)
    return `${Math.floor(diff / 3600)} hour${Math.floor(diff / 3600) > 1 ? 's' : ''} ago`;
  if (diff < 604800)
    return `${Math.floor(diff / 86400)} day${Math.floor(diff / 86400) > 1 ? 's' : ''} ago`;
  if (diff < 2592000)
    return `${Math.floor(diff / 604800)} week${Math.floor(diff / 604800) > 1 ? 's' : ''} ago`;
  if (diff < 31536000)
    return `${Math.floor(diff / 2592000)} month${Math.floor(diff / 2592000) > 1 ? 's' : ''} ago`;

  return `${Math.floor(diff / 31536000)} year${Math.floor(diff / 31536000) > 1 ? 's' : ''} ago`;
}

/** Pad number to 2 digits for dd/MM/yyyy */
function padTwo(n: number): string {
  return n.toString().padStart(2, '0');
}

export function formatDate(input: Date | string | number): string {
  const date = new Date(input);
  const day = padTwo(date.getDate());
  const month = padTwo(date.getMonth() + 1);
  const year = date.getFullYear();
  return `${day}/${month}/${year}`;
}

/**
 * Format a money amount with exactly 2 decimal places and thousands separators.
 * Standard across all form line-item views (unit price / total / grand total).
 * Returns '-' for null/undefined/NaN so callers can drop their own guards.
 */
export function formatMoney2dp(
  value: number | string | null | undefined,
  fallback = '-',
): string {
  if (value == null || value === '') return fallback;
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return fallback;
  return num.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Format a money amount with the system currency format (e.g. "RM {value}").
 * `format` is the `currencyFormat` system setting - pass it from `useCurrencyFormat()`
 * on protected pages; the default matches the shipped setting so public/token pages
 * (which cannot read the settings endpoint) still render "RM 400.00".
 * Returns `fallback` for null/undefined/NaN.
 */
export function formatCurrency(
  value: number | string | null | undefined,
  format = 'RM {value}',
  fallback = '-',
): string {
  const amount = formatMoney2dp(value, '');
  if (!amount) return fallback;
  return (format || 'RM {value}').replace('{value}', amount);
}

/**
 * Parse a value to a Date; returns null if invalid or missing.
 * Use for API values that may be null, undefined, or malformed.
 */
export function parseDateSafe(
  value: Date | string | number | null | undefined
): Date | null {
  if (value == null) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const date = new Date(value as string | number);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Format a date for display; returns fallback for invalid/missing values.
 */
export function formatDateSafe(
  value: Date | string | number | null | undefined,
  fallback = '-'
): string {
  const date = parseDateSafe(value);
  return date ? formatDate(date) : fallback;
}

/**
 * Format a date-time for display; returns fallback for invalid/missing values.
 */
export function formatDateTimeSafe(
  value: Date | string | number | null | undefined,
  fallback = '-'
): string {
  const date = parseDateSafe(value);
  return date ? formatDateTime(date) : fallback;
}

/**
 * Parse a naive UTC datetime string from the database and return a Date object.
 * 
 * CRITICAL RULE: 
 * - Database stores UTC time internally (timestamptz)
 * - Backend sends naive UTC strings (no timezone info): "2026-01-28T00:27:58"
 * - Frontend displays these times AS-IS in local formatting (00:27 stays 00:27)
 * - NO timezone conversion - display the UTC hour/minute/second directly
 * 
 * Example:
 * - DB stores: 2026-01-28 00:27:58 UTC (displayed by PostgreSQL as 08:27:58+08:00)
 * - Backend sends: "2026-01-28T00:27:58" (naive UTC string)
 * - Frontend displays: "28/01/2026, 12:27 AM" (00:27 displayed as-is)
 */
export function parseNaiveDateTimeAsLocal(dateString: string | Date): Date {
  if (dateString instanceof Date) {
    return dateString;
  }

  // Remove any milliseconds and ensure clean string
  let cleanString = dateString.replace(/\.\d{3,}/, '');
  
  // If it has timezone info (Z or +/-HH:MM), remove it and treat as naive
  cleanString = cleanString.replace(/Z$/, '').replace(/[+-]\d{2}:?\d{2}$/, '');
  
  // Parse as local time (no Z suffix) - this makes JavaScript treat it as if it's already local time
  // This way, 00:27 displays as 00:27, not converted to a different timezone
  return new Date(cleanString);
}

/**
 * Parse API datetime string as UTC (backend sends naive UTC strings).
 * Use for duration calculations so (responded_at - initiated_at) is correct.
 */
export function parseDateTimeAsUTC(dateString: string | Date): Date {
  if (dateString instanceof Date) {
    return dateString;
  }
  const s = String(dateString).trim();
  if (!s) return new Date(NaN);
  if (s.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(s)) {
    return new Date(s);
  }
  return new Date(s + 'Z');
}

/** Malaysia timezone (UTC+8) for display of API timestamps stored as UTC in DB */
const MALAYSIA_TZ = 'Asia/Kuala_Lumpur';

/**
 * Respond.io message `status[0].timestamp` may be Unix seconds or milliseconds (API / payload variant).
 * Treating ms as seconds and multiplying by 1000 yields invalid far-future dates (e.g. year 58xxx).
 */
export function respondIoTimestampToDate(timestamp: number): Date {
  if (timestamp == null || !Number.isFinite(timestamp)) {
    return new Date(NaN);
  }
  const ms = timestamp > 1e12 ? timestamp : timestamp * 1000;
  return new Date(ms);
}

function toUTCDate(input: Date | string | number): Date {
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);
  return parseDateTimeAsUTC(input);
}

const PROMOTION_CIVIL_YMD = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parse promotion start/end from the API into an instant `Date`.
 * - `YYYY-MM-DD` alone is Malaysia civil calendar (same as server `promotion_dates` DATE_ONLY).
 * - Datetime strings use naive-UTC semantics via {@link parseDateTimeAsUTC}.
 */
export function promotionBoundaryUtcInstantFromApi(input: Date | string | number): Date {
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);
  const s = String(input).trim();
  if (!s) return new Date(NaN);
  if (PROMOTION_CIVIL_YMD.test(s) && !s.includes('T')) {
    const ms = Date.parse(`${s}T00:00:00+08:00`);
    return new Date(ms);
  }
  return parseDateTimeAsUTC(s);
}

/**
 * Format promotion start/end (API string or Date) as dd/mm/yyyy in Malaysia.
 * Prefer over {@link formatDateInMalaysia} for promotion boundaries so date-only payloads stay aligned.
 */
export function formatPromotionBoundaryInMalaysia(input: Date | string | number): string {
  const date = promotionBoundaryUtcInstantFromApi(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: MALAYSIA_TZ,
  }).format(date);
}

/**
 * Format a UTC datetime (from API/DB) as date only in Malaysia timezone.
 * Pass naive UTC strings from the backend; they are parsed as UTC then displayed in Malaysia.
 */
export function formatDateInMalaysia(input: Date | string | number): string {
  const date = toUTCDate(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: MALAYSIA_TZ,
  }).format(date);
}

/** Time only, Malaysia - for chat bubbles (e.g. 10:22 pm). */
export function formatTimeShortMalaysia(input: Date | number): string {
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: MALAYSIA_TZ,
  }).format(date);
}

/** e.g. Fri, 10 Apr - for chat day headers, Malaysia date. */
export function formatChatDayPillMalaysia(input: Date | number): string {
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: MALAYSIA_TZ,
  }).format(date);
}

/** YYYY-MM-DD in Malaysia, for grouping messages by day. */
export function getMalaysiaDateKey(input: Date | number): string {
  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: MALAYSIA_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

/**
 * Malaysia civil calendar YYYY-MM-DD for a promotion boundary from the API (no `Date` - avoids
 * local-timezone drift on save when paired with `<input type="date">`).
 */
export function malaysiaCivilYyyyMmDdFromApi(
  input: Date | string | number | null | undefined,
): string | null {
  if (input == null) return null;
  const date = promotionBoundaryUtcInstantFromApi(input as Date | string | number);
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MALAYSIA_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const y = parts.find((p) => p.type === 'year')?.value;
  const m = parts.find((p) => p.type === 'month')?.value;
  const d = parts.find((p) => p.type === 'day')?.value;
  if (!y || !m || !d) return null;
  return `${y}-${m}-${d}`;
}

/** Today's date in Malaysia as YYYY-MM-DD (for form defaults). */
export function todayMalaysiaYyyyMmDd(): string {
  return malaysiaCivilYyyyMmDdFromApi(Date.now()) ?? '';
}

/**
 * Calendar day in Malaysia as a local `Date` at midnight (legacy). Prefer
 * {@link malaysiaCivilYyyyMmDdFromApi} for forms that submit YYYY-MM-DD strings.
 */
export function malaysiaCalendarDateFromApi(
  input: Date | string | number | null | undefined,
): Date | null {
  const s = malaysiaCivilYyyyMmDdFromApi(input);
  if (!s) return null;
  const [y, mo, d] = s.split('-').map((x) => Number(x));
  if (!y || !mo || !d) return null;
  return new Date(y, mo - 1, d);
}

/**
 * Local calendar date as YYYY-MM-DD for JSON APIs that interpret promotion dates as
 * civil days (server applies Asia/Kuala_Lumpur midnight). Avoids Date JSON.stringify → UTC shift.
 */
export function formatLocalDateToYyyyMmDd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * Serialize promotion start/end for PUT/POST as YYYY-MM-DD (Malaysia civil), including if the value
 * is an ISO string from a stale client cache.
 */
export function promotionFormDateToApiYyyyMmDd(value: Date | string | undefined): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value === 'string') {
    const t = value.trim();
    if (PROMOTION_CIVIL_YMD.test(t)) return t;
    return malaysiaCivilYyyyMmDdFromApi(t) ?? t;
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return malaysiaCivilYyyyMmDdFromApi(value) ?? formatLocalDateToYyyyMmDd(value);
  }
  return undefined;
}

/**
 * Format a UTC datetime (from API/DB) as date and time in Malaysia timezone.
 * Pass naive UTC strings from the backend; they are parsed as UTC then displayed in Malaysia.
 */
export function formatDateTimeInMalaysia(input: Date | string | number): string {
  const date = toUTCDate(input);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: MALAYSIA_TZ,
  }).format(date);
}

export function formatDateTime(input: Date | string | number): string {
  // Always use parseNaiveDateTimeAsLocal to handle naive and UTC dates correctly
  const date = typeof input === 'string'
    ? parseNaiveDateTimeAsLocal(input)
    : input instanceof Date
      ? input
      : new Date(input);
  const day = padTwo(date.getDate());
  const month = padTwo(date.getMonth() + 1);
  const year = date.getFullYear();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const hour12 = hours % 12 || 12;
  const time = `${hour12}:${padTwo(minutes)} ${ampm}`;
  return `${day}/${month}/${year}, ${time}`;
}

/** Display approximations (not calendar months). */
const SEC_PER_DAY = 86400;
const SEC_PER_MONTH = 30 * SEC_PER_DAY;
const SEC_PER_YEAR = 365 * SEC_PER_DAY;

function pluralUnit(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * Under 24h: hours / minutes / seconds only (e.g. 23h stays 23h).
 * 24h+: years (365d), months (30d), days, then h / m / s.
 */
function formatDurationFromTotalSeconds(
  totalSeconds: number,
  mode: 'compact' | 'withSeconds',
): string {
  if (totalSeconds < SEC_PER_DAY) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const parts: string[] = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (mode === 'withSeconds') {
      parts.push(`${seconds}s`);
    } else if (seconds > 0 || parts.length === 0) {
      parts.push(`${seconds}s`);
    }
    return parts.join(' ');
  }

  let r = totalSeconds;
  const years = Math.floor(r / SEC_PER_YEAR);
  r %= SEC_PER_YEAR;
  const months = Math.floor(r / SEC_PER_MONTH);
  r %= SEC_PER_MONTH;
  const days = Math.floor(r / SEC_PER_DAY);
  r %= SEC_PER_DAY;
  const h = Math.floor(r / 3600);
  r %= 3600;
  const m = Math.floor(r / 60);
  const s = r % 60;

  const parts: string[] = [];
  if (years > 0) parts.push(pluralUnit(years, 'year', 'years'));
  if (months > 0) parts.push(pluralUnit(months, 'month', 'months'));
  if (days > 0) parts.push(pluralUnit(days, 'day', 'days'));

  if (mode === 'withSeconds') {
    parts.push(`${h}h`, `${m}m`, `${s}s`);
    return parts.join(' ');
  }

  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0 || parts.length === 0) parts.push(`${s}s`);

  return parts.join(' ');
}

/**
 * Format a duration in milliseconds to a human-readable string with hours, minutes, and seconds
 * @param milliseconds - Duration in milliseconds (can be negative for overdue times)
 * @returns Under 24h: "2h 30m 15s". 24h+: "14 days 22h 47m 21s". Overdue: leading "-".
 */
export function formatDuration(milliseconds: number): string {
  const isNegative = milliseconds < 0;
  const totalSeconds = Math.floor(Math.abs(milliseconds) / 1000);
  const formatted = formatDurationFromTotalSeconds(totalSeconds, 'compact');
  return isNegative ? `-${formatted}` : formatted;
}

/**
 * Format a duration in milliseconds; always includes seconds under 24h ("1h 2m 0s").
 * For 24h+, includes h/m/s after days (e.g. "1 day 1h 0m 0s").
 */
export function formatDurationWithSeconds(milliseconds: number): string {
  const isNegative = milliseconds < 0;
  const totalSeconds = Math.floor(Math.abs(milliseconds) / 1000);
  const formatted = formatDurationFromTotalSeconds(totalSeconds, 'withSeconds');
  return isNegative ? `-${formatted}` : formatted;
}
