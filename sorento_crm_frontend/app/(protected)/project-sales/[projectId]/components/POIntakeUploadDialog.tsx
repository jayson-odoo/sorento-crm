'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { FileText, Upload, X } from 'lucide-react';
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
import { usePOUpload } from '../../_shared/hooks/usePOIntake';

const ACCEPT = '.pdf,.jpg,.jpeg,.png';
const VALID = ['pdf', 'jpg', 'jpeg', 'png'];

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
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [poNumber, setPoNumber] = React.useState('');
  const [dragging, setDragging] = React.useState(false);

  const accept = (candidate: File | undefined) => {
    if (!candidate) return;
    const extension = candidate.name.split('.').pop()?.toLowerCase();
    if (!extension || !VALID.includes(extension)) {
      toast.error(`Use a PDF or a photo (${ACCEPT})`);
      return;
    }
    setFile(candidate);
  };

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
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={(event) => {
                event.preventDefault();
                setDragging(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                accept(event.dataTransfer?.files?.[0]);
              }}
              className={`rounded-lg border border-dashed px-4 py-8 text-center transition-colors ${
                dragging ? 'border-primary bg-primary/5' : 'border-border'
              }`}
            >
              {file ? (
                <div className="flex items-center justify-center gap-2">
                  <FileText
                    className="size-4 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                  <span
                    className="max-w-[16rem] truncate text-sm font-medium"
                    title={file.name}
                  >
                    {file.name}
                  </span>
                  <Button
                    type="button"
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    aria-label="Remove the selected file"
                    onClick={() => setFile(null)}
                  >
                    <X className="size-3.5" />
                  </Button>
                </div>
              ) : (
                <>
                  <Upload className="mx-auto size-5 text-muted-foreground" aria-hidden />
                  <p className="mt-2 text-sm font-medium">Drop the PO here</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">PDF or photo</p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => inputRef.current?.click()}
                  >
                    Choose a file
                  </Button>
                </>
              )}
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                className="hidden"
                aria-label="PO document"
                onChange={(event) => {
                  accept(event.target.files?.[0]);
                  event.target.value = '';
                }}
              />
            </div>

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
