/* -------------------------------------------------------------------------------------
 * reportService - PLAN-reporting-foundation, slice S1 (Phase 1, mocked).
 *
 * One service for EVERY report. The report key is a parameter, never a code path: the
 * sponsorship report is report #1 and report #2 must reach this file unchanged.
 *
 * ===================================================================================
 * API CONTRACT (backend lands in S2; every function below is a one-line swap)
 * ===================================================================================
 *
 * All routes are mounted under `require_module_enabled_with_api_key("procurement")`
 * and gated on the report's own permission slug (sponsorship:
 * `procurement.sponsorship_forms.report`). Publishing a view additionally needs
 * `reports.views.publish`.
 *
 *   GET  /api/v1/reports
 *        -> { "reports": [{ "key", "title", "permission" }] }   catalog, permission-filtered
 *
 *   GET  /api/v1/reports/{key}
 *        -> ReportMeta (below). 403 without the permission, 404 for an unknown key.
 *
 *   POST /api/v1/reports/{key}/run
 *        body { "params": ReportParamValues, "view": ReportViewConfig | null }
 *        -> ReportResult (below)
 *        `view` is the view as it stands on screen, saved or not, so an unsaved change
 *        runs without being saved first. null = the report default view.
 *        `view.detail.columns` empty means THE WHOLE CATALOG. The screen always asks for
 *        the whole catalog and hides client-side, so ticking a column is instant and a
 *        hidden column is still offerable in the Columns panel (AC-B7). The export asks
 *        for exactly the visible columns in the visible order (AC-C5), which is where
 *        "requested columns in the requested order" (AC-A5) is exercised.
 *        422 { "message": "...", "code": "REPORT_CAPPED", "capped": true } when the sync
 *            caps (5,000 detail rows / 5,000 pivot cells) are exceeded. The export path
 *            has no cap, so the message tells the user to export instead. The envelope is
 *            FLAT because that is what the backend's AppException handler serialises
 *            (app/main.py) - `extractApiError` already reads `message`.
 *        422 { "message": "Unknown param 'foo'", "code": "REPORT_INVALID_PARAMS" } for an
 *            unknown param, an unknown date basis or an unknown column.
 *
 *   POST /api/v1/reports/{key}/export
 *        body { "params": ReportParamValues, "view": ReportViewConfig | null }
 *        -> { "download_id": "<uuid>", "filename": "Sponsorship report-2026.xlsx" }
 *        Creates a `downloads` row (kind `report_xlsx`) and enqueues the render on the
 *        `imports` queue. The file surfaces through the existing My Downloads drawer,
 *        so there is no new download plumbing.
 *
 *   GET    /api/v1/reports/{key}/views          -> { "mine": ReportView[], "shared": ReportView[] }
 *   POST   /api/v1/reports/{key}/views          body { "name", "view": ReportViewConfig } -> ReportView
 *   PUT    /api/v1/reports/{key}/views/{id}     body { "name"?, "view"? }                 -> ReportView
 *   DELETE /api/v1/reports/{key}/views/{id}     -> 204
 *   POST   /api/v1/reports/{key}/views/{id}/publish     body { "is_shared": bool }  -> ReportView
 *   POST   /api/v1/reports/{key}/views/{id}/set-default                             -> ReportView
 *
 *   `mine` = the views the caller OWNS, published ones included (the menu badges those);
 *   `shared` = OTHER users' published views. A personal view is visible to its owner only;
 *   a published one to anyone holding the report permission. At most one `is_default` per
 *   report key, enforced by a partial unique index.
 *
 * --- Money -------------------------------------------------------------------------
 *
 * Every measure travels as a DECIMAL STRING with two places ("1166830.70"), or is
 * ABSENT when the report has no value for it. Absent is not zero: a sponsorship form
 * with no lines has no sample price, and the workbook prints "-" there. The frontend
 * never adds two numbers together - every total in this contract is computed by the
 * engine, so the screen and the exported workbook cannot disagree.
 *
 * --- Deviation from the review artifact ---------------------------------------------
 *
 * `.lavish/reporting-foundation.html` shows `col_dim.values` as bare strings
 * ("2026-01"). The screen needs "Jan'26" in the header and must not invent a
 * formatting rule per dimension, so the contract carries an OPTIONAL
 * `col_dim.value_labels` map supplied by the engine; the frontend falls back to the
 * raw value when it is absent. Recorded in PLAN-reporting-foundation.md.
 *
 * ===================================================================================
 * PHASE 1 STATUS - THIS FILE SERVES A MOCK. DEBT until S2 swaps it. (DoD gate item 1)
 * ===================================================================================
 *
 * Every function below returns fixture data from
 * `@/components/reports/__mocks__/sponsorshipReport.fixtures`. The filters really do
 * filter and the totals really are recomputed there, so the states on screen are the
 * states the engine will produce. Two states cannot be reached by filtering; they are
 * forced with a `?mock=` query parameter that goes away with the mock:
 *
 *   ?mock=error    the run fails
 *   ?mock=capped   the run answers 422 capped
 *   ?mock=loading  the run never resolves
 *   ?mock=nopublish   meta reports `can_publish: false`
 * ----------------------------------------------------------------------------------- */

import {
  MOCK_SCENARIO_KEYS,
  mockExportReport,
  mockReportMeta,
  mockReportViewMutation,
  mockReportViews,
  mockRunReport,
  type MockScenario,
} from '@/components/reports/__mocks__/sponsorshipReport.fixtures';

/** A column as the dataset catalog describes it, and as a layout returns it. */
export type ReportColumnType = 'text' | 'money' | 'integer' | 'date' | 'bool';
export type ReportColumnTag = 'dimension' | 'measure' | 'date' | 'text';

export interface ReportColumn {
  key: string;
  label: string;
  type: ReportColumnType;
  /** Suggested DataGrid width; the user's saved sizing wins once they resize it. */
  size?: number;
}

export interface ReportCatalogColumn extends ReportColumn {
  tag: ReportColumnTag;
}

/**
 * A merged header cell over a run of detail columns (Expected year of delivery).
 *
 * `source` is the catalog dimension the group was derived from. A saved view names the
 * SOURCE among its detail columns, because the member keys are data-dependent (one tick
 * column per year present in the result) and a view written in 2026 must still mean
 * "show the delivery years" in 2027.
 */
export interface ReportColumnGroup {
  label: string;
  source: string;
  keys: string[];
}

export type ReportRow = Record<string, string | number | boolean | null>;

export interface ReportDetailLayout {
  key: string;
  title: string;
  columns: ReportColumn[];
  column_groups: ReportColumnGroup[];
  rows: ReportRow[];
  /** measure key -> decimal string. A measure with nothing to total is absent. */
  totals: Record<string, string>;
}

export interface ReportPivotDimension {
  key: string;
  label: string;
}

export interface ReportPivotColumnDimension extends ReportPivotDimension {
  /** Ordered naturally (months chronological). */
  values: string[];
  /** Optional display label per value; falls back to the raw value. */
  value_labels?: Record<string, string>;
}

/** row value -> column value -> measure key -> decimal string. Sparse: a missing cell is absent. */
export type ReportPivotCells = Record<string, Record<string, Record<string, string>>>;

export interface ReportPivotLayout {
  key: string;
  title: string;
  row_dim: ReportPivotDimension;
  col_dim: ReportPivotColumnDimension;
  measures: ReportColumn[];
  /** Ordered row values, so the screen does not have to sort a dimension it cannot rank. */
  row_values: string[];
  cells: ReportPivotCells;
  row_totals: Record<string, Record<string, string>>;
  col_totals: Record<string, Record<string, string>>;
  grand_total: Record<string, string>;
}

export interface ReportResult {
  key: string;
  period_label: string;
  row_count: number;
  capped: boolean;
  layouts: {
    detail: ReportDetailLayout;
    summary: ReportPivotLayout;
  };
}

export type ReportPeriod =
  | { kind: 'year'; year: number }
  | { kind: 'month_range'; year: number; from_month: number; to_month: number }
  | { kind: 'custom'; from: string; to: string };

export type ReportParamValue = string | string[] | ReportPeriod;
export type ReportParamValues = Record<string, ReportParamValue>;

export interface ReportSelectOption {
  value: string;
  label: string;
}

export type ReportParamMeta =
  | {
      kind: 'date_basis';
      key: string;
      label: string;
      default: string;
      options: ReportSelectOption[];
    }
  | {
      kind: 'period';
      key: string;
      label: string;
      default: ReportPeriod;
      /** Years the dataset actually holds rows for, newest first. */
      years: number[];
    }
  | {
      kind: 'select';
      key: string;
      label: string;
      multi: boolean;
      clearable: boolean;
      default: string[];
      options: ReportSelectOption[];
    };

export interface ReportViewConfig {
  params: ReportParamValues;
  detail: { columns: string[]; order: string[] };
  pivot: { rows: string; cols: string; measures: string[] };
}

export interface ReportView {
  id: string;
  name: string;
  is_shared: boolean;
  is_default: boolean;
  /** Display name of the owner, never the user id (no UUID reaches the UI). */
  owner_name: string | null;
  view: ReportViewConfig;
}

export interface ReportViews {
  mine: ReportView[];
  shared: ReportView[];
}

export interface ReportMeta {
  key: string;
  title: string;
  permission: string;
  params: ReportParamMeta[];
  catalog: ReportCatalogColumn[];
  default_view: ReportViewConfig;
  /** True when the caller holds `reports.views.publish`. Publish + Set as default are
   *  ABSENT without it, never disabled. */
  can_publish: boolean;
}

export interface ReportExportResult {
  download_id: string;
  filename: string;
}

/**
 * The sync caps are a real answer, not a failure: the run is refused and the user is
 * pointed at the uncapped export. Thrown so a hook can tell it apart from a 500.
 */
export class ReportCappedError extends Error {
  readonly capped = true;
  constructor(message: string) {
    super(message);
    this.name = 'ReportCappedError';
  }
}

/** react-query keys, declared here so the hooks and any invalidator agree. */
export const REPORT_META_KEY = 'report-meta';
export const REPORT_RUN_KEY = 'report-run';
export const REPORT_VIEWS_KEY = 'report-views';

/**
 * The listing key the detail DataGrid persists show / hide / order under (AC-C1).
 * Permission-slug scoped like every other listing key, e.g.
 * `procurement.sponsorship_forms.report::detail`.
 */
export function reportLayoutListingKey(permission: string, layoutKey: string): string {
  return `${permission}::${layoutKey}`;
}

/** Phase 1 only: which forced state the URL asks for. Removed with the mock. */
export function readMockScenario(search: string): MockScenario | null {
  const value = new URLSearchParams(search).get('mock');
  return value && (MOCK_SCENARIO_KEYS as readonly string[]).includes(value)
    ? (value as MockScenario)
    : null;
}

export async function fetchReportMeta(
  key: string,
  scenario: MockScenario | null = null,
): Promise<ReportMeta> {
  return mockReportMeta(key, scenario);
}

export async function runReport(
  key: string,
  params: ReportParamValues,
  view: ReportViewConfig,
  scenario: MockScenario | null = null,
): Promise<ReportResult> {
  try {
    return await mockRunReport(key, params, view, scenario);
  } catch (error) {
    // S2 reads this off the 422 body (`detail.capped`); the mock flags it by name.
    if (error instanceof Error && error.name === 'ReportCappedError') {
      throw new ReportCappedError(error.message);
    }
    throw error;
  }
}

export async function fetchReportViews(key: string): Promise<ReportViews> {
  return mockReportViews(key);
}

export async function createReportView(
  key: string,
  body: { name: string; view: ReportViewConfig },
): Promise<ReportView> {
  return mockReportViewMutation(key, { action: 'create', ...body });
}

export async function deleteReportView(key: string, id: string): Promise<void> {
  await mockReportViewMutation(key, { action: 'delete', id });
}

export async function publishReportView(
  key: string,
  id: string,
  isShared: boolean,
): Promise<ReportView> {
  return mockReportViewMutation(key, { action: 'publish', id, is_shared: isShared });
}

export async function setDefaultReportView(key: string, id: string): Promise<ReportView> {
  return mockReportViewMutation(key, { action: 'set-default', id });
}

export async function exportReport(
  key: string,
  params: ReportParamValues,
  view: ReportViewConfig,
): Promise<ReportExportResult> {
  return mockExportReport(key, params, view);
}
