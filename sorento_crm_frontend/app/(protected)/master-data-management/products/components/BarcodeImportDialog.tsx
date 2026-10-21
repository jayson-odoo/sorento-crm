'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, LoaderCircle, TestTube } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
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
import { CountTile } from '@/components/common/CountTile';
import { generateExcelFile } from '@/lib/excel-utils';
import { toast } from '@/lib/toast';
import {
  BARCODE_IMPORT_ACCEPT,
  applyBarcodeImport,
  previewBarcodeImport,
  type BarcodeImportOutcome,
  type BarcodeImportRow,
  type BarcodeRowStatus,
} from '../services/productBarcodeImportService';

/**
 * Products > Actions > Import barcodes (BARCODE-IMPORT).
 *
 * Test then Apply, nothing on file select, same as the other upload dialogs. Apply is
 * synchronous: one column on a few thousand products is well inside a request.
 */

const MAX_SIZE_MB = 25;

const STATUS: Record<
  BarcodeRowStatus,
  {
    label: string;
    variant: 'success' | 'primary' | 'secondary' | 'outline' | 'destructive';
  }
> = {
  new: { label: 'New', variant: 'success' },
  change: { label: 'Change', variant: 'primary' },
  same: { label: 'Same', variant: 'secondary' },
  unknown_code: { label: 'Unknown code', variant: 'outline' },
  ambiguous_code: { label: 'Code in several companies', variant: 'outline' },
  repeated_code: { label: 'Repeated code', variant: 'outline' },
  blank_barcode: { label: 'Blank barcode', variant: 'outline' },
  too_long: { label: 'Too long', variant: 'destructive' },
};

const WARNING_LABEL = {
  duplicate: 'Duplicate',
  not_ean13: 'Not EAN-13 valid',
} as const;

function downloadTemplate() {
  void generateExcelFile(
    [{}],
    [
      { key: 'Product Code', label: 'Product Code', selected: true },
      { key: 'Barcode', label: 'Barcode', selected: true },
    ],
    'barcode_import_template.xlsx',
  );
}

function BarcodeValue({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  return (
    <span
      className={`block truncate whitespace-nowrap ${className ?? ''}`}
      title={value}
    >
      {value}
    </span>
  );
}

function BarcodeCell({ row }: { row: BarcodeImportRow }) {
  if (row.status === 'change') {
    return (
      <>
        <BarcodeValue
          value={row.old_barcode ?? ''}
          className="text-muted-foreground line-through"
        />
        <BarcodeValue value={`-> ${row.new_barcode ?? ''}`} />
      </>
    );
  }
  if (row.status === 'repeated_code') {
    return (
      <span className="text-muted-foreground">
        Row {row.repeated_of_row} used
      </span>
    );
  }
  const value = row.new_barcode ?? row.old_barcode;
  return value ? <BarcodeValue value={value} /> : null;
}

function OutcomePanel({
  outcome,
  applied,
}: {
  outcome: BarcodeImportOutcome;
  applied: boolean;
}) {
  if (!outcome.readable) {
    return (
      <Alert variant="destructive" appearance="light">
        <AlertDescription>
          No {outcome.missing_columns.join(' or ')} column found. Nothing{' '}
          {applied ? 'was' : 'will be'} written.
        </AlertDescription>
      </Alert>
    );
  }
  const c = outcome.counts;
  const skipped =
    c.unknown_code +
    c.ambiguous_code +
    c.repeated_code +
    c.blank_barcode +
    c.too_long;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Columns used:{' '}
        <span className="font-medium text-foreground">
          {outcome.code_column}
        </span>{' '}
        and{' '}
        <span className="font-medium text-foreground">
          {outcome.barcode_column}
        </span>
        {applied ? (
          <>
            .{' '}
            <span className="font-medium text-foreground">
              {outcome.applied ?? 0}
            </span>{' '}
            product{outcome.applied === 1 ? '' : 's'} updated.
          </>
        ) : null}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CountTile label="New" value={c.new} />
        <CountTile label="Change" value={c.change} />
        <CountTile label="Same" value={c.same} />
        <CountTile label="Skipped" value={skipped} />
        <CountTile label="Unknown code" value={c.unknown_code} />
        <CountTile label="Too long" value={c.too_long} />
        <CountTile label="Duplicate" value={c.duplicate} />
        <CountTile label="Not EAN-13 valid" value={c.not_ean13} />
      </div>
      {outcome.rows.length ? (
        <div className="max-h-80 overflow-auto rounded-lg border">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-2 py-1.5 font-medium">Row</th>
                <th className="px-2 py-1.5 font-medium">Product</th>
                <th className="px-2 py-1.5 font-medium">Barcode</th>
                <th className="px-2 py-1.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {outcome.rows.map((r) => (
                <tr key={r.row} className="border-t align-top">
                  <td className="px-2 py-1.5 tabular-nums text-muted-foreground">
                    {r.row}
                  </td>
                  <td className="max-w-[200px] px-2 py-1.5">
                    <div
                      className="truncate font-medium"
                      title={r.product_code}
                    >
                      {r.product_code || '(blank)'}
                    </div>
                    {r.product_name ? (
                      <div
                        className="truncate text-xs text-muted-foreground"
                        title={r.product_name}
                      >
                        {r.product_name}
                      </div>
                    ) : null}
                  </td>
                  <td className="max-w-[200px] px-2 py-1.5 tabular-nums">
                    <BarcodeCell row={r} />
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex flex-wrap gap-1">
                      <Badge
                        variant={STATUS[r.status].variant}
                        appearance="light"
                        size="sm"
                      >
                        {STATUS[r.status].label}
                      </Badge>
                      {r.warnings.map((w) => (
                        <Badge
                          key={w}
                          variant="warning"
                          appearance="light"
                          size="sm"
                        >
                          {WARNING_LABEL[w]}
                        </Badge>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

export function BarcodeImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BarcodeImportOutcome | null>(null);
  const [result, setResult] = useState<BarcodeImportOutcome | null>(null);
  const [testing, setTesting] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A newer pick must not have an older preview land on top of it.
  const seq = useRef(0);

  useEffect(() => {
    if (!open) return;
    seq.current += 1;
    setFile(null);
    setPreview(null);
    setResult(null);
    setTesting(false);
    setApplying(false);
    setError(null);
  }, [open]);

  const choose = (next: File | null) => {
    seq.current += 1;
    setFile(next);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  const runTest = async () => {
    if (!file) return;
    const token = ++seq.current;
    setTesting(true);
    setError(null);
    try {
      const out = await previewBarcodeImport(file);
      if (seq.current === token) setPreview(out);
    } catch (e) {
      if (seq.current === token)
        setError(e instanceof Error ? e.message : 'Failed to read the file.');
    } finally {
      if (seq.current === token) setTesting(false);
    }
  };

  const apply = async () => {
    if (!file) return;
    setApplying(true);
    setError(null);
    try {
      const out = await applyBarcodeImport(file);
      setResult(out);
      void queryClient.invalidateQueries({ queryKey: ['products'] });
      toast.success(
        `${out.applied ?? 0} barcode${out.applied === 1 ? '' : 's'} updated`,
      );
    } catch (e) {
      const message =
        e instanceof Error ? e.message : 'Failed to apply the file.';
      setError(message);
      toast.error(message);
    } finally {
      setApplying(false);
    }
  };

  const writable = preview ? preview.counts.new + preview.counts.change : null;
  const canApply =
    !!file &&
    !testing &&
    !applying &&
    (!preview || (preview.readable && (writable ?? 0) > 0));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import barcodes</DialogTitle>
          <DialogDescription>
            A sheet with a product code column and a barcode column (.xlsx or
            .csv).
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <FileDropzone
            files={file ? [file] : []}
            onFilesChange={(next) => choose(next[0] ?? null)}
            onReject={(rejected, reason) => {
              if (reason === 'extra') return;
              setError(
                reason === 'size'
                  ? `${rejected.name} is larger than ${MAX_SIZE_MB} MB.`
                  : `${rejected.name} is not a .xlsx or .csv file.`,
              );
            }}
            accept={BARCODE_IMPORT_ACCEPT}
            maxSizeMb={MAX_SIZE_MB}
            disabled={testing || applying}
            aria-label="Barcode file"
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={downloadTemplate}
          >
            <Download className="size-4" aria-hidden />
            Download template
          </Button>

          {error ? (
            <Alert variant="destructive" appearance="light">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {result ? (
            <OutcomePanel outcome={result} applied />
          ) : preview ? (
            <OutcomePanel outcome={preview} applied={false} />
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          {!result ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => void runTest()}
                disabled={!file || testing || applying}
              >
                {testing ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <TestTube className="size-4" aria-hidden />
                )}
                Test
              </Button>
              <Button onClick={() => void apply()} disabled={!canApply}>
                {applying ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : null}
                {writable !== null
                  ? `Apply ${writable} barcode${writable === 1 ? '' : 's'}`
                  : 'Apply'}
              </Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BarcodeImportDialog;
