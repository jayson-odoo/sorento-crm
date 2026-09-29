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
  type LineNotFoundEntry,
  type LineNotFoundReason,
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
 * the Order Inquiry sheet, now the migration tool for the operator's own Excel: sales orders,
 * purchase orders and shipping orders already arrive from AutoCount in real time, what the
 * sheet still carries is which line the operator is waiting on and which PO or SPO for
 * (PLAN-scm-oi-sheet-migration.md).
 *
 * Test, then upload, with nothing at all running on file select. Confirm queues an import job
 * and the upload drawer follows it, because the resolve happens on the worker. So what the
 * upload DID is reported on the job page, not here.
 *
 * The flow itself is shared (`useTwoStepUpload`), so the sequence guard and the server-owned
 * accept list cannot drift between the dialogs.
 */

const TITLE = 'Upload order inquiry sheet';
const DESCRIPTION = 'Raises the sheet’s rows against the sales order line and its PO/SPO.';
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
 * `total`, where a list HAS one, is separate from `items.length`: the backend caps every one
 * of these lists at 200, and heading the section with the length of what it happens to be
 * showing turns 15,787 rows with no line into "(200)", which reads like a small, closed
 * problem. The count is the truth; the chips are a sample of it.
 *
 * Omitted, the heading carries NO count (review finding 11, 14 Sep). Two of the three lists
 * have only a capped sample to count - the server sends no total for them, and inventing one
 * from the sample is the very misreading above. No count key was added for them either: a
 * number nobody can act on is surface for nothing.
 */
function ChipList({
  title,
  items,
  total,
  hint,
  limit = CHIP_LIMIT,
}: {
  title: string;
  items: string[];
  total?: number;
  hint?: string;
  /** Caps how many chips show before the "+N more" tail. Most lists use `CHIP_LIMIT`; the
      no-matching-line list is denser text and asks for a taller cap (AC-S2-3). */
  limit?: number;
}) {
  if (!items.length) return null;
  const counted = Math.max(total ?? items.length, items.length);
  const hidden = counted - Math.min(items.length, limit);
  return (
    <div className="rounded-lg border border-border p-3">
      <h4 className="text-xs font-semibold">
        {title}
        {total === undefined ? '' : ` (${fmtInt(counted)})`}
      </h4>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {items.slice(0, limit).map((item, index) => (
          <span
            key={`${item}-${index}`}
            className="rounded bg-muted px-1.5 py-0.5 text-2xs font-mono"
          >
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

/**
 * The reason codes AC-S1-23 defines, in words - the chip list is read by a person, not a
 * parser, so the code itself never reaches the screen.
 *
 * Word for word the sentences `import_outcome_codes.LABELS` prints on the job page for the
 * same three codes (review finding 5, 14 Sep). They were paraphrased here, and two of the
 * paraphrases were wrong about the rule: the match takes a CLOSED line as readily as an open
 * one (D8), and the quantity it compares against is what the line ORDERED, not what is still
 * outstanding. Somebody reading the preview and then the job page has to see one answer.
 */
const LINE_NOT_FOUND_REASON: Record<LineNotFoundReason, string> = {
  no_line_for_item: 'No sales order line for this item',
  location_differs: 'No line for this item at that stock location',
  qty_exceeds_ordered: 'Quantity exceeds what the line ordered',
  order_fully_delivered: 'No line left: every line is cancelled',
};

/** `SO · item · qty · reason`, one per line (AC-S2-3). */
function formatLineNotFound(entry: LineNotFoundEntry): string {
  return `${entry.so_number} · ${entry.item_code} · ${fmtInt(entry.qty)} · ` +
    `${LINE_NOT_FOUND_REASON[entry.reason]}`;
}

/** How many chips the no-matching-line list shows before its "+N more" tail (AC-S2-3). */
const LINE_NOT_FOUND_LIMIT = 20;

function InquirySummary({ data }: { data: OrderInquiryPreview }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-8">
          <CountTile label="Rows" value={data.rows} />
          <CountTile label="Will raise" value={data.rows_raised} />
          <CountTile label="Already raised" value={data.rows_already_raised} />
          {/* Of "Already raised", not a separate count of rows: a migrated row's date
              corrected to the sheet's own, never a new row (18 Sep reversal). */}
          <CountTile label="Dates corrected" value={data.rows_delivery_date_updated} />
          <CountTile label="No SO line" value={data.rows_line_not_found} />
          {/* What Confirm does to the BOOK's neighbours, not only to the sheet: how many
              planning records it opens (security review SF2, AC-S2-8). */}
          <CountTile label="Orders adopted" value={data.orders_adopted} />
          {/* Per ROW, not per document: a row linked to two documents is one row the book
              answered for, and "Documents found" read as a count of documents (review
              finding 6). */}
          <CountTile label="Rows linked" value={data.links_written} />
          <CountTile label="Documents not found" value={data.documents_not_linkable.length} />
        </div>
        <p className="mt-1.5 text-2xs text-muted-foreground">
          {fmtInt(data.sheets_read.length)}{' '}
          {plural(data.sheets_read.length, 'sheet', 'sheets')} read
          {data.sheets_skipped.length
            ? `, ${fmtInt(data.sheets_skipped.length)} skipped`
            : ''}
          .
        </p>
      </div>

      <ChipList
        title="Sales orders not in the CRM"
        items={data.sales_orders_not_found}
      />
      <ChipList
        title="Documents we could not link"
        items={data.documents_not_linkable}
      />
      <ChipList
        title="Rows with no matching line"
        items={data.line_not_found.map(formatLineNotFound)}
        total={data.rows_line_not_found}
        limit={LINE_NOT_FOUND_LIMIT}
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

  // AC-S2-4: a preview that read fine but would raise nothing is not confirmable, even though
  // `useTwoStepUpload`'s own `canConfirm` never requires a Test - that generic rule stays for
  // the untested case, this narrows it once the preview says nothing would happen.
  const nothingToRaise = !!shown && shown.ok && shown.rows_raised === 0;
  const canConfirm = upload.canConfirm && !nothingToRaise;

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
          <Button onClick={() => void upload.confirm()} disabled={!canConfirm}>
            {applying ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
            Confirm upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default OrderInquiryUploadDialog;
