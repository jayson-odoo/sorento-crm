/**
 * Project import (PLAN-project-import-12nov.md, "Frontend contract"): the shapes the routes in
 * `sorento_crm_backend/app/api/v1/projects/project_import.py` answer with.
 */

export type ProjectImportStatus = 'draft' | 'previewed' | 'importing' | 'imported' | 'reverted';

export type ProjectImportKind = 'customer' | 'project' | 'developer' | 'person';

export type ProjectImportAction = 'link' | 'create' | 'skip' | 'none';

export type ProjectImportOutcome =
  | 'created'
  | 'updated'
  | 'unchanged'
  | 'skipped'
  | 'needs_review'
  | 'error';

export type ProjectImportCounts = Partial<Record<ProjectImportOutcome, number>>;

export interface ProjectImportSheetColumn {
  position: number;
  header: string;
  sample: string | null;
  field: string | null;
}

export interface ProjectImportSheet {
  name: string;
  name_trimmed: string;
  has_ps_heading: boolean;
  row_count: number;
  columns: ProjectImportSheetColumn[];
  ticked?: boolean;
}

export interface ProjectImportRunRow {
  id: string;
  run_no: string;
  filename: string | null;
  status: ProjectImportStatus;
  job_status?: string;
  uploaded_by: string | null;
  uploaded_by_id?: string;
  uploaded_at: string | null;
  rows: number;
  created: number;
  skipped: number;
  to_review: number;
  imported_at: string | null;
}

export interface ProjectImportRun extends ProjectImportRunRow {
  sheets: ProjectImportSheet[];
  columns: Record<string, string>;
  missing_columns: string[];
  preview_counts: ProjectImportCounts | null;
  preview_codes?: Record<string, number> | null;
  result_counts?: ProjectImportCounts | null;
  result_codes?: Record<string, number> | null;
  sheet_errors?: { sheet: string; code: string; heading: string }[];
  revert_result?: {
    removed: Record<string, number>;
    kept: { entity_type: string; label: string; reason: string }[];
  } | null;
  reverted_at?: string | null;
  /** The import's outcome envelope (counts, codes and the shared breakdown), once imported. */
  result?: Record<string, unknown> | null;
}

export interface ProjectImportLine {
  kind: ProjectImportKind;
  customer_value_key: string;
  value_key: string;
  value_text: string | null;
  customer_text: string | null;
  rows: number;
  action: ProjectImportAction | null;
  target_id: string | null;
  target_label: string | null;
  new_title: string | null;
  source: 'saved' | 'so' | null;
  set_by_name: string | null;
  set_at: string | null;
  status: 'todo' | 'set';
}

export type ProjectImportLinesSummary = Record<ProjectImportKind, { total: number; todo: number }>;

export interface ProjectImportLineBody {
  kind: ProjectImportKind | string;
  customer_value_key?: string;
  value_key: string;
  action: ProjectImportAction | string;
  target_id?: string | null;
  new_title?: string | null;
}

export interface ProjectImportBulkBody {
  kind: ProjectImportKind | string;
  keys: [string, string][];
  action: ProjectImportAction | string;
  target_id?: string | null;
  new_title?: string | null;
}

export interface ProjectImportReportRow {
  sheet: string;
  row_number: number;
  ps_number: string;
  customer: string | null;
  project: string | null;
  po_number: string | null;
  po_date: string | null;
  outcome: ProjectImportOutcome;
  codes: string[];
  message: string | null;
}

export interface ProjectImportPreviewResult {
  counts: ProjectImportCounts;
  codes: Record<string, number>;
  sheet_errors: { sheet: string; code: string; heading: string }[];
}

export interface Paged<T> {
  data: T[];
  total: number;
}

export interface PagedItems<T> {
  items: T[];
  total: number;
}
