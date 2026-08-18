/**
 * ============================================================================
 * SCM - outstanding-orders upload channel, feature service
 * ============================================================================
 * Layering: OutstandingUploadDialog -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/outstanding_import.py) ────────────────
 *
 *  1) Preview - writes NOTHING, returns the diff the user confirms against
 *     POST /api/v1/scm/outstanding/{kind}/preview
 *     multipart body, single field named exactly "file"
 *     -> 200 OutstandingPreview
 *
 *     A file whose header cannot answer the question is a 200 carrying
 *     `ok: false` + `missing_columns`, NOT an error - the screen has to name
 *     the columns so the export can be fixed, and an error body would lose
 *     them. So a 200 always resolves here, whatever `ok` says.
 *
 *  2) Apply - QUEUES the write, returns the job to watch
 *     POST /api/v1/scm/outstanding/{kind}/apply
 *     same multipart body (the same file the preview was taken from)
 *     -> 202 { message, job_id, id }
 *     -> 400 when the session has no single active company: `sales_orders` /
 *        `purchase_orders` are owned tables, so "whose book is this?" has no
 *        answer, and the refusal happens before any job row exists
 *
 *     The counts are NOT in this response - the write happens on the worker.
 *     They land on the job (`/system-management/import-jobs/{job_id}`), under
 *     `result.upload`, alongside a per-row outcome for every source row. The
 *     upload drawer follows the job from `notifyImportQueued()`.
 *
 *     A file the reader cannot use is no longer a 400 either: reading happens on
 *     the worker, so an unusable file FAILS THE JOB with its reason on it. Test
 *     is what tells the operator that before they confirm.
 *
 *  kind = 'sales-orders' | 'purchase-orders'. Auth on both: `scm.reorder.run`.
 *
 * Two calls on purpose: nothing is ever written from a single click, because
 * the whole plan is computed from this data and a wrong file quietly imported
 * is a week of unpicking.
 *
 * SCM services call `apiFetch('/api/v1/scm/...')` with the version segment
 * spelled out (see reorderRunService) - `lib/api.ts` has no `/api/scm` rewrite
 * entry, so a short path would go to Next.js and 404.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';

/** Which order book the file carries. Maps 1:1 to the route's `{kind}` segment. */
export type OutstandingImportKind = 'sales-orders' | 'purchase-orders';

/** Every way a line can differ from what we already hold. `unchanged` included. */
export type OutstandingChangeKind =
  | 'added'
  | 'qty_changed'
  | 'date_moved'
  | 'date_and_qty_changed'
  | 'closed'
  | 'unchanged';

/** A row the reader could not turn into a line at all. */
export interface OutstandingRowProblem {
  row_number: number;
  reason: string;
  value: string;
}

/** A row that read fine but names a product / warehouse we do not hold. */
export interface OutstandingResolutionIssue {
  row_number: number;
  field: string;
  value: string;
  reason: string;
}

/** One real line per change kind, so the confirm screen shows evidence not just counts. */
export interface OutstandingSampleRow {
  doc_number: string;
  item_code: string;
  location: string;
  qty_before: number | null;
  qty_after: number | null;
  /** ISO date (YYYY-MM-DD) or null when the line has no after state (closed). */
  date_before: string | null;
  date_after: string | null;
  /** Positive = pushed out, negative = pulled in, null = not a date change. */
  days_moved: number | null;
  label: string | null;
}

/** Empty for a file the reader could not use, so every kind is optional. */
export type OutstandingCounts = Partial<Record<OutstandingChangeKind, number>>;

/** Only the kinds the backend had rows to show appear here. */
export type OutstandingSamples = Partial<Record<OutstandingChangeKind, OutstandingSampleRow[]>>;

/**
 * An agent code this file names that can classify nothing yet.
 *
 * Its own list, never merged into the rejected rows: the file is fine, the code resolved (or
 * was created by the upload), and no row is skipped. What it reports is a gap in MASTER data
 * only the client can close - which of his agent codes still need a demand class - and
 * putting that among the failures would make a clean file read as a broken one.
 */
export interface OutstandingAgentNotice {
  code: string;
  /** True when this upload is the first thing that has ever named the code. */
  is_new: boolean;
  reason: string;
}

/**
 * The planning-change batch this upload raised, when the diff changed a PLANNED line
 * (`PLAN-so-book-diff-replanning.md` AC-R01). `null` when nothing planned was touched - no
 * batch was born, and the upload card renders nothing.
 */
export interface OutstandingPlanningChangeBatch {
  id: string;
  order_count: number;
  line_count: number;
}

export interface OutstandingPreview {
  doc_type: string;
  /** false = the header is missing required columns; nothing can be applied. */
  ok: boolean;
  scope_documents: string[];
  counts: OutstandingCounts;
  total_rows: number;
  unmapped_headers: string[];
  missing_columns: string[];
  row_problems: OutstandingRowProblem[];
  resolution_issues: OutstandingResolutionIssue[];
  samples: OutstandingSamples;
  unmapped_agents: OutstandingAgentNotice[];
  /** Absent (not just `null`) on every Phase 1 response - Phase 2 wires the real preview. */
  planning_change_batch?: OutstandingPlanningChangeBatch | null;
}

/**
 * One multipart body for both steps. No `Content-Type` header is set: the
 * browser owns the multipart boundary and setting it by hand corrupts the body.
 */
function fileBody(file: File): FormData {
  const body = new FormData();
  body.append('file', file);
  return body;
}

/** What this file WOULD change. Writes nothing. */
export async function previewOutstandingImport(
  kind: OutstandingImportKind,
  file: File,
): Promise<OutstandingPreview> {
  const res = await apiFetch(`/api/v1/scm/outstanding/${kind}/preview`, {
    method: 'POST',
    body: fileBody(file),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to read the file'));
  return (await res.json()) as OutstandingPreview;
}

/**
 * Queue the upload. Send the SAME file the preview was taken from.
 *
 * Returns the job, not the result: what the upload did lands on the job page, and the drawer
 * follows it there.
 */
export async function applyOutstandingImport(
  kind: OutstandingImportKind,
  file: File,
): Promise<ImportQueuedResult> {
  const res = await apiFetch(`/api/v1/scm/outstanding/${kind}/apply`, {
    method: 'POST',
    body: fileBody(file),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to queue the upload'));
  return (await res.json()) as ImportQueuedResult;
}

/**
 * Which spreadsheet formats the server will accept (`SCM_UPLOAD_EXTENSIONS`).
 *
 * Asked for rather than hard-coded in the dialog: the accept list belongs to the server,
 * which is the thing that actually refuses a file. A second copy in the browser is how the
 * dialog came to reject a legacy `.xls` the reader parses perfectly well.
 */
export async function getOutstandingUploadConfig(): Promise<{ allowed_extensions: string[] }> {
  const res = await apiFetch('/api/v1/scm/outstanding/config');
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to read the upload settings'));
  }
  return (await res.json()) as { allowed_extensions: string[] };
}
