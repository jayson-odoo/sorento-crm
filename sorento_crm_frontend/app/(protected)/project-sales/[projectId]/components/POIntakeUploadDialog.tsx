'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileDropzone } from '@/components/common/FileDropzone';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePOUpload } from '../../_shared/hooks/usePOIntake';
import { listEditableProjectOptions } from '../../_shared/services/projectService';
import { pipelineOriginHref, withReviewOrigin } from '../../_shared/lib/reviewOrigin';

const ACCEPT = '.pdf,.jpg,.jpeg,.png';

/**
 * Uploading the scan.
 *
 * The upload returns as soon as the document is stored, so this closes and goes straight to
 * the confirm screen, where extraction reports itself. Holding a modal open for two minutes
 * of queue time would be a worse lie than showing the queue.
 *
 * `projectId` is omitted when this opens from the page-level Start menu (S2), which is not
 * scoped to a row: the project field renders first and the rest of the dialog behaves exactly
 * as the per-project call sites already do, once one is picked. That same absence is what
 * names the review page's origin (S4): Start always returns to the Pipeline list
 * (`pipelineListQuery` is the grid's own list state), a fixed `projectId` call site names its
 * own origin instead (`originHref`, e.g. the project's own tab) or omits one to stay put.
 */
export function POIntakeUploadDialog({
  projectId,
  purchaseOrderId,
  purchaseOrderNumber,
  onDone,
  originHref,
  pipelineListQuery,
}: {
  projectId?: string;
  purchaseOrderId?: string | null;
  purchaseOrderNumber?: string | null;
  onDone: () => void;
  originHref?: string;
  pipelineListQuery?: string;
}) {
  const router = useRouter();
  const [pickedProjectId, setPickedProjectId] = React.useState('');
  const needsProjectField = !projectId;
  const effectiveProjectId = projectId ?? pickedProjectId;
  const upload = usePOUpload(effectiveProjectId);
  const [file, setFile] = React.useState<File | null>(null);
  const [poNumber, setPoNumber] = React.useState('');

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {purchaseOrderId
              ? `Upload a new document for ${purchaseOrderNumber || 'this PO'}`
              : 'Upload a customer PO'}
          </DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!file || !effectiveProjectId) return;
            const result = await upload
              .mutateAsync({
                file,
                po_number: purchaseOrderId ? null : poNumber.trim() || null,
                purchase_order_id: purchaseOrderId ?? null,
              })
              .catch(() => null);
            if (!result) return;
            toast.success(
              result.page_count
                ? `Uploaded. Reading ${result.page_count} page${result.page_count === 1 ? '' : 's'}.`
                : 'Uploaded. Reading the document.',
            );
            onDone();
            const origin = needsProjectField
              ? pipelineOriginHref(pipelineListQuery, effectiveProjectId)
              : originHref;
            router.push(
              withReviewOrigin(
                `/project-sales/${effectiveProjectId}/purchase-orders/${result.po_version_id}`,
                origin,
              ),
            );
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            {needsProjectField && (
              <div className="space-y-1.5">
                <Label htmlFor="po-upload-project">
                  Project <span className="text-destructive">*</span>
                </Label>
                <SearchableSelect
                  id="po-upload-project"
                  value={pickedProjectId}
                  onChange={setPickedProjectId}
                  clearable
                  fetchOptions={listEditableProjectOptions}
                  placeholder="Search a project"
                  emptyMessage="No projects match"
                />
              </div>
            )}

            <FileDropzone
              id="po-upload-file"
              accept={ACCEPT}
              files={file ? [file] : []}
              onFilesChange={(files) => setFile(files[0] ?? null)}
              onReject={(rejected, reason) =>
                toast.error(
                  reason === 'type'
                    ? `${rejected.name} is not a PDF or a photo.`
                    : `${rejected.name} is larger than 25 MB.`,
                )
              }
              maxSizeMb={25}
              title="Drop the PO here"
              hint="PDF or photo"
              aria-label="PO document"
            />

            {!purchaseOrderId && (
              <div className="space-y-1.5">
                <Label htmlFor="po-upload-number">PO number</Label>
                <Input
                  id="po-upload-number"
                  value={poNumber}
                  onChange={(event) => setPoNumber(event.target.value)}
                  placeholder="Leave blank and the extraction fills it"
                />
              </div>
            )}
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!file || !effectiveProjectId || upload.isPending}>
              {upload.isPending ? 'Uploading…' : 'Upload'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
