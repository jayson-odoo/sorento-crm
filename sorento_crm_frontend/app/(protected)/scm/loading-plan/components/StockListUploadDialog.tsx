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
import {
  applyStockList,
  previewStockList,
  testStockList,
  type StockListPreview,
  type StockListResult,
} from '../../services/fulfilmentService';

/**
 * The supplier's own stock list.
 *
 * Two things this dialog has to be loud about, because both are destructive in a way the
 * other SCM uploads are not:
 *
 *  - it REPLACES what we hold for this supplier, so the count of rows it would replace is on
 *    screen before Confirm rather than in the result afterwards;
 *  - the supplier is chosen OUTSIDE the dialog and shown inside it, because a stock list
 *    applied to the wrong supplier deletes one snapshot and invents another.
 */
export function StockListUploadDialog({
  open,
  onOpenChange,
  supplierId,
  supplierName,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  supplierId: string;
  supplierName: string;
  onApplied?: (result: StockListResult) => void;
}) {
  const upload = useTwoStepUpload<StockListPreview, StockListResult>({
    open,
    preview: (file) => previewStockList(file, supplierId),
    apply: (file) => applyStockList(file, supplierId),
    test: (file) => testStockList(file, supplierId),
    onApplied,
  });

  const { preview, result } = upload;
  const summary = preview && 'rows' in (preview.summary ?? {}) ? preview.summary : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload stock list</DialogTitle>
          <DialogDescription>
            What {supplierName} is holding now. Replaces the list we hold for them.
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
            aria-label="Supplier stock list file"
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

          {preview && !preview.readable ? (
            <Alert variant="destructive">
              <AlertDescription>
                {preview.missing_columns.length
                  ? `This file has no ${preview.missing_columns.join(', ')} column.`
                  : 'This file could not be read.'}
              </AlertDescription>
            </Alert>
          ) : null}

          {summary && !result ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <CountTile label="Items" value={summary.rows} />
                <CountTile label="Packed" value={summary.qty_packed} />
                <CountTile label="Unfinished" value={summary.qty_unfinished} />
                <CountTile label="Replaces" value={preview?.rows_held_now ?? 0} />
              </div>
              {summary.items_unmeasured > 0 ? (
                <p className="text-2xs text-muted-foreground">
                  {summary.items_unmeasured.toLocaleString()}{' '}
                  {summary.items_unmeasured === 1 ? 'carries' : 'of them carry'} no volume, so
                  {summary.items_unmeasured === 1 ? ' it cannot' : ' they cannot'} be fitted to a
                  container until the supplier sends one.
                </p>
              ) : null}
              {summary.items_unmatched > 0 ? (
                <p className="text-2xs text-muted-foreground">
                  {summary.items_unmatched.toLocaleString()}{' '}
                  {summary.items_unmatched === 1
                    ? 'model number is not in the catalogue. It is kept, but nothing can be loaded against it.'
                    : 'model numbers are not in the catalogue. They are kept, but nothing can be loaded against them.'}
                </p>
              ) : null}
            </div>
          ) : null}

          {upload.testResult ? <UploadTestVerdict result={upload.testResult} /> : null}

          {result ? (
            <Alert>
              <AlertDescription>
                Saved {result.rows_written.toLocaleString()} items
                {result.rows_replaced > 0
                  ? `, replacing ${result.rows_replaced.toLocaleString()}`
                  : ''}
                .
              </AlertDescription>
            </Alert>
          ) : null}
        </DialogBody>

        <DialogFooter>
          {upload.runTest ? (
            <Button
              variant="outline"
              onClick={() => void upload.runTest?.()}
              disabled={!upload.file || upload.testing || upload.applying}
            >
              {upload.testing ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <TestTube className="size-4" />
              )}
              Test
            </Button>
          ) : null}
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

export default StockListUploadDialog;
