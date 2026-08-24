/**
 * Date helpers for the Upload Activity drawer.
 *
 * The backend serialises datetimes with `datetime.utcnow()` - they're UTC but
 * Pydantic v2 emits them without a tz suffix (`2026-06-02T10:05:48.123`). The
 * browser's `new Date()` then interprets the bare string as **local time**,
 * which shows "8 hr ago" for an upload that just happened in UTC+8.
 *
 * `parseServerDate` appends `Z` whenever no offset or `Z` is present, so the
 * resulting Date object is anchored to UTC. Centralising this means we never
 * accidentally double-correct.
 */

const TZ_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/;

export function parseServerDate(input: string | Date): Date {
  if (input instanceof Date) return input;
  const s = String(input);
  return TZ_SUFFIX_RE.test(s) ? new Date(s) : new Date(`${s}Z`);
}

export function timeAgo(iso: string | Date): string {
  const diff = Date.now() - parseServerDate(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} day${d > 1 ? 's' : ''} ago`;
  return parseServerDate(iso).toLocaleDateString();
}
