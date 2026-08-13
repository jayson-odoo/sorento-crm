/**
 * The AutoCount reorder level + reorder quantity listing.
 *
 * > "the reorder level and reorder quantity ... are set at autocount, and they need to
 * >  upload to our system"
 *
 * AutoCount owns the level; we receive it. Columns are resolved through the alias table
 * server-side, so a differently-spelled real export is alias rows, not code.
 *
 * Contract (S13c): POST /api/v1/scm/reorder-levels/import/{preview|apply}, multipart file.
 * Both return the same resolution - created / updated / unchanged / conflicts - so the
 * Test button and Confirm cannot disagree about the same file. `conflict_rows` are levels
 * a person set by hand that the file disagrees with: reported, never overwritten.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface LevelImportConflict {
  item_code: string;
  location: string | null;
  held_level: number;
  file_level: number;
  held_source: string | null;
}

export interface LevelImportOutcome {
  readable: boolean;
  missing_columns: string[];
  unmapped_headers: string[];
  problems: { row: number; reason: string }[];
  total_rows: number;
  created: number;
  updated: number;
  unchanged: number;
  conflicts: number;
  conflict_rows: LevelImportConflict[];
  sample: {
    item_code: string;
    location: string | null;
    reorder_level: number;
    reorder_qty: number | null;
  }[];
  /** `useTwoStepUpload` gates Confirm on this. */
  ok: boolean;
}

function withOk(body: Omit<LevelImportOutcome, 'ok'>): LevelImportOutcome {
  return { ...body, ok: body.readable };
}

async function post(path: string, file: File, fallback: string): Promise<LevelImportOutcome> {
  const body = new FormData();
  body.append('file', file);
  const res = await apiFetch(path, { method: 'POST', body });
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return withOk((await res.json()) as Omit<LevelImportOutcome, 'ok'>);
}

/** What the file WOULD do. Writes nothing. */
export function previewLevelImport(file: File): Promise<LevelImportOutcome> {
  return post('/api/v1/scm/reorder-levels/import/preview', file, 'Failed to read the file');
}

export function applyLevelImport(file: File): Promise<LevelImportOutcome> {
  return post('/api/v1/scm/reorder-levels/import/apply', file, 'Failed to apply the file');
}
