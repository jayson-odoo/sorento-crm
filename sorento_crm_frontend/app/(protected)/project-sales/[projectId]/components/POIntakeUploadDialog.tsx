'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
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
import { usePOUpload } from '../../_shared/hooks/usePOIntake';

const ACCEPT = '.pdf,.jpg,.jpeg,.png';

/**
 * Uploading the scan.
 *
 * The upload returns as soon as the document is stored, so this closes and goes straight to
 * the confirm screen, where extraction reports itself. Holding a modal open for two minutes
 * of queue time would be a worse lie than showing the queue.
 */
export function POIntakeUploadDialog({
  projectId,
  purchaseOrderId,
  purchaseOrderNumber,
  onDone,
}: {
  projectId: string;
  purchaseOrderId?: string | null;
  purchaseOrderNumber?: string | null;
  onDone: () => void;
}) {
  const router = useRouter();
  const upload = usePOUpload(projectId);
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
            if (!file) return;
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
            router.push(
              `/project-sales/${projectId}/purchase-orders/${result.po_version_id}`,
            );
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
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
            <Button type="submit" disabled={!file || upload.isPending}>
              {upload.isPending ? 'Uploading…' : 'Upload'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
