import type { ExportSplit } from '@/components/common/export-split';

/**
 * `GET /api/v1/scm/order-summary/low-stock-view` (PLAN-excel-preview-26sep AC-1), field for
 * field `LowStockViewOut`. The workbook the user is about to download, built by the same
 * function that writes the file, so the page and the file cannot disagree.
 */

export type LowStockCell = string | number | null;

export interface LowStockViewSheet {
  title: string;
  /** The sheet's rows, in print order, as indexes into `LowStockView.rows`. */
  row_indexes: number[];
  /** A "Low stock" or "<key> - Low" sheet. */
  low: boolean;
}

/** One supplier or category choice over the WHOLE run, with its row and low counts. */
export interface LowStockFacet {
  key: string;
  rows: number;
  low: number;
}

export interface LowStockView {
  /** `run_id` is opaque: the export needs it, the screen never shows it. */
  run: { run_id: string; as_of: string | null };
  split: ExportSplit;
  columns: string[];
  rows: LowStockCell[][];
  sheets: LowStockViewSheet[];
  facets: { suppliers: LowStockFacet[]; categories: LowStockFacet[] };
  /** After the filters. */
  counts: { rows: number; low: number; sheets: number };
  /** Over `max_rows`: `rows` and `sheets` are empty, `counts` still say how many. */
  over_cap: boolean;
  max_rows: number;
  filename: string;
}

/** What the page asks for, and exactly what Download sends. */
export interface LowStockRequest {
  /** Omitted: the newest completed run. */
  runId?: string;
  split: ExportSplit;
  suppliers: string[];
  categories: string[];
}
