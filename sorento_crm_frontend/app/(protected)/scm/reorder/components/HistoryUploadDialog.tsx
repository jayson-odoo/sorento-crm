'use client';

import { LoaderCircle } from 'lucide-react';
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
import { formatDateInMalaysia } from '@/lib/helpers';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyOrderInquiry,
  applyPurchaseHistory,
  previewOrderInquiry,
  previewPurchaseHistory,
  type HistoryImportKind,
  type OrderInquiryPreview,
  type OrderInquiryResult,
  type OrderLinkResolution,
  type PurchaseHistoryPreview,
  type PurchaseHistoryResult,
} from '../services/purchaseHistoryService';
import { CountTile } from './UploadCountTile';

/**
 * SCM - the two curation feeds: purchase history, and the Order Inquiry sheet.
 *
 * Separate from `OutstandingUploadDialog` because the files MEAN different things, not
 * because they look different. The outstanding extract is the open order book and drives
 * supply; this dialog's two files carry what that extract does not hold - what was bought
 * historically, where stock is meant to land, and which purchase order a sales order is
 * waiting on.
 *
 * The two-step flow itself is shared (`useTwoStepUpload`), so the sequence guard and the
 * server-owned accept list cannot drift between the dialogs.
 */

const COPY: Record<
  HistoryImportKind,
  { title: string; description: string; dropzoneLabel: string }
> = {
  'purchase-history': {
    title: 'Upload purchase history',
    // What it does to the plan, in one line. Not a description of the file format.
    description: 'Past orders, for supplier lead time and cost. Never counted as incoming stock.',
    dropzoneLabel: 'Purchase Order Listing file',
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

function Problems({ problems }: { problems: string[] }) {
  if (!problems.length) return null;
  return (
    <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3">
      <p className="text-sm font-medium">This file could not be read.</p>
      <ul className="mt-1.5 space-y-1">
        {problems.map((problem) => (
          <li key={problem} className="text-2xs text-muted-foreground">
            {problem}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** What the resolver did. Shown after an apply, because the pairing it completed may have
    been claimed by a file somebody uploaded weeks ago and nothing else would say so. */
function LinkOutcome({ links }: { links: OrderLinkResolution }) {
  return (
    <section aria-label="Order links" className="rounded-lg border border-border p-3">
      <h4 className="text-xs font-semibold">Sales order to purchase order links</h4>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <CountTile label="Resolved now" value={links.resolved} />
        <CountTile label="Still waiting" value={links.still_open} />
        <CountTile label="Examined" value={links.examined} />
      </div>
    </section>
  );
}

function HistorySummary({
  data,
  applied,
}: {
  data: PurchaseHistoryPreview;
  applied?: PurchaseHistoryResult;
}) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <CountTile label="Orders" value={data.orders} />
          <CountTile label={applied ? 'Orders written' : 'New'} value={applied ? applied.orders_created : data.orders_new} />
          <CountTile label="Already held" value={data.orders_existing} />
          <CountTile label={applied ? 'Lines written' : 'Lines'} value={applied ? applied.lines_created : data.lines} />
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

function InquirySummary({
  data,
  applied,
}: {
  data: OrderInquiryPreview;
  applied?: OrderInquiryResult;
}) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <CountTile label="Rows" value={data.rows} />
          <CountTile label="Matched" value={data.lines_matched} />
          <CountTile
            label={applied ? 'Locations written' : 'With a location'}
            value={applied ? applied.locations_written : data.with_location}
          />
          <CountTile
            label={applied ? 'Links claimed' : 'PO links'}
            value={applied ? applied.claims_written : data.po_claims}
          />
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
  /** Fired once the write succeeds, so the page can refresh what it derives from it. */
  onApplied?: (result: PurchaseHistoryResult | OrderInquiryResult) => void;
}

export function HistoryUploadDialog({
  open,
  onOpenChange,
  kind,
  onApplied,
}: HistoryUploadDialogProps) {
  const isHistory = kind === 'purchase-history';
  const copy = COPY[kind];

  const upload = useTwoStepUpload<
    PurchaseHistoryPreview | OrderInquiryPreview,
    PurchaseHistoryResult | OrderInquiryResult
  >({
    open,
    preview: (file) => (isHistory ? previewPurchaseHistory(file) : previewOrderInquiry(file)),
    apply: (file) => (isHistory ? applyPurchaseHistory(file) : applyOrderInquiry(file)),
    onApplied,
  });

  const { file, preview, result, previewing, applying, error } = upload;
  const shown = result ?? preview;

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

          {result ? <p className="text-sm font-medium">Upload applied.</p> : null}

          {!result ? (
            <>
              <FileDropzone
                files={file ? [file] : []}
                onFilesChange={(next) => void upload.choose(next[0] ?? null)}
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
            </>
          ) : null}

          {shown && !shown.ok ? <Problems problems={shown.problems} /> : null}

          {shown && shown.ok ? (
            <>
              {isHistory ? (
                <HistorySummary
                  data={shown as PurchaseHistoryPreview}
                  applied={result ? (result as PurchaseHistoryResult) : undefined}
                />
              ) : (
                <InquirySummary
                  data={shown as OrderInquiryPreview}
                  applied={result ? (result as OrderInquiryResult) : undefined}
                />
              )}
              {result ? <LinkOutcome links={result.links} /> : null}
            </>
          ) : null}
        </DialogBody>

        <DialogFooter>
          {result ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
                Cancel
              </Button>
              <Button onClick={() => void upload.confirm()} disabled={!upload.canConfirm}>
                {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
                Confirm upload
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default HistoryUploadDialog;
