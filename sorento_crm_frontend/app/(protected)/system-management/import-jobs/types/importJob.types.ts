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
  result?: any;
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
