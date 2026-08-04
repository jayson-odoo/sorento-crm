'use client';

import { toast } from 'sonner';
import {
  TemplateUploadDialog,
  type TemplateUploadHelpers,
  type ValidateImportResult,
} from '@/components/template/TemplateUploadDialog';

/**
 * Import the Container Status workbook.
 *
 * The entry point lives HERE, on Packing Lists, not in the generic file library.
 * One sheet row is one packing list, so this is the domain the maintainer is already
 * working in. The file is still retained as an attachment behind the scenes (so the
 * assistant can hand the workbook back to a contact), but that is storage, not a
 * place anyone should have to navigate to in order to upload.
 *
 * PHASE 1 MOCK — `onTest` and `onUpload` are stubbed. Wire to
 * POST /api/v1/procurement/packing-lists/container-status-import in S3 (issue #61).
 *
 * EXPECTED CONTRACT (documented here so S3 builds to it):
 *   POST  multipart/form-data { file }
 *   202   { job_id, queued: true }
 *   POST  .../container-status-import/validate  (dry run, no writes)
 *   200   { valid, errors[], warnings[],
 *           summary: { total_rows, would_update, would_create, error_count } }
 *
 * Those summary key names are NOT free choice: TemplateUploadDialog renders a fixed
 * set and silently drops anything else.
 */

/** Mirrors the real workbook so the prototype shows believable numbers. */
const MOCK_DRY_RUN: ValidateImportResult = {
  valid: true,
  errors: [],
  warnings: [
    '4 rows rejected: container number is not a valid ISO 6346 code (repeated header rows reading "CONTAINER") - Fitting row 31, Ceramic rows 69 and 75, Arrived - Joint Mocha row 22.',
    '31 rows carry a liner with no tracking adapter (TCLC, IAA, HEDE, NSS, LNL). Their dates stay manual.',
  ],
  // Canonical summary keys — TemplateUploadDialog only renders these, so the S3
  // endpoint must return them under exactly these names.
  summary: {
    total_rows: 411,
    would_update: 111,
    would_create: 296,
    error_count: 4,
  },
};

export default function ContainerStatusImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const handleTest = async (): Promise<ValidateImportResult> => {
    await new Promise((r) => setTimeout(r, 900));
    return MOCK_DRY_RUN;
  };

  const handleUpload = async (
    _rows: unknown[],
    helpers?: TemplateUploadHelpers,
    file?: File,
  ): Promise<void> => {
    // The workbook is parsed server-side: 5 tabs and 51 columns, so the raw file is
    // what gets posted. `_rows` (the dialog's client-side parse of the first sheet)
    // is deliberately unused.
    helpers?.setStatus?.('Uploading workbook...');
    for (const pct of [15, 45, 75, 100]) {
      helpers?.setProgress(pct);
      await new Promise((r) => setTimeout(r, 220));
    }
    helpers?.setStatus?.('Queued for import');
    toast.success(
      `${file?.name ?? 'Workbook'} queued. Clearance dates appear on each container once the import finishes.`,
    );
    onOpenChange(false);
  };

  return (
    <TemplateUploadDialog
      open={open}
      onOpenChange={onOpenChange}
      onUpload={handleUpload}
      onTest={handleTest}
      title="Import Container Status workbook"
      description="Every tab is read and matched to existing packing lists by container number. A blank cell never clears a date you already have. Run Test first to see what would change."
    />
  );
}
