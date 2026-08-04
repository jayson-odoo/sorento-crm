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
 *  2) Apply - writes it, returns the applied counts
 *     POST /api/v1/scm/outstanding/{kind}/apply
 *     same multipart body (the same file the preview was taken from)
 *     -> 200 OutstandingApplyResult
 *     -> 400 when the file is unusable (missing required columns)
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
}

/** What the write actually did, which is not the same shape as the diff. */
export interface OutstandingAppliedCounts {
  added: number;
  updated: number;
  closed: number;
  unchanged: number;
}

export interface OutstandingApplyResult {
  ok: boolean;
  counts: OutstandingCounts;
  applied: OutstandingAppliedCounts;
  scope_documents: string[];
  resolution_issues: OutstandingResolutionIssue[];
  row_problems: OutstandingRowProblem[];
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

/** Write the upload. Send the SAME file the preview was taken from. */
export async function applyOutstandingImport(
  kind: OutstandingImportKind,
  file: File,
): Promise<OutstandingApplyResult> {
  const res = await apiFetch(`/api/v1/scm/outstanding/${kind}/apply`, {
    method: 'POST',
    body: fileBody(file),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to apply the upload'));
  return (await res.json()) as OutstandingApplyResult;
}
