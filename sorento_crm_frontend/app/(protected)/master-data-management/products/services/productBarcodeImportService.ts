/**
 * BARCODE-IMPORT: set product barcodes from a sheet of product code + barcode.
 *
 * Contract: POST /api/v1/master-data/products/barcode-import/{preview|apply}, multipart file
 * (.xlsx or .csv). Both return the same per-row resolution, so Test and Apply cannot disagree
 * about a file; apply adds `applied` (how many products were written: New + Change only).
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type BarcodeRowStatus =
  | 'new'
  | 'change'
  | 'same'
  | 'unknown_code'
  | 'ambiguous_code'
  | 'repeated_code'
  | 'blank_barcode'
  | 'too_long'
  | 'scientific';

export type BarcodeRowWarning = 'duplicate' | 'not_ean13';

export interface BarcodeImportRow {
  row: number;
  product_code: string;
  product_name: string | null;
  old_barcode: string | null;
  new_barcode: string | null;
  status: BarcodeRowStatus;
  warnings: BarcodeRowWarning[];
  repeated_of_row: number | null;
  /** Codes of the other products sharing this barcode (in the file or already in the CRM). */
  duplicate_of: string[];
  /** The sheet's note for this row, when it has a note column. */
  note: string | null;
}

export interface BarcodeImportOutcome {
  readable: boolean;
  missing_columns: string[];
  code_column: string | null;
  barcode_column: string | null;
  note_column: string | null;
  /** Names of the companies in scope: what this file reads and writes. */
  companies: string[];
  total_rows: number;
  counts: Record<BarcodeRowStatus | BarcodeRowWarning, number>;
  rows: BarcodeImportRow[];
  applied?: number;
  /** Apply refuses the file without this, so a write always follows a Test of the same bytes. */
  preview_token: string;
}

export const BARCODE_IMPORT_ACCEPT = '.xlsx,.csv';

async function post(
  path: string,
  file: File,
  fallback: string,
  previewToken?: string,
): Promise<BarcodeImportOutcome> {
  const body = new FormData();
  body.append('file', file);
  if (previewToken) body.append('preview_token', previewToken);
  const res = await apiFetch(
    `/api/v1/master-data/products/barcode-import/${path}`,
    {
      method: 'POST',
      body,
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as BarcodeImportOutcome;
}

/** What the file WOULD do. Writes nothing. */
export function previewBarcodeImport(
  file: File,
): Promise<BarcodeImportOutcome> {
  return post('preview', file, 'Failed to read the file');
}

/** Needs the `preview_token` a Test of the same file returned; the server refuses without it. */
export function applyBarcodeImport(
  file: File,
  previewToken: string,
): Promise<BarcodeImportOutcome> {
  return post('apply', file, 'Failed to apply the file', previewToken);
}
