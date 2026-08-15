'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { MAX_SIZE_MB, useTwoStepUpload } from '../../reorder/hooks/useTwoStepUpload';
import { CountTile } from '../../reorder/components/UploadCountTile';
import { UploadTestVerdict } from '../../reorder/components/UploadTestVerdict';
import { EM_DASH } from '../../lib/format';
import {
  applyPackingList,
  previewPackingList,
  type PackingListPreview,
} from '../../services/fulfilmentService';

/**
 * The pre-load list or packing list.
 *
 * The thing this dialog exists to show before Confirm is that the file holds SEVERAL
 * containers. A count of lines would hide it: five blocks of seven read as "35 rows", and the
 * user would find out it created five shipments afterwards. So the blocks are listed, each with
 * its own container number, and a block with none says so rather than showing a blank.
 */

interface ImportedShipment {
  shipment_id: string;
  shipment_number: string;
  container_no: string | null;
  lines: number;
}

interface ApplyResult {
  shipments_created: number;
  shipments_updated: number;
  lines_skipped: number;
  results: {
    shipment_id?: string;
    shipment_number: string;
    container_no?: string | null;
    lines?: number;
    created: boolean;
    reason?: string;
  }[];
}

export function PackingListUploadDialog({
  open,
  onOpenChange,
  supplierId,
  onImported,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  supplierId: string | null;
  onImported?: (shipments: ImportedShipment[]) => void;
}) {
  const upload = useTwoStepUpload<PackingListPreview, ApplyResult>({
    open,
    preview: (file) => previewPackingList(file),
    apply: (file) =>
      applyPackingList(file, { supplierId }) as unknown as Promise<ApplyResult>,
    test: (file) =>
      applyPackingList(file, { supplierId, validateOnly: true }) as unknown as Promise<never>,
    onApplied: (result) =>
      onImported?.(
        (result.results ?? [])
          .filter((r) => r.shipment_id)
          .map((r) => ({
            shipment_id: r.shipment_id as string,
            shipment_number: r.shipment_number,
            container_no: r.container_no ?? null,
            lines: r.lines ?? 0,
          })),
      ),
  });

  const { preview, result } = upload;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload packing list</DialogTitle>
          <DialogDescription>
            Every container block in the file becomes its own shipment.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <FileDropzone
            files={upload.file ? [upload.file] : []}
            onFilesChange={(next) => void upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={upload.previewing || upload.applying}
            aria-label="Packing list file"
          />

          {upload.previewing ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <LoaderCircle className="size-3.5 animate-spin" /> Reading the file...
            </p>
          ) : null}

          {upload.error ? (
            <Alert variant="destructive">
              <AlertDescription>{upload.error}</AlertDescription>
            </Alert>
          ) : null}

          {preview && !preview.ok ? (
            <Alert variant="destructive">
              <AlertDescription>
                {preview.missing_columns?.length
                  ? `This file has no ${preview.missing_columns.join(', ')} column.`
                  : 'No container block was found in this file.'}
              </AlertDescription>
            </Alert>
          ) : null}

          {preview?.ok && !result ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <CountTile label="Containers" value={preview.block_count} />
                <CountTile label="Lines" value={preview.line_count} />
                <CountTile label="Not in catalogue" value={preview.unmatched_items} />
              </div>
              <div className="divide-y divide-border rounded-lg border">
                {preview.blocks.map((b) => (
                  <div
                    key={`${b.shipment_number}-${b.index}`}
                    className="flex items-center justify-between gap-3 p-2.5"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium">
                        {b.container_no || 'No container number yet'}
                      </div>
                      <div className="truncate text-2xs text-muted-foreground">
                        {b.bl_no ? `B/L ${b.bl_no}` : EM_DASH}
                      </div>
                    </div>
                    <span className="shrink-0 text-2xs text-muted-foreground">
                      {b.lines} lines · {b.qty.toLocaleString()} pcs
                    </span>
                  </div>
                ))}
              </div>
              {preview.unmatched_items > 0 ? (
                <p className="text-2xs text-muted-foreground">
                  {preview.unmatched_item_codes.slice(0, 8).join(', ')}
                  {preview.unmatched_items > 8
                    ? ` and ${preview.unmatched_items - 8} more`
                    : ''}{' '}
                  {preview.unmatched_items === 1 ? 'is' : 'are'} not in the catalogue.{' '}
                  {preview.unmatched_items === 1 ? 'That line' : 'Those lines'} will not be
                  created.
                </p>
              ) : null}
            </div>
          ) : null}

          {upload.testResult ? <UploadTestVerdict result={upload.testResult} /> : null}

          {result ? (
            <Alert>
              <AlertDescription>
                {result.shipments_created > 0
                  ? `Created ${result.shipments_created} container${result.shipments_created === 1 ? '' : 's'}`
                  : 'Nothing new was created'}
                {result.shipments_updated > 0
                  ? `, updated ${result.shipments_updated}`
                  : ''}
                {result.lines_skipped > 0
                  ? `. ${result.lines_skipped} line${result.lines_skipped === 1 ? '' : 's'} skipped for having no product we hold`
                  : ''}
                .
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => void upload.runTest()}
            disabled={!upload.file || upload.testing || upload.applying}
          >
            {upload.testing ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <TestTube className="size-4" />
            )}
            Test
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {!result ? (
            <Button onClick={() => void upload.confirm()} disabled={!upload.canConfirm}>
              {upload.applying ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Confirm
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
