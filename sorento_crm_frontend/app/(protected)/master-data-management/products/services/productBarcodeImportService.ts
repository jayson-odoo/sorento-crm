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
  | 'too_long';

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
}

export interface BarcodeImportOutcome {
  readable: boolean;
  missing_columns: string[];
  code_column: string | null;
  barcode_column: string | null;
  total_rows: number;
  counts: Record<BarcodeRowStatus | BarcodeRowWarning, number>;
  rows: BarcodeImportRow[];
  applied?: number;
}

export const BARCODE_IMPORT_ACCEPT = '.xlsx,.csv';

async function post(
  path: string,
  file: File,
  fallback: string,
): Promise<BarcodeImportOutcome> {
  const body = new FormData();
  body.append('file', file);
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

export function applyBarcodeImport(file: File): Promise<BarcodeImportOutcome> {
  return post('apply', file, 'Failed to apply the file');
}
