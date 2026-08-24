/** API returns times like "09:00:00" - normalize for <input type="time" /> (HH:MM). */
export function apiTimeToInputValue(value: string | undefined, fallback: string): string {
  if (!value || typeof value !== 'string') return fallback;
  const m = /^(\d{1,2}):(\d{2})/.exec(value.trim());
  if (!m) return fallback;
  return `${m[1].padStart(2, '0')}:${m[2]}`;
}

/** Send as full time for JSON body (FastAPI accepts HH:MM:SS). */
export function inputValueToApiTime(hhmm: string): string {
  const parts = hhmm.split(':');
  const h = (parts[0] ?? '0').padStart(2, '0');
  const m = (parts[1] ?? '0').padStart(2, '0');
  return `${h}:${m}:00`;
}
