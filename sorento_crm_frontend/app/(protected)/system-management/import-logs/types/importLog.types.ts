export interface ImportLog {
  id: string;
  import_session_id: string;
  entity_type: string;
  entity_table: string;
  filename?: string | null;
  import_type: string;
  total_rows: number;
  successful_rows: number;
  created_rows: number;
  updated_rows: number;
  failed_rows: number;
  skipped_rows: number;
  warnings?: any;
  errors?: any;
  summary?: any;
  imported_by?: string | null;
  imported_at: Date;
  created_at?: Date;
  duration_ms?: number | null;
}
