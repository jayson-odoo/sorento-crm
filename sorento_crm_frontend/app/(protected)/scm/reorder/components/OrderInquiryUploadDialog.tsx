'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
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
import { ImportFeedbackSections } from '@/components/common/ImportFeedbackSections';
import { useImportJobDrawer } from '@/components/upload-activity/useImportJobDrawer';
import type { ImportQueuedResult } from '@/components/upload-activity/importQueue';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyOrderInquiry,
  previewOrderInquiry,
  testOrderInquiry,
  type OrderInquiryPreview,
} from '../services/orderInquiryService';
import { CountTile } from './UploadCountTile';
import { UploadReadingIndicator } from './UploadReadingIndicator';
import { UploadTestVerdict } from './UploadTestVerdict';
import { fmtInt } from '../../lib/format';

/**
 * SCM - the Order Inquiry sheet upload.
 *
 * Renamed from `HistoryUploadDialog` (ingest-parity-standardisation S4, AC-P4-1): this dialog
 * used to also carry the purchase-history and sales-history curation feeds, which were
 * retired - closed history now arrives through the ESB's own document ingest. What remains is
 * the Order Inquiry sheet, which carries what neither the order book nor a history extract
 * holds - where stock is meant to land, and which purchase order a sales order is waiting on.
 *
 * Test, then upload, with nothing at all running on file select. Confirm queues an import job
 * and the upload drawer follows it, because the resolve happens on the worker. So what the
 * upload DID is reported on the job page, not here.
 *
 * The flow itself is shared (`useTwoStepUpload`), so the sequence guard and the server-owned
 * accept list cannot drift between the dialogs.
 */

const TITLE = 'Upload order inquiry sheet';
const DESCRIPTION = 'Stock locations, and which purchase order each sales order is waiting on.';
const DROPZONE_LABEL = 'Order Inquiry file';

/** How many codes or numbers to name before collapsing the rest into a tail count. */
const CHIP_LIMIT = 12;

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

// ── pieces ──────────────────────────────────────────────────────────────────

/**
 * A named list. Named rather than only counted: a count says there is a problem, the codes
 * say which one, and the list is what somebody acts on.
 *
 * `total` is separate from `items.length` and is NOT optional, because the backend caps every
 * one of these lists at 200. Heading the section with the length of what it happens to be
 * showing turns 15,787 missing sales orders into "(200)", which reads like a small, closed
 * problem. The count is the truth; the chips are a sample of it.
 */
function ChipList({
  title,
  items,
  total,
  hint,
}: {
  title: string;
  items: string[];
  total: number;
  hint?: string;
}) {
  if (!items.length) return null;
  const hidden = Math.max(total, items.length) - Math.min(items.length, CHIP_LIMIT);
  return (
    <div className="rounded-lg border border-border p-3">
      <h4 className="text-xs font-semibold">
        {title} ({fmtInt(Math.max(total, items.length))})
      </h4>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {items.slice(0, CHIP_LIMIT).map((item) => (
          <span key={item} className="rounded bg-muted px-1.5 py-0.5 text-2xs font-mono">
            {item}
          </span>
        ))}
        {hidden > 0 ? (
          <span className="px-1.5 py-0.5 text-2xs text-muted-foreground">
            +{fmtInt(hidden)} more
          </span>
        ) : null}
      </div>
      {hint ? <p className="mt-1.5 text-2xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/** The file could not be read at all. Rendered by the shared import feedback component, so
    a blocking problem looks the same here as in every other import dialog. */
function Problems({ problems }: { problems: string[] }) {
  return <ImportFeedbackSections errors={problems} />;
}

function InquirySummary({ data }: { data: OrderInquiryPreview }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <CountTile label="Rows" value={data.rows} />
          {/* Both figures, always. The book restates an instalment across its month, roll-up
              and snapshot tabs, so a reader shown only the smaller number reads the drop as
              rows lost. */}
          <CountTile label="Scheduled deliveries" value={data.instalments} />
          <CountTile label="Matched" value={data.lines_matched} />
          <CountTile label="PO links" value={data.po_claims} />
          <CountTile label="Not ordered yet" value={data.not_ordered} />
        </div>
        <p className="mt-1.5 text-2xs text-muted-foreground">
          {fmtInt(data.sheets_read.length)}{' '}
          {plural(data.sheets_read.length, 'sheet', 'sheets')} read
          {data.sheets_skipped.length
            ? `, ${fmtInt(data.sheets_skipped.length)} skipped`
            : ''}
          .
        </p>
        {data.rows_restating_an_instalment > 0 ? (
          <p className="mt-1 text-2xs text-muted-foreground">
            {fmtInt(data.rows_restating_an_instalment)}{' '}
            {plural(data.rows_restating_an_instalment, 'row', 'rows')} restate a delivery
            another sheet already lists, counted once.
          </p>
        ) : null}
      </div>

      <ChipList
        title="Sales orders we have not received yet"
        items={data.sales_orders_not_found}
        total={data.lines_unmatched}
        hint="Their locations are not written. Upload this sheet again once those orders land."
      />
      <ChipList
        title="Locations we do not recognise"
        items={data.unknown_locations}
        total={data.unknown_locations.length}
        hint="Add the warehouse, or correct the code in the sheet."
      />
    </div>
  );
}

// ── dialog ──────────────────────────────────────────────────────────────────

export interface OrderInquiryUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fired once the job is queued, so a page can react to the upload having started. */
  onQueued?: (queued: ImportQueuedResult) => void;
}

export function OrderInquiryUploadDialog({
  open,
  onOpenChange,
  onQueued,
}: OrderInquiryUploadDialogProps) {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();

  const upload = useTwoStepUpload<OrderInquiryPreview, ImportQueuedResult>({
    open,
    preview: (file) => previewOrderInquiry(file),
    apply: (file) => applyOrderInquiry(file),
    test: (file) => testOrderInquiry(file),
    onApplied: (queued) => {
      // The work is not tied to this tab: open the drawer, close the dialog, and let the job
      // be followed there.
      notifyImportQueued();
      onOpenChange(false);
      toast.success('Upload queued. Processing in the background.', {
        duration: 6000,
        action: {
          label: 'View job',
          onClick: () => router.push(`/system-management/import-jobs/${queued.job_id}`),
        },
      });
      onQueued?.(queued);
    },
  });

  const { file, preview: shown, previewing, applying, error } = upload;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{TITLE}</DialogTitle>
          {/* Also the dialog's accessible description - without one Radix warns that the
              content has no `aria-describedby`. */}
          <DialogDescription>{DESCRIPTION}</DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <FileDropzone
            files={file ? [file] : []}
            onFilesChange={(next) => upload.choose(next[0] ?? null)}
            onReject={upload.reject}
            accept={upload.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={previewing || applying}
            aria-label={DROPZONE_LABEL}
          />

          <UploadReadingIndicator reading={previewing} />

          {upload.testResult ? <UploadTestVerdict result={upload.testResult} /> : null}

          {shown && !shown.ok ? <Problems problems={shown.problems} /> : null}

          {shown && shown.ok ? <InquirySummary data={shown} /> : null}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void upload.runTest()}
            disabled={!file || previewing || applying || upload.testing}
          >
            {upload.testing ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <TestTube className="size-4" aria-hidden />
            )}
            Test
          </Button>
          <Button onClick={() => void upload.confirm()} disabled={!upload.canConfirm}>
            {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
            Confirm upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default OrderInquiryUploadDialog;
