/** One outcome bucket in a job's breakdown. `count` is exact and complete - never truncated. */
export interface ImportOutcomeBreakdownEntry {
  code: string;
  label: string;
  count: number;
  /** Up to 10 distinct offending values (missing product codes, doc numbers, filenames…). */
  top_values?: { value: string; count: number }[];
}

export interface ImportOutcomeBreakdown {
  successful: ImportOutcomeBreakdownEntry[];
  skipped: ImportOutcomeBreakdownEntry[];
  failed: ImportOutcomeBreakdownEntry[];
}

/**
 * The uniform envelope every importer writes into `import_jobs.result`.
 * Legacy jobs predate it - treat every field as optional and fall back to the raw JSON view.
 */
export interface ImportJobResultEnvelope {
  message?: string;
  counts?: {
    total: number;
    processed: number;
    successful: number;
    failed: number;
    skipped: number;
  };
  breakdown?: ImportOutcomeBreakdown;
  /** True when per-row capture hit its cap; counts/breakdown stay exact regardless. */
  rows_truncated?: boolean;
  /** How many per-row records were actually captured. */
  rows_total?: number;
  [key: string]: unknown;
}

export type ImportRowOutcome = 'created' | 'updated' | 'unchanged' | 'skipped' | 'failed';

/** One captured source row. */
export interface ImportJobRow {
  id: string;
  row_number?: number | null;
  outcome: ImportRowOutcome;
  code: string;
  label?: string | null;
  message?: string | null;
  /** The offending token, when the reason has one (product code, doc no, filename). */
  value?: string | null;
  /** The row's mapped business columns - never raw UUIDs. */
  identity?: Record<string, unknown> | null;
  entity_type?: string | null;
  entity_id?: string | null;
}

export interface ImportJobRowsQuery {
  pageIndex: number;
  pageSize: number;
  outcome?: string;
  code?: string;
  query?: string;
}

export interface ImportJob {
  id: string;
  job_id: string;
  job_type: string;
  status: 'pending' | 'queued' | 'started' | 'finished' | 'failed' | 'cancelled';
  user_id: string;
  filename?: string | null;
  total_rows: number;
  processed_rows: number;
  successful_rows: number;
  failed_rows: number;
  skipped_rows: number;
  result?: ImportJobResultEnvelope | null;
  error?: string | null;
  created_at: Date;
  started_at?: Date | null;
  completed_at?: Date | null;
  updated_at?: Date | null;
  job_metadata?: any;
  // Retained original upload (tracing). Raw storage key is never exposed; download
  // via getImportJobSourceUrl which returns a fresh signed URL.
  source_filename?: string | null;
  source_file_size?: number | null;
  has_source_file?: boolean;
}
