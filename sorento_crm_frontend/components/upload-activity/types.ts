/**
 * Upload Activity drawer — shared types.
 *
 * These shapes mirror the Phase 2 backend contract defined in
 * `services/uploadActivityService.ts`. During Phase 1 (mocks only),
 * these are populated from `mocks.ts` and from the optimistic
 * `UploadManager` context.
 *
 * Source of truth doc: `docs/plans/PLAN-upload-activity-drawer.md` §4.3
 */

export type FileStatus =
  | 'uploading' // FE optimistic, POST in flight
  | 'processing' // POST done, n8n callback pending
  | 'linked' // n8n callback: linked to >=1 entity
  | 'unlinked' // n8n callback: no entity matched (terminal, may need manual link)
  | 'failed' // POST failed OR n8n returned failed OR sweeper timeout
  | 'post_failed'; // FE-only: POST itself never completed; user can retry from cached File blob

export type SessionStatus =
  | 'uploading'
  | 'processing'
  | 'linked'
  | 'partial'
  | 'failed';

export type SessionType = 'single' | 'multi' | 'bulk_zip' | 'import_job';

export interface LinkedEntity {
  entity_type: string; // "product" | "promotion" | "form" | "packing_list" | ...
  entity_id: string;
  display_name: string;
  matched_by: string; // "filename_token:CBMC5570" etc.
}

export interface UnlinkedReason {
  reason: string;
}

export interface UploadActivityFile {
  client_id: string; // FE-generated, stable across optimistic → reconciled
  attachment_id: string | null; // null while POST in flight
  filename: string;
  status: FileStatus;
  summary: string; // friendly one-liner
  linked: LinkedEntity[];
  unlinked_reasons: UnlinkedReason[];
  error_code: string | null;
  error_message: string | null;
  integration_log_id: string | null;
  last_updated_at: string; // ISO timestamp
  // Phase 1 only: cached File blob for retry on POST failure.
  // Phase 2 backend stripped from response. Optional via `_post_blob?` symbol.
  _post_blob?: File;
}

export interface SessionAggregate {
  total: number;
  uploading: number;
  processing: number;
  linked: number;
  unlinked: number;
  failed: number;
}

export interface UploadActivitySession {
  session_id: string; // upload_batch_id (multi/single) or import_job.job_id (bulk_zip / import_job)
  session_type: SessionType;
  title: string; // filename | "5 files" | "brand_2026.zip"
  started_at: string;
  finished_at: string | null;
  status: SessionStatus;
  aggregate: SessionAggregate;
  files: UploadActivityFile[];
  import_job_id: string | null; // bulk_zip + import_job
  needs_action: boolean; // any file in `failed` or `unlinked`
  // ---- import_job sessions only (Excel/data imports, no attachment rows).
  // Replaces the per-page LatestImportStatusPanel bar.
  job_type?: string | null;
  total_rows?: number | null;
  processed_rows?: number | null;
  successful_rows?: number | null;
  failed_rows?: number | null;
  skipped_rows?: number | null;
  job_error?: string | null;
}
