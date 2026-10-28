import { parseDateTimeAsUTC } from './helpers';
import { isAwaitingReview } from './submission-status';

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

const STATUS_KEYS = ['status', 'approval_status', 'order_status'];
// The review stage each form's submit lands on (lib/submission-status.ts); a move from
// rejected into one of them is a resubmission, whenever it was written.
const REVIEW_STAGES = new Set(['pending_project_sales', 'pending', 'pending_approval']);
// Status-engine records carry the labels only in the summary: "Status: Rejected → Submitted".
const SUMMARY_RESUBMIT = /\brejected\s*→\s*(re)?submitted\b/i;
const SUMMARY_REJECT = /→\s*rejected\s*$/i;
// "Status: Draft → Submitted" / "Status changed to Submitted": the label the record moved to.
const SUMMARY_STATUS_TO = /^Status(?::.*→|\s+changed to)\s*(.+)$/;
// The customer's own side: a save by one of them while the record is rejected answers the
// rejection (the chatbot's edit-via-submit kept the status `rejected` before RESUBMITTED-STATUS).
// History only: since RESUBMITTED-STATUS went live (28 Oct 2026 03:40 MYT) every resubmit moves
// the status, and a later integration save on a rejected record (an n8n edit) is not one.
const CUSTOMER_ACTORS = new Set(['contact', 'integration', 'public_link']);
const RESUBMITTED_STATUS_LIVE = Date.parse('2026-10-27T19:40:00Z');
const at = (changedAt: string) => parseDateTimeAsUTC(changedAt).getTime();

export type AuditTrailHeading = 'Resubmitted' | 'Rejected';

type TrailEntry = {
  id: string;
  action: string;
  changed_at: string;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  description: string | null;
  actor_type?: string | null;
  contact_id?: string | null;
};

const norm = (v: unknown) => (typeof v === 'string' ? v.trim().toLowerCase() : '');

function isReviewStage(key: string, status: string): boolean {
  if (isAwaitingReview(status) || REVIEW_STAGES.has(status)) return true;
  // A purchase request's resubmit clears its approval_status.
  return key === 'approval_status' && status === '';
}

/**
 * The heading of each of a record's own rows that rejected it or sent it back in, keyed by
 * row id. Walks the rows oldest first and carries the status each one left, so a row reads
 * right even when it does not carry the status it moved from, and history written before the
 * "Resubmitted" status existed reads the same as a resubmit written today. Pass the record's
 * own rows only: a child row's status is not the record's.
 */
export function auditTrailHeadings(entries: TrailEntry[]): Map<string, AuditTrailHeading> {
  const headings = new Map<string, AuditTrailHeading>();
  const current: Record<string, string> = {};
  // The API returns newest first; reversed before the sort so rows stamped the same instant
  // keep their written order.
  const oldestFirst = [...entries]
    .reverse()
    .sort((a, b) => at(a.changed_at) - at(b.changed_at));
  for (const entry of oldestFirst) {
    const oldV = entry.old_values || {};
    const newV = entry.new_values || {};
    if (entry.action !== 'UPDATE') {
      for (const key of STATUS_KEYS) {
        if (key in newV) current[key] = norm(newV[key]);
      }
      continue;
    }
    let heading: AuditTrailHeading | null = null;
    let moved = false;
    for (const key of STATUS_KEYS) {
      if (!(key in newV)) continue;
      const from = key in oldV ? norm(oldV[key]) : (current[key] ?? '');
      const to = norm(newV[key]);
      current[key] = to;
      if (from === to) continue;
      moved = true;
      if (to === 'rejected') heading = 'Rejected';
      else if (from === 'rejected' && isReviewStage(key, to)) heading ??= 'Resubmitted';
    }
    const summary = entry.description?.trim() ?? '';
    const engineTo = moved ? null : SUMMARY_STATUS_TO.exec(summary);
    if (engineTo) {
      moved = true;
      current.status_id = norm(engineTo[1]);
      if (SUMMARY_RESUBMIT.test(summary)) heading = 'Resubmitted';
      else if (SUMMARY_REJECT.test(summary)) heading = 'Rejected';
    }
    if (
      !moved &&
      !heading &&
      Object.values(current).includes('rejected') &&
      at(entry.changed_at) < RESUBMITTED_STATUS_LIVE &&
      // Rows written before the actor columns read `legacy`: a contact id names the customer.
      (CUSTOMER_ACTORS.has(entry.actor_type ?? '') ||
        ((entry.actor_type ?? 'legacy') === 'legacy' && !!entry.contact_id)) &&
      auditFieldChanges(oldV, newV).length > 0
    ) {
      heading = 'Resubmitted';
    }
    if (heading) headings.set(entry.id, heading);
  }
  return headings;
}

/**
 * A past resubmit's summary says "rejected → submitted": the status it is called today
 * (RESUBMITTED-STATUS) is what the reader sees. A named stage stays as recorded.
 */
export function resubmittedSummary(summary: string): string {
  return summary.replace(
    /\b(rejected\s*→\s*)(s)(ubmitted)\b/i,
    (_m, lead: string, s: string, rest: string) => `${lead}${s === 'S' ? 'Res' : 'res'}${rest}`,
  );
}
