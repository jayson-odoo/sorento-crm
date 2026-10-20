'use client';

import * as React from 'react';
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
import { LineSplitEditor } from './LineSplitEditor';

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
 * walks one page per order this Confirm covers, and the page IS the split editor (UAC F18):
 * the board's own `LineSplitEditor`, inline, scoped to the lines this Confirm covers, with
 * its own Save; an unsplit line reads the purchasing email's words for its saved decision.
 * An order nobody has adopted yet (no split read) and a covered line the read does not list
 * stay read-only rows. Confirm then runs today's press.
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
  /** UAC F19: the page's editor holds unsaved split edits. */
  const [dirty, setDirty] = React.useState(false);

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
  // UAC F18: what the page edits (covered lines the split read lists) and what stays a
  // read-only row (a covered line the read does not list, or every line with no read).
  const editable = React.useMemo(() => {
    const data = splitRead?.data;
    if (!page?.psoId || !data || reading || readFailed) return null;
    const read = new Set(data.lines.map((line) => line.line_id));
    const inRead = page.covered.filter((line) => line.lineId && read.has(line.lineId));
    if (inRead.length === 0) return null;
    return {
      psoId: page.psoId,
      onlyLineIds: new Set(inRead.map((line) => line.lineId as string)) as ReadonlySet<string>,
      words: new Map(
        page.covered.flatMap((line) =>
          line.lineId ? [[line.lineId, line.savedRemark] as const] : [],
        ),
      ) as ReadonlyMap<string, string | null>,
      rest: coveredSheetLines(
        null,
        page.covered.filter((line) => !line.lineId || !read.has(line.lineId)),
      ),
    };
  }, [page, reading, readFailed, splitRead?.data]);

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

  // UAC F19: an unsaved split edit is saved or undone before the guide moves on.
  const canBack = step.kind === 'review' ? step.index > 0 : pages.length > 0;
  const nextLabel =
    step.kind === 'review'
      ? step.index + 1 < pages.length
        ? 'Next order'
        : 'Next: Confirm'
      : null;
  // UAC F14: a page is never "seen" before its split read has loaded.
  const nextEnabled =
    step.kind === 'review' && Boolean(page) && !reading && !readFailed && !dirty;

  return (
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
              ) : editable ? (
                <>
                  {/* UAC F18: the board's split editor, inline and scoped to this page. */}
                  <div className="overflow-hidden rounded-lg border border-border">
                    <LineSplitEditor
                      key={editable.psoId}
                      psoId={editable.psoId}
                      active
                      onlyLineIds={editable.onlyLineIds}
                      savedRemarks={editable.words}
                      readLoaded
                      stayAfterSave
                      onDirtyChange={setDirty}
                      className="h-auto"
                      renderHeader={({ dirty: unsaved, canSave, saving, save, discard }) => (
                        <div className="flex items-center justify-end gap-2 border-b border-border px-3 py-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={!unsaved || saving}
                            onClick={discard}
                          >
                            Undo
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            disabled={!unsaved || !canSave}
                            onClick={save}
                          >
                            Save
                          </Button>
                        </div>
                      )}
                    />
                  </div>
                  {editable.rest.lines.length > 0 ? (
                    <div className="overflow-hidden rounded-lg border border-border">
                      <SplitLinesSheet
                        payload={null}
                        soNumber={page.soNumber}
                        sheet={editable.rest}
                      />
                    </div>
                  ) : null}
                </>
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

        <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3">
          {dirty ? (
            <p className="w-full text-xs text-muted-foreground">
              Save or undo your split changes first
            </p>
          ) : null}
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
              disabled={posting || dirty}
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
  );
}
