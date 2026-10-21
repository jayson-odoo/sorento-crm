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
import { LineSplitEditor, type LineSplitEditorHandle } from './LineSplitEditor';
import { formatSplitDate } from '../lib/lineSplitModel';

/** One line this Confirm covers, as the board states it, with its editable remark (UAC F25). */
export type ConfirmGuideLine = CoveredSheetLine & {
  /** The planner's own remark kept in the line's saved decision; null = the default words. */
  ownRemark: string | null;
  /** The line's remark can be kept in a saved decision (an Approve or Amend draft). */
  remarkEditable: boolean;
};

/** One page of the guide (UAC F2): an order this Confirm covers, and the lines it covers. */
export interface ConfirmGuidePage {
  /** The order's planning record; null until the press adopts it (nothing to read yet). */
  psoId: string | null;
  /** The core sales order: what the board adopts when the page has no planning record yet. */
  salesOrderId: string;
  soNumber: string;
  /** The board's SO date for the order (`YYYY-MM-DD`); null when the board has none. */
  soDate?: string | null;
  /** The lines this Confirm covers on the order, as the board states them (UAC F2, F10). */
  covered: ConfirmGuideLine[];
}

/** A read-only row prints the planner's own remark, else the default words (UAC F25). */
const readOnlyWords = (line: ConfirmGuideLine): CoveredSheetLine => ({
  ...line,
  savedRemark: line.ownRemark || line.savedRemark,
});

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
  autocountNote = [],
  applyLabel = 'Apply AutoCount change',
  runConfirm,
  saveRemarks,
  preparing = false,
  prepareErrors,
  onRetryPrepare,
  onClose,
}: {
  /** The orders of this Confirm, in board order; re-read live, so a page drops once saved away. */
  pages: ConfirmGuidePage[];
  /**
   * PLAN-BATCH-COUNT-DISPLAY (reviewer round 1): the board's AutoCount change note, said again on
   * the Confirm step. With no page (no decision, only pending changes) it is the whole press, and
   * the title and button read `applyLabel` instead of "Confirm 0 orders".
   */
  autocountNote?: string[];
  applyLabel?: string;
  runConfirm: () => Promise<boolean>;
  /**
   * UAC F26: keeps saved lines' remarks in their saved decisions (board line key -> remark,
   * '' = the default words); rejects when one could not be saved.
   */
  saveRemarks: (changes: ReadonlyMap<string, string>) => Promise<void>;
  /**
   * OI-SPLIT-CONFIRM-POLISH (owner, SO426939): the board is giving the orders with no planning
   * record one (so their page is the editable sheet, never the read-only one), or that failed.
   */
  preparing?: boolean;
  /** Per core sales order id: why it could not be made ready (the server's sentence). */
  prepareErrors?: ReadonlyMap<string, string>;
  onRetryPrepare?: () => void;
  onClose: () => void;
}) {
  const [step, setStep] = React.useState<Step>(() =>
    pages.length > 0 ? { kind: 'review', index: 0 } : { kind: 'confirm' },
  );
  const [posting, setPosting] = React.useState(false);
  /** UAC F19: the page's editor holds unsaved split edits. */
  const [dirty, setDirty] = React.useState(false);
  /** UAC F23: the page's editor, asked whether Escape or a click outside may close. */
  const editorRef = React.useRef<LineSplitEditorHandle | null>(null);

  const page = step.kind === 'review' ? pages[step.index] : undefined;
  // Every page's split read, kept while the guide is open; the current page reads its own.
  const reads = useLineSplitsReads(pages.map((entry) => entry.psoId));
  const splitRead = step.kind === 'review' && page ? reads[step.index] : undefined;
  const reading = Boolean(page?.psoId) && Boolean(splitRead?.isPending);
  // A page with no planning record waits for the board's adopt, never shown read-only while it
  // runs. Only a FAILED adopt leaves its lines read-only, under the error and its Retry, and
  // the guide can still move on: the press names that order in its results, and one order
  // that cannot be planned never holds up the others.
  const unready = Boolean(page && !page.psoId && preparing);
  const prepareError =
    page && !page.psoId && !preparing ? prepareErrors?.get(page.salesOrderId) ?? null : null;
  const prepareFailed = Boolean(prepareError);
  const readFailed = Boolean(splitRead?.isError);
  // OI-SPLIT-CONFIRM-POLISH (owner, SO426939): the ONE SO date every sheet on the page prints:
  // the order's split read, else the board's (an order nobody adopted has no read at all).
  const soDate = splitRead?.data?.so_date ?? page?.soDate ?? null;
  const sheetHead = page ? { so_number: page.soNumber, so_date: soDate } : null;
  // The page's sheet: split lines from the split read, every other covered line one row.
  const sheet = React.useMemo(
    () =>
      page && !reading && !readFailed && !unready
        ? coveredSheetLines(splitRead?.data ?? null, page.covered.map(readOnlyWords))
        : null,
    [page, reading, readFailed, unready, splitRead?.data],
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
      remarks: new Map(
        page.covered.flatMap((line) =>
          line.lineId
            ? [
                [
                  line.lineId,
                  { words: line.savedRemark, own: line.ownRemark, editable: line.remarkEditable },
                ] as const,
              ]
            : [],
        ),
      ) as ReadonlyMap<string, { words: string | null; own: string | null; editable: boolean }>,
      keyOf: new Map(
        page.covered.flatMap((line) => (line.lineId ? [[line.lineId, line.key] as const] : [])),
      ) as ReadonlyMap<string, string>,
      rest: coveredSheetLines(
        null,
        page.covered
          .filter((line) => !line.lineId || !read.has(line.lineId))
          .map(readOnlyWords),
      ),
    };
  }, [page, reading, readFailed, splitRead?.data]);

  // UAC B4: a Save that left the last page's order out of this Confirm drops its page; the
  // guide moves on to the Confirm step (an earlier page's drop shows the next order by index).
  React.useEffect(() => {
    if (step.kind === 'review' && step.index >= pages.length) setStep({ kind: 'confirm' });
  }, [step, pages.length]);

  /**
   * Cancel: the explicit way out, which confirms and sends nothing (UAC A2, F23). An order the
   * guide adopted as it opened keeps its planning record (OI-SPLIT-CONFIRM-POLISH, owner).
   */
  const close = React.useCallback(() => {
    if (posting) return;
    onClose();
  }, [posting, onClose]);
  /**
   * UAC F23: Escape or a click outside never closes the guide while a split row is being
   * dragged (Escape puts the drag back) or while the page has unsaved split edits (the
   * "Save or undo your split changes first" line is already showing); the board's dialog
   * guards the same way.
   */
  const requestClose = () => {
    if (editorRef.current?.isDragging() || editorRef.current?.isDirty()) return;
    close();
  };

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
    step.kind === 'review' && Boolean(page) && !reading && !readFailed && !unready && !dirty;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) requestClose();
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
            {pages.length > 0
              ? `Confirm ${pages.map((entry) => entry.soNumber).join(', ')}`
              : applyLabel}
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
                {/* Owner ruling (21 Oct): a phone hides the SO DATE column, so the page header
                    says it, from the same one SO date every sheet prints. */}
                {soDate ? (
                  <span
                    data-testid="confirm-guide-so-date"
                    className="text-xs text-muted-foreground tabular-nums md:hidden"
                  >
                    {formatSplitDate(soDate)}
                  </span>
                ) : null}
                <Badge variant="warning" appearance="light" size="sm">
                  Saved, not confirmed
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {plural(sheet ? sheet.lines.length : page.covered.length, 'line')}
                </span>
              </div>
              {prepareFailed ? (
                <div
                  data-testid="confirm-guide-prepare-error"
                  className="flex flex-col items-start gap-2 text-sm"
                >
                  <span role="alert" className="break-words">
                    {prepareError}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onRetryPrepare}
                  >
                    Retry
                  </Button>
                </div>
              ) : null}
              {unready ? (
                <SectionSkeleton rows={4} />
              ) : readFailed ? (
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
                      lineRemarks={editable.remarks}
                      // OI-SPLIT-CONFIRM-POLISH: no drag-to-reorder on the Review split page.
                      canDrag={false}
                      onSaveRemarks={(changes) =>
                        saveRemarks(
                          new Map(
                            [...changes].flatMap(([lineId, remark]) => {
                              const key = editable.keyOf.get(lineId);
                              return key ? [[key, remark] as const] : [];
                            }),
                          ),
                        )
                      }
                      readLoaded
                      stayAfterSave
                      onDirtyChange={setDirty}
                      handleRef={editorRef}
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
                        payload={sheetHead}
                        soNumber={page.soNumber}
                        sheet={editable.rest}
                      />
                    </div>
                  ) : null}
                </>
              ) : sheet ? (
                <div className="overflow-hidden rounded-lg border border-border">
                  <SplitLinesSheet
                    payload={sheetHead}
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
              {pages.length > 0 ? (
                <p className="text-sm break-words">
                  {`${plural(pages.length, 'order')}: ${pages
                    .map((entry) => `${entry.soNumber} (${plural(entry.covered.length, 'line')})`)
                    .join(', ')}. Nothing has been sent yet.`}
                </p>
              ) : null}
              {autocountNote.map((line) => (
                <p key={line} className="text-sm break-words">
                  {line}
                </p>
              ))}
              {pages.length === 0 ? (
                <p className="text-sm break-words">Nothing has been sent yet.</p>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* OI-SPLIT-CONFIRM-POLISH (owner, 21 Oct): Cancel far left; the step's action at the
            right, Back immediately left of it. */}
        <div
          data-testid="confirm-guide-footer"
          className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-3"
        >
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
          ) : (
            <Button
              type="button"
              data-testid="confirm-guide-confirm"
              disabled={posting}
              onClick={() => void pressConfirm()}
            >
              {pages.length > 0 ? `Confirm ${plural(pages.length, 'order')}` : applyLabel}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
