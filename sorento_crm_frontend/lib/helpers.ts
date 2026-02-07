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

/**
 * Format a duration in milliseconds to a human-readable string with hours, minutes, and seconds
 * @param milliseconds - Duration in milliseconds (can be negative for overdue times)
 * @returns Formatted string like "2h 30m 15s" or "-1h 5m 20s" for overdue
 */
export function formatDuration(milliseconds: number): string {
  const isNegative = milliseconds < 0;
  const absMs = Math.abs(milliseconds);
  
  const totalSeconds = Math.floor(absMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds}s`);
  
  const formatted = parts.join(' ');
  return isNegative ? `-${formatted}` : formatted;
}

/**
 * Format a duration in milliseconds to a string that always includes seconds (e.g. "1h 2m 0s", "2m 35s")
 */
export function formatDurationWithSeconds(milliseconds: number): string {
  const isNegative = milliseconds < 0;
  const absMs = Math.abs(milliseconds);
  const totalSeconds = Math.floor(absMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  parts.push(`${seconds}s`);
  const formatted = parts.join(' ');
  return isNegative ? `-${formatted}` : formatted;
}
