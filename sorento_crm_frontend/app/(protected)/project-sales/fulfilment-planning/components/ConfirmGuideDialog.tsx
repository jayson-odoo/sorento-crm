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
  coveredSheetLines,
  type CoveredSheetLine,
} from '../../_shared/components/LineSplitInfo';
import { useLineSplitsReads } from '../../_shared/hooks/useLineSplits';
import { LineSplitDialog } from './LineSplitDialog';

/** One page of the guide (UAC F2): an order this Confirm covers, and the lines it covers. */
export interface ConfirmGuidePage {
  /** The order's planning record; null until the press adopts it (nothing to read yet). */
  psoId: string | null;
  soNumber: string;
  /** The lines this Confirm covers on the order, as the board states them (UAC F2, F10). */
  covered: CoveredSheetLine[];
}

/** UAC F1: the two steps. */
const STEPS: readonly WizardStep[] = [
  { id: 'review', label: 'Review split' },
  { id: 'confirm', label: 'Confirm' },
];

/** As wide as the sheet needs on a desktop, full screen on a phone. */
const GUIDE_DIALOG_CLASS =
  'gap-0 overflow-hidden p-0 md:inset-6 md:mx-auto md:max-w-[1180px] max-md:inset-0 max-md:rounded-none';

type Step = { kind: 'review'; index: number } | { kind: 'confirm' };

const plural = (count: number, one: string, many = `${one}s`) =>
  `${count} ${count === 1 ? one : many}`;

/**
 * OI-SPLIT-GUIDE: Confirm (N) on the planning board, step by step (UAC A, F). Review split
 * walks one page per order this Confirm covers: the #1794 read-only split sheet of exactly
 * the lines it covers, an unsplit line reading the purchasing email's words for its saved
 * decision, with today's edit sheet one button away. Confirm then runs today's press.
 *
 * The board owns the press: `runConfirm` is it, unchanged (silent dry run, narrowing, post,
 * result card, toast), resolving false only when a call failed, so the guide stays open.
 */
export function ConfirmGuideDialog({
  pages,
  runConfirm,
  onClose,
}: {
  /** The orders of this Confirm, in board order; re-read live, so a page drops once saved away. */
  pages: ConfirmGuidePage[];
  runConfirm: () => Promise<boolean>;
  onClose: () => void;
}) {
  const [step, setStep] = React.useState<Step>(() =>
    pages.length > 0 ? { kind: 'review', index: 0 } : { kind: 'confirm' },
  );
  const [posting, setPosting] = React.useState(false);
  /** The order whose edit sheet is open on top of the guide (UAC B4). */
  const [editing, setEditing] = React.useState<{
    psoId: string;
    open: boolean;
    /** UAC F13: the page's covered lines, the only ones the edit sheet lists. */
    lineIds: ReadonlySet<string>;
  } | null>(null);

  const page = step.kind === 'review' ? pages[step.index] : undefined;
  // Every page's split read, kept while the guide is open; the current page reads its own.
  const reads = useLineSplitsReads(pages.map((entry) => entry.psoId));
  const splitRead = step.kind === 'review' && page ? reads[step.index] : undefined;
  const reading = Boolean(page?.psoId) && Boolean(splitRead?.isPending);
  const readFailed = Boolean(splitRead?.isError);
  // The page's sheet: split lines from the split read, every other covered line one row.
  const sheet = React.useMemo(
    () =>
      page && !reading && !readFailed
        ? coveredSheetLines(splitRead?.data ?? null, page.covered)
        : null,
    [page, reading, readFailed, splitRead?.data],
  );

  // UAC B4: a Save that left the last page's order out of this Confirm drops its page; the
  // guide moves on to the Confirm step (an earlier page's drop shows the next order by index).
  React.useEffect(() => {
    if (step.kind === 'review' && step.index >= pages.length) setStep({ kind: 'confirm' });
  }, [step, pages.length]);

  const close = React.useCallback(() => {
    if (posting) return;
    onClose();
  }, [posting, onClose]);

  const next = () => {
    if (step.kind !== 'review') return;
    setStep(
      step.index + 1 < pages.length ? { kind: 'review', index: step.index + 1 } : { kind: 'confirm' },
    );
  };
  const back = () => {
    if (step.kind === 'review') {
      if (step.index > 0) setStep({ kind: 'review', index: step.index - 1 });
    } else if (pages.length > 0) {
      setStep({ kind: 'review', index: pages.length - 1 });
    }
  };
  const pressConfirm = async () => {
    if (posting) return;
    setPosting(true);
    if (await runConfirm()) {
      onClose();
      return;
    }
    setPosting(false);
  };

  const canBack = step.kind === 'review' ? step.index > 0 : pages.length > 0;
  const nextLabel =
    step.kind === 'review'
      ? step.index + 1 < pages.length
        ? 'Next order'
        : 'Next: Confirm'
      : null;
  // UAC F14: a page is never "seen" before its split read has loaded.
  const nextEnabled =
    step.kind === 'review' && Boolean(page) && !reading && !readFailed;

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
              {`Confirm ${pages.map((entry) => entry.soNumber).join(', ')}`}
            </DialogTitle>
            <div data-testid="confirm-guide-steps">
              <WizardSteps steps={STEPS} currentId={step.kind} />
            </div>
            {step.kind === 'review' && pages.length > 1 && page ? (
              <p className="text-xs text-muted-foreground">
                {`Order ${step.index + 1} of ${pages.length}`}
              </p>
            ) : null}
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-5 py-4">
            {page ? (
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
                    {plural(sheet ? sheet.lines.length : page.covered.length, 'line')}
                  </span>
                  {page.psoId ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="max-md:w-full md:ms-auto"
                      data-testid="confirm-guide-split-edit"
                      onClick={() =>
                        page.psoId &&
                        setEditing({
                          psoId: page.psoId,
                          open: true,
                          lineIds: new Set(
                            page.covered.flatMap((line) => (line.lineId ? [line.lineId] : [])),
                          ),
                        })
                      }
                    >
                      <Split className="size-4" aria-hidden />
                      {`Split delivery ${page.soNumber}`}
                    </Button>
                  ) : null}
                </div>
                {readFailed ? (
                  <div
                    data-testid="confirm-guide-split-error"
                    className="flex flex-col items-start gap-2 py-4 text-sm"
                  >
                    <span role="alert" className="break-words">
                      {(splitRead?.error instanceof Error && splitRead.error.message) ||
                        'The split sheet could not be loaded.'}
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      data-testid="confirm-guide-split-retry"
                      onClick={() => void splitRead?.refetch()}
                    >
                      Retry
                    </Button>
                  </div>
                ) : sheet ? (
                  <div className="overflow-hidden rounded-lg border border-border">
                    <SplitLinesSheet
                      payload={splitRead?.data ?? null}
                      soNumber={page.soNumber}
                      sheet={sheet}
                    />
                  </div>
                ) : (
                  <SectionSkeleton rows={4} />
                )}
              </section>
            ) : null}

            {step.kind === 'confirm' ? (
              <div className="space-y-3">
                <p className="text-sm break-words">
                  {`${plural(pages.length, 'order')}: ${pages
                    .map((entry) => `${entry.soNumber} (${plural(entry.covered.length, 'line')})`)
                    .join(', ')}. Nothing has been sent yet.`}
                </p>
                <Button
                  type="button"
                  data-testid="confirm-guide-confirm"
                  disabled={posting}
                  onClick={() => void pressConfirm()}
                >
                  {`Confirm ${plural(pages.length, 'order')}`}
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
          onlyLineIds={editing.lineIds}
          onOpenChange={(open) =>
            setEditing((current) => (current ? { ...current, open } : current))
          }
        />
      ) : null}
    </>
  );
}
