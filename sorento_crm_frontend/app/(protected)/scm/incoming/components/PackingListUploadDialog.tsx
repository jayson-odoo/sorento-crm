'use client';

import { useEffect, useState } from 'react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MAX_SIZE_MB, useTwoStepUpload } from '../../reorder/hooks/useTwoStepUpload';
import { CountTile } from '../../reorder/components/UploadCountTile';
import { UploadTestVerdict } from '../../reorder/components/UploadTestVerdict';
import { EM_DASH, fmtInt } from '../../lib/format';
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
 *
 * Currency is asked for LAST and usually not at all. These files price what they ship, and the
 * price is stored with the money it is in - but the document normally states that itself
 * (`RMB`, `单价(元)`) and the supplier's price list often does too, so the field is the last
 * resort rather than the first question. Where one of them answered, the read says which.
 */

/** Where the currency came from, in the words the operator would use. */
const CURRENCY_SOURCE: Record<string, string> = {
  form: 'as entered above',
  document: 'stated by the file',
  supplier_price_list: "from the supplier's price list",
};

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
  const [currency, setCurrency] = useState('');
  const trimmedCurrency = currency.trim() || null;

  // Cleared on every open, like the file and the verdict: a currency left over from the last
  // upload would silently override what the NEXT file states.
  useEffect(() => {
    if (open) setCurrency('');
  }, [open]);

  const upload = useTwoStepUpload<PackingListPreview, ApplyResult>({
    open,
    preview: (file) => previewPackingList(file, { supplierId, currency: trimmedCurrency }),
    apply: (file) =>
      applyPackingList(file, {
        supplierId,
        currency: trimmedCurrency,
      }) as unknown as Promise<ApplyResult>,
    test: (file) =>
      applyPackingList(file, {
        supplierId,
        currency: trimmedCurrency,
        validateOnly: true,
      }) as unknown as Promise<never>,
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

          <div>
            <Label htmlFor="packing-list-currency" className="mb-1 block text-xs">
              Currency
            </Label>
            <Input
              id="packing-list-currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))}
              maxLength={3}
              placeholder="MYR"
              autoComplete="off"
              className="w-28 uppercase"
              disabled={upload.previewing || upload.applying}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Only needed when the file does not state one.
            </p>
          </div>

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
              {preview.priced_lines ? (
                <p className="text-2xs text-muted-foreground">
                  {preview.currency
                    ? `Priced in ${preview.currency} (${CURRENCY_SOURCE[preview.currency_source ?? 'none'] ?? preview.currency_source}).`
                    : 'Nothing states which money these prices are in - enter a currency above.'}
                </p>
              ) : null}
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
                      {b.lines} lines · {fmtInt(b.qty)} pcs
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
