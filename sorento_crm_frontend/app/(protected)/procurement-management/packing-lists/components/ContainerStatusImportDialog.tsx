'use client';

import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { useImportJobDrawer } from '@/components/upload-activity';
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
 * It queues a background import job exactly like the SPO allocation and delivery
 * order imports: `notifyImportQueued()` pops the Upload Activity drawer open and
 * the job then drives its own polling until terminal, and the toast offers a
 * shortcut to the job page. An import is never a fire-and-forget toast.
 *
 * PHASE 1 MOCK - `onTest` and `onUpload` are stubbed. Wire to
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

/**
 * HOW THE PARSER MUST READ THE WORKBOOK, and the numbers that follow from it.
 *
 * Nothing here is positional. Every sheet is scanned for rows whose cell text is
 * exactly "CONTAINER"; each such row OPENS a block, and that block's columns are
 * resolved from its own header row. `Container Status 2026.xlsx` has 5 tabs holding
 * 9 blocks, because several tabs stack more than one titled section:
 *
 *   Fitting                          header rows 2, 31        17 + 2   = 19
 *   Ceramic                          header rows 2, 69, 75    55 + 0 + 0 = 55
 *   Arrived                          header row  2            318
 *   Arrived - Joint Mocha Container  header rows 2, 22        15 + 0   = 15
 *   Arrived (Mocha) Joint BL         header row  2            0
 *                                                             ------------
 *                                                             407 containers
 *
 * 407 values, 407 distinct, zero collisions across tabs.
 *
 * A repeated header row is therefore a SECTION BOUNDARY, not a bad data row. An
 * earlier draft of this mock reported those 4 rows (Fitting 31, Ceramic 69 and 75,
 * Joint Mocha 22) as ISO 6346 rejects, which was wrong twice over: they are headers,
 * and the true reject count is 0 - every one of the 407 values matches ^[A-Z]{4}\d{7}$.
 *
 * Header names drift between tabs, so matching is by NAME WITH ALIASES:
 *   LINER              <- Ceramic calls it "RL" (values are CMA / WHL / OOCL / ...)
 *   WAREHOUSE ARRIVALS <- Arrived calls it "W/H ARRIVALS"
 *   CHINA FORWARDING COST (RMB) <- Arrived calls it "CHINA FREIGHT (RMB)"
 *   SST                <- Joint Mocha calls it "10% SST"
 *   DEMURRAGE          <- three tabs misspell it "Demurrange"
 * Reading Ceramic's column 4 positionally would have mislabelled 55 liners.
 */
const MOCK_DRY_RUN: ValidateImportResult = {
  valid: true,
  errors: [],
  warnings: [
    '9 header blocks across 5 tabs. Each block is anchored on its own row reading "CONTAINER" (Fitting 2 and 31, Ceramic 2, 69 and 75, Arrived 2, Arrived - Joint Mocha 2 and 22, Arrived (Mocha) Joint BL 2) and its columns are read from that row, so a repeated header opens a new section instead of failing as a data row.',
    'Ceramic labels its liner column "RL" while every other tab labels it "LINER"; Arrived uses "W/H ARRIVALS" for "WAREHOUSE ARRIVALS". Matched by name, so all 407 rows still resolve.',
    '475 numbered rows carry no container number and are skipped without an error. Arrived alone accounts for 427 of them.',
    '4 of the 9 blocks are empty scaffolding: Ceramic sections 2 and 3, Arrived - Joint Mocha section 2, and the whole Arrived (Mocha) Joint BL tab.',
    '140 of 407 containers sit on a liner with no tracking adapter. Adapters cover WHL (116), CMA (79) and OOCL (72); the other 15 liners stay manual.',
  ],
  // Canonical summary keys - TemplateUploadDialog only renders these, so the S3
  // endpoint must return them under exactly these names.
  summary: {
    total_rows: 407,
    would_update: 111,
    would_create: 296,
    error_count: 0,
  },
};

/** Stand-in for the `job_id` the real 202 returns. */
const MOCK_JOB_ID = '00000000-0000-4000-8000-000000000c51';

export default function ContainerStatusImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();

  const handleTest = async (): Promise<ValidateImportResult> => {
    await new Promise((r) => setTimeout(r, 900));
    return MOCK_DRY_RUN;
  };

  const handleUpload = async (
    _rows: unknown[],
    helpers?: TemplateUploadHelpers,
    file?: File,
  ): Promise<void> => {
    // The workbook is parsed server-side: 9 header blocks over 5 tabs, so the raw
    // file is what gets posted. `_rows` (the dialog's client-side parse of the first
    // sheet only) is deliberately unused - it would see one block and miss 390 rows.
    helpers?.setStatus?.('Uploading workbook...');
    for (const pct of [15, 45, 75, 100]) {
      helpers?.setProgress(pct);
      await new Promise((r) => setTimeout(r, 220));
    }
    helpers?.setStatus?.('Queued for import');
    onOpenChange(false);

    // Same handoff as the SPO and delivery order imports: open the Upload Activity
    // drawer so the job is visible while it runs, and offer the job page directly.
    notifyImportQueued();
    toast.success(
      `${file?.name ?? 'Workbook'} queued. Clearance dates appear on each container once the import finishes.`,
      {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${MOCK_JOB_ID}`),
        },
      },
    );
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
