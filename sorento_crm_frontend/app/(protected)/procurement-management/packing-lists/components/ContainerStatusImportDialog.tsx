'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useUploadManager } from '@/components/upload-activity';
import {
  importContainerStatus,
  validateContainerStatusImport,
} from '../services/packingListService';
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
 * LIVE CONTRACT (slice 3):
 *   POST /api/v1/procurement/packing-lists/container-status-import
 *     multipart { file } -> 202 { message, job_id, queued: true }
 *   POST  ...?validate_only=true
 *     200 { valid, errors[], warnings[],
 *           summary: { total_rows, would_update, would_create, error_count } }
 *
 * Those summary key names are NOT free choice: TemplateUploadDialog renders a fixed
 * set and silently drops anything else.
 */

/**
 * WHY THE RAW FILE IS POSTED, rather than the dialog's parsed rows.
 *
 * `Container Status 2026.xlsx` has 5 tabs holding 9 header blocks, because several
 * tabs stack more than one titled section (Fitting rows 2 and 31, Ceramic 2/69/75,
 * Arrived 2, Arrived - Joint Mocha 2 and 22, Arrived (Mocha) Joint BL 2) for 407
 * containers in total. TemplateUploadDialog's own client-side parse reads the FIRST
 * SHEET ONLY, so it would see one block and miss 390 rows. Both handlers below
 * ignore that parse and post the file; the backend does the real read.
 */

export default function ContainerStatusImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { startSession } = useUploadManager();

  const handleTest = async (
    _rows: unknown[],
    file?: File,
  ): Promise<ValidateImportResult> => {
    if (!file) throw new Error('Choose a workbook first.');
    return validateContainerStatusImport(file);
  };

  const handleUpload = async (
    _rows: unknown[],
    helpers?: TemplateUploadHelpers,
    file?: File,
  ): Promise<void> => {
    // The workbook is parsed server-side: 9 header blocks over 5 tabs, so the raw
    // file is what gets posted. `_rows` (the dialog's client-side parse of the first
    // sheet only) is deliberately unused - it would see one block and miss 390 rows.
    if (!file) throw new Error('Choose a workbook first.');

    helpers?.setStatus?.('Uploading workbook...');
    helpers?.setProgress(20);
    const queued = await importContainerStatus(file);
    helpers?.setProgress(100);
    helpers?.setStatus?.('Queued for import');
    onOpenChange(false);

    // Push an `import_job` session so the drawer shows THIS import, not just an
    // empty panel. `notifyImportQueued()` alone only invalidates the backend feed,
    // and the feed has no row until the worker has created the job - so the drawer
    // opens on nothing, which is exactly what it must not do. `startSession` opens
    // the drawer itself and the real backend row replaces this one on reconcile.
    // The uploader has already run (the POST above), so it resolves immediately.
    startSession({
      files: [file],
      sessionType: 'import_job',
      importJobId: queued.job_id,
      title: file.name,
      jobType: 'container_status',
      uploader: async () => ({ attachment_id: queued.job_id }),
    });

    // The worker writes onto the shipments this list is showing.
    void queryClient.invalidateQueries({ queryKey: ['packing-lists'] });

    toast.success(
      `${file.name} queued. Clearance dates appear on each container once the import finishes.`,
      {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () =>
            router.push(`/system-management/import-jobs/${queued.job_id}`),
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
