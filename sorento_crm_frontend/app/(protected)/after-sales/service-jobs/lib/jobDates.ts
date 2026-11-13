/** Date helpers for the job dialogs. Malaysian time is UTC+8 with no daylight saving. */
const MYT_OFFSET_MS = 8 * 60 * 60 * 1000;

export interface MytParts {
  date: Date; // a local Date carrying the Malaysian civil day
  time: string; // "h:mm am"
}

export function formatTimeAmPm(hour24: number, minute: number): string {
  const suffix = hour24 >= 12 ? 'pm' : 'am';
  const h = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${h}:${String(minute).padStart(2, '0')} ${suffix}`;
}

/** An ISO instant read as a Malaysian civil date and time. */
export function toMytParts(iso: string): MytParts | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const d = new Date(t + MYT_OFFSET_MS);
  return {
    date: new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()),
    time: formatTimeAmPm(d.getUTCHours(), d.getUTCMinutes()),
  };
}

/** "10:00 am", "2:30pm" or "14:30" to hours and minutes; null when it is not a time. */
export function parseTimeText(text: string): { hour: number; minute: number } | null {
  const m = /^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)?\s*$/i.exec(text);
  if (!m) return null;
  let hour = Number(m[1]);
  const minute = m[2] ? Number(m[2]) : 0;
  const suffix = m[3]?.toLowerCase();
  if (minute > 59) return null;
  if (suffix) {
    if (hour < 1 || hour > 12) return null;
    if (suffix === 'pm' && hour < 12) hour += 12;
    if (suffix === 'am' && hour === 12) hour = 0;
  } else if (hour > 23) {
    return null;
  }
  return { hour, minute };
}

/** A Malaysian civil date and time as an ISO instant with the +08:00 offset. */
export function mytIso(date: Date, hour: number, minute: number): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(hour)}:${p(minute)}:00+08:00`;
}

/** yyyy-mm-dd for a local Date's civil day (the board's `day` and the list's date range). */
export function ymd(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}
