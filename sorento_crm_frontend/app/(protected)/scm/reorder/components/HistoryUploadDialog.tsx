'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
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
import { formatDateInMalaysia } from '@/lib/helpers';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyOrderInquiry,
  applyPurchaseHistory,
  previewOrderInquiry,
  previewPurchaseHistory,
  testOrderInquiry,
  testPurchaseHistory,
  type HistoryImportKind,
  type OrderInquiryPreview,
  type PurchaseHistoryPreview,
  type SalesHistoryPreview,
  previewSalesHistory,
  applySalesHistory,
} from '../services/purchaseHistoryService';
import { CountTile } from './UploadCountTile';
import { UploadTestVerdict } from './UploadTestVerdict';

/**
 * SCM - the three curation feeds: purchase history, sales history, and the Order Inquiry
 * sheet.
 *
 * Separate from `OutstandingUploadDialog` because the files MEAN different things, not
 * because they look different. The outstanding extract is the open order book and drives
 * supply; this dialog's files carry what that extract does not hold - what was bought and
 * sold historically, where stock is meant to land, and which purchase order a sales order is
 * waiting on.
 *
 * Test, then upload, with nothing at all running on file select. Confirm queues an import
 * job and the upload drawer follows it: the sales book is 81,361 lines in the client's own
 * export and writing it inside the request is what timed the gateway out. So what the upload
 * DID is reported on the job page, not here.
 *
 * The flow itself is shared (`useTwoStepUpload`), so the sequence guard and the server-owned
 * accept list cannot drift between the dialogs.
 */

const COPY: Record<
  HistoryImportKind,
  { title: string; description: string; dropzoneLabel: string }
> = {
  'purchase-history': {
    title: 'Upload purchase history',
    // What it does to the plan, in one line. Not a description of the file format, and not
    // lead time: that is measured to the goods receipt and this file carries none.
    description: 'Past orders, for last cost and slow movers. Never counted as incoming stock.',
    dropzoneLabel: 'Purchase Order Listing file',
  },
  'sales-history': {
    title: 'Upload sales history',
    // What it does to the plan, in one line. The second sentence is the whole point of the
    // channel: the same file through the outstanding upload would be demand.
    description: 'Past sales orders, for the demand record. Never counted as demand.',
    dropzoneLabel: 'Sales Order Listing file',
  },
  'order-inquiry': {
    title: 'Upload order inquiry sheet',
    description: 'Stock locations, and which purchase order each sales order is waiting on.',
    dropzoneLabel: 'Order Inquiry file',
  },
};

/** How many codes or numbers to name before collapsing the rest into a tail count. */
const CHIP_LIMIT = 12;

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

function dateText(value: string | null): string {
  return value ? formatDateInMalaysia(value) : '-';
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
        {title} ({Math.max(total, items.length).toLocaleString()})
      </h4>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {items.slice(0, CHIP_LIMIT).map((item) => (
          <span key={item} className="rounded bg-muted px-1.5 py-0.5 text-2xs font-mono">
            {item}
          </span>
        ))}
        {hidden > 0 ? (
          <span className="px-1.5 py-0.5 text-2xs text-muted-foreground">
            +{hidden.toLocaleString()} more
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

function HistorySummary({ data }: { data: PurchaseHistoryPreview }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <CountTile label="Orders" value={data.orders} />
          <CountTile label="New" value={data.orders_new} />
          <CountTile label="Already held" value={data.orders_existing} />
          <CountTile label="Lines" value={data.lines} />
          <CountTile label="Charge lines" value={data.charge_lines} />
        </div>
        <p className="mt-1.5 text-2xs text-muted-foreground">
          {dateText(data.date_from)} to {dateText(data.date_to)}.{' '}
          {data.so_claims.toLocaleString()}{' '}
          {plural(data.so_claims, 'order names', 'orders name')} a sales order.
        </p>
      </div>

      <ChipList
        title="Items we do not hold"
        items={data.unmatched_item_codes}
        total={data.unmatched_items}
        hint="These lines are skipped. Nothing is created in the product catalogue from an upload."
      />
    </div>
  );
}

/**
 * The sales book, and the one figure it carries that no other channel does.
 *
 * `Still owed` above zero means the file is not purely history: those lines carry real
 * outstanding quantity, they will be absorbed as finished business anyway, and the
 * outstanding channel is where they belong. It is shown even at zero, because a figure that
 * appears only when it is bad teaches nobody where to look.
 *
 * What the upload then DID - created, updated, unchanged, and the documents it settled that
 * still owed something - is reported on the job, because it happens on the worker.
 */
function SalesHistorySummary({ data }: { data: SalesHistoryPreview }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          <CountTile label="Orders" value={data.orders} />
          <CountTile label="Lines" value={data.lines} />
          <CountTile label="Charge lines" value={data.non_stock_lines} />
          <CountTile label="Still owed" value={data.outstanding_lines} />
        </div>
        <p className="mt-1.5 text-2xs text-muted-foreground">
          {dateText(data.date_from)} to {dateText(data.date_to)}.{' '}
          {data.layout_rows.toLocaleString()}{' '}
          {plural(data.layout_rows, 'row is', 'rows are')} a package caption or spacer.
        </p>
      </div>

      <ChipList
        title="Items we do not hold"
        items={data.unknown_items}
        total={data.unknown_item_count}
        hint="These lines are skipped. Nothing is created in the product catalogue from an upload."
      />
      <ChipList
        title="Customers we do not hold"
        items={data.unknown_debtors}
        total={data.unknown_debtor_count}
        hint="The orders are still absorbed, with the debtor code and printed name kept on them so the link can be made later."
      />
      <ChipList
        title="Locations we do not hold"
        items={data.unknown_locations}
        total={data.unknown_locations.length}
        hint="Those lines are absorbed without a location rather than guessing one."
      />
    </div>
  );
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
          {data.sheets_read.length.toLocaleString()}{' '}
          {plural(data.sheets_read.length, 'sheet', 'sheets')} read
          {data.sheets_skipped.length
            ? `, ${data.sheets_skipped.length.toLocaleString()} skipped`
            : ''}
          .
        </p>
        {data.rows_restating_an_instalment > 0 ? (
          <p className="mt-1 text-2xs text-muted-foreground">
            {data.rows_restating_an_instalment.toLocaleString()}{' '}
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

export interface HistoryUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: HistoryImportKind;
  /** Fired once the job is queued, so a page can react to the upload having started. */
  onQueued?: (queued: ImportQueuedResult) => void;
}

export function HistoryUploadDialog({
  open,
  onOpenChange,
  kind,
  onQueued,
}: HistoryUploadDialogProps) {
  const isHistory = kind === 'purchase-history';
  const isSales = kind === 'sales-history';
  const copy = COPY[kind];
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();

  const upload = useTwoStepUpload<
    PurchaseHistoryPreview | OrderInquiryPreview | SalesHistoryPreview,
    ImportQueuedResult
  >({
    open,
    preview: (file) =>
      isSales
        ? previewSalesHistory(file)
        : isHistory
          ? previewPurchaseHistory(file)
          : previewOrderInquiry(file),
    apply: (file) =>
      isSales
        ? applySalesHistory(file)
        : isHistory
          ? applyPurchaseHistory(file)
          : applyOrderInquiry(file),
    // The sales book has no `validate_only` route: its apply is already a reconcile
    // (same -> skip) rather than an append, so the preview IS its dry run. The other two have
    // one, and Test runs it alongside the preview - one press, one answer.
    test: isSales
      ? undefined
      : (file) => (isHistory ? testPurchaseHistory(file) : testOrderInquiry(file)),
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
          <DialogTitle>{copy.title}</DialogTitle>
          {/* Also the dialog's accessible description - without one Radix warns that the
              content has no `aria-describedby`. */}
          <DialogDescription>{copy.description}</DialogDescription>
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
            aria-label={copy.dropzoneLabel}
          />

          {previewing ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
              Reading the file...
            </div>
          ) : null}

          {upload.testResult ? <UploadTestVerdict result={upload.testResult} /> : null}

          {shown && !shown.ok ? <Problems problems={shown.problems} /> : null}

          {shown && shown.ok ? (
            isSales ? (
              <SalesHistorySummary data={shown as SalesHistoryPreview} />
            ) : isHistory ? (
              <HistorySummary data={shown as PurchaseHistoryPreview} />
            ) : (
              <InquirySummary data={shown as OrderInquiryPreview} />
            )
          ) : null}
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

export default HistoryUploadDialog;
