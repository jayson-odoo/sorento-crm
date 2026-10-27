/**
 * How an audit row's before/after values read on a record's Audit Trail.
 *
 * Bookkeeping columns are stamped by the system on every save, so a change to one tells the
 * reader nothing. One list, so every trail skips the same ones.
 */
export const AUDIT_BOOKKEEPING_FIELDS: ReadonlySet<string> = new Set([
  'id',
  'created_at',
  'updated_at',
  'created_by',
  'updated_by',
  'last_responded_at',
  'portal_draft_at',
  'company_id',
]);

/** Text longer than this (or spanning lines) is shown as a collapsible before/after. */
export const AUDIT_LONG_TEXT = 120;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuidValue(v: unknown): boolean {
  return typeof v === 'string' && UUID_RE.test(v);
}

/** `defect_description` -> "Defect description", `root_cause_id` -> "Root cause". */
export function auditFieldLabel(key: string): string {
  const words = key.replace(/_id$/, '').replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatAuditValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '(empty)';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v) && v.every((x) => typeof x !== 'object' || x === null)) {
    return v.length ? v.map((x) => formatAuditValue(x)).join(', ') : '(empty)';
  }
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  // An empty value is the same "nothing" whichever way it is spelled.
  const empty = (x: unknown) => x === null || x === undefined || x === '';
  if (empty(a) && empty(b)) return true;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

export type AuditFieldChange =
  | { kind: 'line'; key: string; text: string }
  | { kind: 'long'; key: string; label: string; before: string; after: string };

/** Every real field change on an UPDATE, bookkeeping skipped, in the row's key order. */
export function auditFieldChanges(
  oldValues: Record<string, unknown> | null,
  newValues: Record<string, unknown> | null,
): AuditFieldChange[] {
  const oldV = oldValues || {};
  const newV = newValues || {};
  const keys = [...new Set([...Object.keys(newV), ...Object.keys(oldV)])];
  const out: AuditFieldChange[] = [];
  for (const key of keys) {
    if (AUDIT_BOOKKEEPING_FIELDS.has(key)) continue;
    const ov = oldV[key];
    const nv = newV[key];
    if (sameValue(ov, nv)) continue;
    const label = auditFieldLabel(key);
    // No ids on screen: a link that moved reads as "changed".
    if (isUuidValue(ov) || isUuidValue(nv)) {
      out.push({ kind: 'line', key, text: `${label} changed` });
      continue;
    }
    const before = formatAuditValue(ov);
    const after = formatAuditValue(nv);
    const long = (s: string) => s.length > AUDIT_LONG_TEXT || s.includes('\n');
    if (long(before) || long(after)) {
      out.push({ kind: 'long', key, label, before, after });
    } else {
      out.push({ kind: 'line', key, text: `${label}: ${before} → ${after}` });
    }
  }
  return out;
}
