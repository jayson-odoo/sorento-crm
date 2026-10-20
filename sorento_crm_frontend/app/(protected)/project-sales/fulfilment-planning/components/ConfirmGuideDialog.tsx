'use client';

import * as React from 'react';
import { Split } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { WizardSteps, type WizardStep } from '@/components/common/WizardSteps';
import {
  SplitLinesSheet,
  splitDateText,
} from '../../_shared/components/LineSplitInfo';
import { VERB_LABEL } from '../../_shared/components/OrderInquiryVerbPill';
import { useLineSplits } from '../../_shared/hooks/useLineSplits';
import { formatQty } from '../../_shared/lib/money';
import type {
  AutocountChange,
  PreviewInquiryRow,
  PreviewTransfer,
} from '../../_shared/types/fulfilmentPlanning.types';
import { LineSplitDialog } from './LineSplitDialog';

/** One Split page (UAC B1): an order of this Confirm with at least one saved split edit. */
export interface ConfirmGuideSplitPage {
  psoId: string;
  soNumber: string;
  /** The order's saved split edits this Confirm applies (the board's "Split edits to confirm"). */
  lineIds: string[];
}

/** One order of the Review step (UAC C2, C5), off the dry run's answer. */
export interface ConfirmGuideReviewOrder {
  psoId: string;
  soNumber: string;
  rows: PreviewInquiryRow[];
  transfers: PreviewTransfer[];
  /** Why the order is left out of step 3 (the dry run refused it); null when it goes on. */
  refusal: string | null;
}

/**
 * What the board's dry run answered: the press step 3 hands over (`prepared`, given back to
 * `runPost` untouched) and the Review rows, or every order refused (UAC C7), in which case
 * `settle` puts today's result card up and the guide closes.
 */
export type ConfirmGuidePreview<P> =
  | { kind: 'ready'; prepared: P; review: ConfirmGuideReviewOrder[] }
  | { kind: 'closed'; settle: () => void };

/** UAC C4: the plain label of a row the AutoCount book forced, from the server's cause. */
const AUTOCOUNT_LABEL: Record<AutocountChange, string> = {
  cancelled: 'AutoCount cancelled',
  qty: 'AutoCount changed qty',
  date: 'AutoCount changed date',
  qty_date: 'AutoCount changed qty and date',
};

/** UAC F1/F2: as wide as the sheet needs on a desktop, full screen on a phone. */
const GUIDE_DIALOG_CLASS =
  'gap-0 overflow-hidden p-0 md:inset-6 md:mx-auto md:max-w-[1180px] max-md:inset-0 max-md:rounded-none';

type Step = { kind: 'split'; index: number } | { kind: 'review' } | { kind: 'confirm' };

type ReviewState<P> =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; prepared: P; orders: ConfirmGuideReviewOrder[] };

const plural = (count: number, one: string, many = `${one}s`) =>
  `${count} ${count === 1 ? one : many}`;

/** The remark cell: the row's verb in the words the board prints; a retired row reads CANCEL. */
function remarkOf(row: PreviewInquiryRow): string {
  if (row.state === 'cancelled') return 'CANCEL';
  return VERB_LABEL[row.verb] ?? row.verb;
}

/** A read that failed, said in place with a Retry (never a skeleton forever). */
function Failure({
  testId,
  retryTestId,
  error,
  fallback,
  onRetry,
}: {
  testId: string;
  retryTestId: string;
  error: unknown;
  fallback: string;
  onRetry: () => void;
}) {
  return (
    <div data-testid={testId} className="flex flex-col items-start gap-2 py-4 text-sm">
      <span role="alert" className="break-words">
        {(error instanceof Error && error.message) || fallback}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-testid={retryTestId}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}

const TH = 'border-b border-border px-2.5 py-2 text-start font-medium whitespace-nowrap';
const TD = 'border-b border-border px-2.5 py-2 align-middle whitespace-nowrap';

/** One order of the Review step: its rows to purchasing and its transfers, or why it is left out. */
function ReviewOrder({ order }: { order: ConfirmGuideReviewOrder }) {
  return (
    <section
      data-testid="confirm-guide-review-order"
      data-so={order.soNumber}
      className="space-y-2"
    >
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="text-base font-semibold">{order.soNumber}</span>
        {order.refusal === null && order.rows.length > 0 ? (
          <span className="text-xs text-muted-foreground">
            {`${plural(order.rows.length, 'row')} to purchasing`}
          </span>
        ) : null}
      </div>
      {order.refusal !== null ? (
        <p data-testid="confirm-guide-refused" className="text-sm break-words text-destructive">
          {order.refusal}
        </p>
      ) : order.rows.length === 0 ? (
        <p data-testid="confirm-guide-nothing" className="text-sm text-muted-foreground">
          Nothing to send to purchasing
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] border-separate border-spacing-0 text-xs [&_tr:last-child>td]:border-b-0">
            <thead className="bg-muted/40 text-muted-foreground">
              <tr>
                <th className={TH}>Line</th>
                <th className={TH}>Item code</th>
                <th className={TH}>Location</th>
                <th className={`${TH} text-end`}>Qty</th>
                <th className={TH}>Delivery date</th>
                <th className={TH}>Remark</th>
              </tr>
            </thead>
            <tbody>
              {order.rows.map((row, index) => {
                const label = row.autocount_change
                  ? AUTOCOUNT_LABEL[row.autocount_change]
                  : null;
                return (
                  <tr key={`${row.line_no ?? ''}-${index}`} data-testid="confirm-guide-review-row">
                    <td className={`${TD} tabular-nums`}>{row.line_no ?? ''}</td>
                    <td className={`${TD} font-medium`}>{row.item_code ?? ''}</td>
                    <td className={TD}>{row.stock_location ?? ''}</td>
                    <td className={`${TD} text-end tabular-nums`}>{formatQty(String(row.qty))}</td>
                    <td className={`${TD} tabular-nums`}>{splitDateText(row.delivery_date)}</td>
                    <td className={TD}>
                      <span className="inline-flex items-center gap-1.5">
                        <span>{remarkOf(row)}</span>
                        {label ? (
                          <Badge
                            data-testid="confirm-guide-autocount"
                            variant="info"
                            appearance="light"
                            size="sm"
                          >
                            {label}
                          </Badge>
                        ) : null}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {order.refusal === null && order.transfers.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[480px] border-separate border-spacing-0 text-xs [&_tr:last-child>td]:border-b-0">
            <thead className="bg-muted/40 text-muted-foreground">
              <tr>
                <th className={TH}>Line</th>
                <th className={TH}>Transfer</th>
                <th className={`${TH} text-end`}>Qty</th>
                <th className={TH}>From</th>
                <th className={TH}>To</th>
              </tr>
            </thead>
            <tbody>
              {order.transfers.map((move, index) => (
                <tr key={`${move.line_no ?? ''}-${index}`}>
                  <td className={`${TD} tabular-nums`}>{move.line_no ?? ''}</td>
                  <td className={TD}>{move.kind}</td>
                  <td className={`${TD} text-end tabular-nums`}>{formatQty(String(move.qty))}</td>
                  <td className={TD}>{move.from_location ?? ''}</td>
                  <td className={TD}>{move.to_location ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

/**
 * OI-SPLIT-GUIDE: Confirm (N) on the planning board, step by step (UAC A to D). Split shows
 * each order's saved split edits read-only, with today's edit sheet one button away; Review
 * runs the dry run today's press already makes and lists every row purchasing will get;
 * Confirm posts what that dry run answered, through the board's own press.
 *
 * The board owns the press: `runPreview` is its build plus dry run, `runPost` its post plus
 * result card and toast. The guide only walks the steps and draws what they answer.
 */
export function ConfirmGuideDialog<P>({
  soNumbers,
  splitPages,
  runPreview,
  runPost,
  onClose,
}: {
  /** The orders of this Confirm, in board order (UAC A3). */
  soNumbers: string[];
  /** Orders with a saved split edit, in board order; re-read live, so a page drops once saved back. */
  splitPages: ConfirmGuideSplitPage[];
  runPreview: () => Promise<ConfirmGuidePreview<P>>;
  /** Resolves true once posted (the guide closes), false when the post failed (it stays). */
  runPost: (prepared: P) => Promise<boolean>;
  onClose: () => void;
}) {
  // The step row keeps the shape it opened with: a page saved away does not renumber it.
  const [withSplit] = React.useState(() => splitPages.length > 0);
  const [step, setStep] = React.useState<Step>(() =>
    splitPages.length > 0 ? { kind: 'split', index: 0 } : { kind: 'review' },
  );
  const [review, setReview] = React.useState<ReviewState<P>>({ status: 'loading' });
  const [posting, setPosting] = React.useState(false);
  /** The order whose edit sheet is open on top of the guide (UAC B4). */
  const [editing, setEditing] = React.useState<{ psoId: string; open: boolean } | null>(null);
  // Each entry into Review gets a number; an answer for an entry the guide has since left
  // (Back, Cancel, a fresh entry) is dropped.
  const entryRef = React.useRef(0);

  const page = step.kind === 'split' ? splitPages[step.index] : undefined;
  const { query: splitRead } = useLineSplits(page?.psoId, Boolean(page));

  const startReview = React.useCallback(() => {
    entryRef.current += 1;
    const entry = entryRef.current;
    setStep({ kind: 'review' });
    setReview({ status: 'loading' });
    runPreview().then(
      (outcome) => {
        if (entryRef.current !== entry) return;
        if (outcome.kind === 'closed') {
          // UAC C7: nothing to post; the board shows today's result card instead.
          outcome.settle();
          onClose();
          return;
        }
        setReview({ status: 'ready', prepared: outcome.prepared, orders: outcome.review });
      },
      (error: unknown) => {
        if (entryRef.current !== entry) return;
        setReview({ status: 'error', error });
      },
    );
  }, [runPreview, onClose]);

  // UAC B6: no Split step, so the guide opens straight onto Review. Once, on open.
  const openedRef = React.useRef(false);
  React.useEffect(() => {
    if (openedRef.current) return;
    openedRef.current = true;
    if (step.kind === 'review') startReview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // UAC B4: a Save that left the last page's order with no saved edit drops the page; the
  // guide moves on to Review (an earlier page's drop shows the next order by index alone).
  React.useEffect(() => {
    if (step.kind === 'split' && step.index >= splitPages.length) startReview();
  }, [step, splitPages.length, startReview]);

  const close = React.useCallback(() => {
    if (posting) return;
    entryRef.current += 1;
    onClose();
  }, [posting, onClose]);

  const next = () => {
    if (step.kind === 'split') {
      if (step.index + 1 < splitPages.length) setStep({ kind: 'split', index: step.index + 1 });
      else startReview();
    } else if (step.kind === 'review' && review.status === 'ready') {
      setStep({ kind: 'confirm' });
    }
  };
  const back = () => {
    if (step.kind === 'split') {
      if (step.index > 0) setStep({ kind: 'split', index: step.index - 1 });
    } else if (step.kind === 'review') {
      entryRef.current += 1;
      if (splitPages.length > 0) setStep({ kind: 'split', index: splitPages.length - 1 });
    } else {
      startReview();
    }
  };
  const post = async () => {
    if (review.status !== 'ready' || posting) return;
    setPosting(true);
    const ok = await runPost(review.prepared);
    if (ok) {
      onClose();
      return;
    }
    setPosting(false);
  };

  const steps: WizardStep[] = [
    ...(withSplit ? [{ id: 'split', label: 'Split' }] : []),
    { id: 'review', label: 'Review' },
    { id: 'confirm', label: 'Confirm' },
  ];
  const canBack =
    step.kind === 'split'
      ? step.index > 0
      : step.kind === 'review'
        ? splitPages.length > 0
        : true;
  const nextLabel =
    step.kind === 'split'
      ? step.index + 1 < splitPages.length
        ? 'Next order'
        : 'Next: Review'
      : step.kind === 'review'
        ? 'Next: Confirm'
        : null;
  const nextEnabled =
    step.kind === 'split' ? Boolean(page) && !splitRead.isError : review.status === 'ready';
  // Step 3's orders: every order of the dry run it did not refuse (UAC C5, D1).
  const confirming =
    review.status === 'ready' ? review.orders.filter((order) => order.refusal === null) : [];

  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent
          data-testid="confirm-guide"
          variant="fullscreen"
          className={GUIDE_DIALOG_CLASS}
          aria-describedby={undefined}
        >
          <DialogHeader className="mb-0 space-y-2 border-b border-border px-5 pt-4 pb-3 pe-12 text-start sm:text-start">
            <DialogTitle className="truncate text-base">
              {`Confirm ${soNumbers.join(', ')}`}
            </DialogTitle>
            <div data-testid="confirm-guide-steps">
              <WizardSteps steps={steps} currentId={step.kind} />
            </div>
            {step.kind === 'split' && splitPages.length > 1 && page ? (
              <p className="text-xs text-muted-foreground">
                {`Order ${step.index + 1} of ${splitPages.length}`}
              </p>
            ) : null}
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-5 py-4">
            {step.kind === 'split' && page ? (
              <section
                data-testid="confirm-guide-split-page"
                data-so={page.soNumber}
                className="space-y-3"
              >
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2">
                  <span className="text-base font-semibold">{page.soNumber}</span>
                  <Badge variant="warning" appearance="light" size="sm">
                    Saved, not confirmed
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {plural(page.lineIds.length, 'split line')}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="max-md:w-full md:ms-auto"
                    data-testid="confirm-guide-split-edit"
                    onClick={() => setEditing({ psoId: page.psoId, open: true })}
                  >
                    <Split className="size-4" aria-hidden />
                    {`Split delivery ${page.soNumber}`}
                  </Button>
                </div>
                {splitRead.isError ? (
                  <Failure
                    testId="confirm-guide-split-error"
                    retryTestId="confirm-guide-split-retry"
                    error={splitRead.error}
                    fallback="The split sheet could not be loaded."
                    onRetry={() => void splitRead.refetch()}
                  />
                ) : splitRead.isPending ? (
                  <SectionSkeleton rows={4} />
                ) : (
                  <div className="overflow-hidden rounded-lg border border-border">
                    <SplitLinesSheet payload={splitRead.data ?? null} lineIds={page.lineIds} />
                  </div>
                )}
              </section>
            ) : null}

            {step.kind === 'review' ? (
              <div data-testid="confirm-guide-review" className="space-y-5">
                {review.status === 'loading' ? <SectionSkeleton rows={4} /> : null}
                {review.status === 'error' ? (
                  <Failure
                    testId="confirm-guide-review-error"
                    retryTestId="confirm-guide-review-retry"
                    error={review.error}
                    fallback="The dry run could not be run."
                    onRetry={startReview}
                  />
                ) : null}
                {review.status === 'ready'
                  ? review.orders.map((order) => (
                      <ReviewOrder key={`${order.psoId}-${order.soNumber}`} order={order} />
                    ))
                  : null}
              </div>
            ) : null}

            {step.kind === 'confirm' ? (
              <div className="space-y-3">
                <p className="text-sm break-words">
                  {`${plural(confirming.length, 'order')}: ${confirming
                    .map((order) => `${order.soNumber} (${plural(order.rows.length, 'row')})`)
                    .join(', ')}. Nothing has been sent yet.`}
                </p>
                <Button
                  type="button"
                  data-testid="confirm-guide-confirm"
                  disabled={posting}
                  onClick={() => void post()}
                >
                  {`Confirm ${plural(confirming.length, 'order')}`}
                </Button>
              </div>
            ) : null}
          </div>

          <div className="flex items-center gap-2 border-t border-border px-5 py-3">
            <Button
              type="button"
              variant="outline"
              data-testid="confirm-guide-cancel"
              disabled={posting}
              onClick={close}
            >
              Cancel
            </Button>
            <span className="flex-1" />
            {canBack ? (
              <Button
                type="button"
                variant="outline"
                data-testid="confirm-guide-back"
                disabled={posting}
                onClick={back}
              >
                Back
              </Button>
            ) : null}
            {nextLabel ? (
              <Button
                type="button"
                data-testid="confirm-guide-next"
                disabled={!nextEnabled}
                onClick={next}
              >
                {nextLabel}
              </Button>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
      {editing ? (
        <LineSplitDialog
          open={editing.open}
          psoId={editing.psoId}
          onOpenChange={(open) =>
            setEditing((current) => (current ? { ...current, open } : current))
          }
        />
      ) : null}
    </>
  );
}
