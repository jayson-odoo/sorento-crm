'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { useProject } from '../../../_shared/hooks/useProjects';
import {
  useDeliverySchedulePriorVersion,
  useDeliveryScheduleVersion,
  useDeliveryScheduleVersionMutations,
  useDeliveryScheduleVersionNeighbours,
} from '../../../_shared/hooks/useDeliverySchedules';
import { usePOVersion } from '../../../_shared/hooks/usePOIntake';
import { resolveExtractionPhase } from '../../../_shared/types/deliverySchedule.types';
import { describeReadingTime, describeWaitingFor } from '../../../_shared/lib/readingTime';
import type { DeliveryScheduleConfirmBody } from '../../../_shared/types/deliverySchedule.types';
import { ReconciliationBadge } from '../../components/DeliverySchedulesPanel';
import {
  demoScheduleVersionState,
  useDemoScheduleState,
} from '../_demo/scheduleDemo';
import {
  buildCellMap,
  buildCellMetaMap,
  buildColumnStates,
  cellMapKey,
  dateColumns as buildDateColumns,
  groupPhasesByArea,
  isQty,
  normaliseQty,
} from '../lib/scheduleTotals';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleByDateMatrix } from './DeliveryScheduleByDateMatrix';
import { DeliveryScheduleColumnCards } from './DeliveryScheduleColumnCards';
import { DeliveryScheduleConfirmDialog } from './DeliveryScheduleConfirmDialog';
import { DeliveryScheduleMatrix } from './DeliveryScheduleMatrix';
import type { ColumnFocusRequest, ScheduleGridController } from './DeliveryScheduleMatrix';
import { DeliveryScheduleNotes } from './DeliveryScheduleNotes';
import { poProductOptions } from './DeliveryScheduleProductPicker';
import { DeliveryScheduleReconciliationList } from './DeliveryScheduleReconciliationList';
import { DeliveryScheduleRevisionDiff } from './DeliveryScheduleRevisionDiff';
import { DeliveryScheduleRevisionProposals } from './DeliveryScheduleRevisionProposals';

/**
 * Reviewing one version of a delivery schedule.
 *
 * This is a reconciliation surface, not an accept-or-reject. Measured on the client's own two
 * documents, 29 of 37 and 35 of 38 columns reconciled on the first pass, so the job is to fix
 * the handful that did not: every column shows our total, the schedule's own TOTAL QTY and the
 * PO quantity side by side, and the ones that disagree are the work.
 */
export function DeliveryScheduleReviewClient({
  projectId,
  versionId,
}: {
  projectId: string;
  versionId: string;
}) {
  const demo = useDemoScheduleState();
  const project = useProject(demo ? undefined : projectId);
  const live = useDeliveryScheduleVersion(versionId, { enabled: !demo });
  const view = demo ? demoScheduleVersionState(demo) : live;
  const version = view.data;
  // Only once the read has finished. Beside a spinner a duration reads as the total,
  // which it is not yet.
  const readingTime =
    version && version.extraction_state !== 'queued' && version.extraction_state !== 'running'
      ? describeReadingTime(version.extraction_elapsed_ms)
      : null;

  const {
    saveCells,
    resolveProduct,
    dismissColumn,
    confirm,
    retryExtraction,
    acceptProposal,
    rejectProposal,
  } = useDeliveryScheduleVersionMutations(projectId, versionId);
  /** Which proposal a request is in flight for, so only its own card shows pending. */
  const [pendingProposalIndex, setPendingProposalIndex] = React.useState<number | null>(null);
  // The demo screen has no server behind it, so it has no neighbours to ask for either.
  const neighbours = useDeliveryScheduleVersionNeighbours(versionId, { enabled: !demo });
  // The version this one revises, for the was -> now diff. No-op on a version 1 or on demo.
  const priorVersion = useDeliverySchedulePriorVersion(version, { enabled: !demo });

  /**
   * The PO this schedule was checked against, for the column pickers.
   *
   * A column has to land on a line of THIS PO or it cannot reconcile, so the pickers offer
   * the PO's own products rather than the whole catalogue. Read once here rather than in
   * each picker: the three views mount a picker per unreconciled column and they would
   * otherwise ask for the same document a dozen times.
   */
  const poVersion = usePOVersion(version?.po_version_id ?? undefined, !demo);
  const poOptions = React.useMemo(
    () => poProductOptions(poVersion.data?.lines ?? []),
    [poVersion.data?.lines],
  );

  const [drafts, setDrafts] = React.useState<Map<string, string>>(new Map());
  const [learnedColumns, setLearnedColumns] = React.useState<number[]>([]);
  const [confirming, setConfirming] = React.useState(false);
  /**
   * The column a "Fix the quantities" press asked to be put INSIDE.
   *
   * Scrolling a column into view leaves the reviewer next to the thing they have to type in
   * rather than in it, which on a 38-column matrix still means hunting for the cell. The
   * nonce is what makes a second press of the same button fire again: the key alone would
   * be an unchanged value and the views would ignore it.
   */
  const [focusRequest, setFocusRequest] = React.useState<ColumnFocusRequest>(null);
  /**
   * A column has TWO nodes, not one: the matrix and the phone cards are both mounted and a
   * media query hides one of them. A single slot per column would hold whichever registered
   * last, so a reconciliation row clicked on a desktop would scroll to a `display: none`
   * card and appear to do nothing. Both are kept, and the one that is actually laid out is
   * chosen at click time.
   */
  const columnRefs = React.useRef<Map<string, Set<HTMLElement>>>(new Map());

  const phase = version ? resolveExtractionPhase(version) : 'queued';
  const canEdit =
    (demo ? true : (project.data?.can_edit ?? false)) && !version?.confirmed_at;

  const storedCells = React.useMemo(
    () => buildCellMap(version?.cells ?? []),
    [version?.cells],
  );
  const cellMeta = React.useMemo(
    () => buildCellMetaMap(version?.cells ?? []),
    [version?.cells],
  );

  /**
   * The document turned round by date rather than by phase (section 9.8). Built off the
   * whole cell list, not just what By date is currently showing, so the hint chip below can
   * count the moved cells even while By phase is the one on screen.
   */
  const [viewMode, setViewMode] = React.useState<'phase' | 'date'>('phase');
  const dateColumnsData = React.useMemo(
    () => buildDateColumns({ phases: version?.phases ?? [], cells: version?.cells ?? [] }),
    [version?.phases, version?.cells],
  );
  const overrideCount = React.useMemo(
    () => (version?.cells ?? []).filter((cell) => cell.delivery_date_override).length,
    [version?.cells],
  );

  const columns = React.useMemo(
    () =>
      buildColumnStates(
        version?.products ?? [],
        version?.phases ?? [],
        version?.cells ?? [],
        drafts,
      ),
    [version?.products, version?.phases, version?.cells, drafts],
  );

  const phaseGroups = React.useMemo(
    () => groupPhasesByArea(version?.phases ?? []),
    [version?.phases],
  );

  const blocking = React.useMemo(
    () => columns.filter((column) => !column.reconciled),
    [columns],
  );
  const reconciledCount = columns.length - blocking.length;
  /**
   * Everything worth a look: what blocks, what was dismissed, and what carries a warning.
   *
   * A dismissed column no longer blocks and stays here all the same: this is the only place
   * the dismissal and its reason are visible, and it is where the Undo lives. Dropping the
   * row the moment it stopped counting would leave a reviewer no way back from a decision
   * they had just taken.
   *
   * A warning is not work - the column agrees with the PO - but it is the one place the
   * sentence behind it can be read, so it is listed in the same table with an amber pill
   * rather than hidden among the thirty columns that had nothing to say. Filtered in ONE
   * pass so a column that is both blocked and warned appears once, in document order, which
   * is the order the matrix beside it uses.
   */
  const listedColumns = React.useMemo(
    () =>
      columns.filter(
        (column) => !column.reconciled || column.dismissed || Boolean(column.warning),
      ),
    [columns],
  );

  const registerColumnRef = React.useCallback((key: string, node: HTMLElement | null) => {
    // A ref callback reports its unmount as a bare null and never says which node it was
    // holding, so nothing is removed here; the detached ones are swept on the next jump.
    if (!node) return;
    const nodes = columnRefs.current.get(key);
    if (nodes) nodes.add(node);
    else columnRefs.current.set(key, new Set([node]));
  }, []);

  // jsdom implements no scrollIntoView, hence the optional call.
  const jumpToColumn = React.useCallback((key: string) => {
    const nodes = columnRefs.current.get(key);
    if (!nodes) return;
    for (const node of nodes) if (!node.isConnected) nodes.delete(node);
    // `offsetParent` is null for anything a media query has hidden, which is exactly the
    // shape of the grid this width is not using. jsdom lays nothing out, so it is null
    // there for every node and the first one stands in.
    const live = Array.from(nodes);
    const target = live.find((node) => node.offsetParent !== null) ?? live[0];
    target?.scrollIntoView?.({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, []);

  /**
   * Both: bring the column on screen, then hand it the cursor.
   *
   * The two views answer the request themselves because only they know which of their own
   * cells is the first editable one, and on a phone the card has to open before there is a
   * field to focus at all.
   */
  const jumpAndFocusColumn = React.useCallback(
    (key: string) => {
      jumpToColumn(key);
      setFocusRequest((previous) => ({ key, nonce: (previous?.nonce ?? 0) + 1 }));
    },
    [jumpToColumn],
  );

  const valueFor = React.useCallback(
    (phaseId: string, columnKey: string) => {
      const key = cellMapKey(phaseId, columnKey);
      const draft = drafts.get(key);
      if (draft !== undefined) return draft;
      return storedCells.get(key) ?? '';
    },
    [drafts, storedCells],
  );

  const setDraft = React.useCallback(
    (phaseId: string, columnKey: string, value: string) => {
      setDrafts((previous) => {
        const next = new Map(previous);
        next.set(cellMapKey(phaseId, columnKey), value);
        return next;
      });
    },
    [],
  );

  const dropDraft = React.useCallback((key: string) => {
    setDrafts((previous) => {
      if (!previous.has(key)) return previous;
      const next = new Map(previous);
      next.delete(key);
      return next;
    });
  }, []);

  /**
   * Saves one cell on blur.
   *
   * The column total is recomputed locally from the drafts, so a corrected column flips to
   * reconciled as the number is typed rather than after the round trip. The write still goes
   * out, and the response replaces the version in the cache.
   */
  const commit = React.useCallback(
    (phaseId: string, column: ColumnState) => {
      const key = cellMapKey(phaseId, column.key);
      const draft = drafts.get(key);
      if (draft === undefined) return;

      const stored = storedCells.get(key) ?? '';
      const unchanged =
        (draft.trim() === '' && stored.trim() === '') ||
        (isQty(draft) && isQty(stored) && normaliseQty(draft) === normaliseQty(stored));
      if (unchanged) {
        dropDraft(key);
        return;
      }

      if (draft.trim() !== '' && !isQty(draft)) {
        toast.error(`"${draft}" is not a quantity.`);
        return;
      }
      if (!column.productId) return;
      if (demo) return;

      // "0" deletes the cell, per the contract, which is how a blank is written back.
      const qty = draft.trim() === '' ? '0' : draft.trim();
      saveCells.mutate(
        [{ phase_id: phaseId, product_id: column.productId, qty }],
        { onSuccess: () => dropDraft(key) },
      );
    },
    [demo, drafts, dropDraft, saveCells, storedCells],
  );

  const onResolveProduct = React.useCallback(
    (columnIndex: number, productId: string) => {
      const remember = () =>
        setLearnedColumns((previous) =>
          previous.includes(columnIndex) ? previous : [...previous, columnIndex],
        );
      if (demo) {
        remember();
        return;
      }
      resolveProduct.mutate(
        { productIndex: columnIndex, productId },
        { onSuccess: remember },
      );
    },
    [demo, resolveProduct],
  );

  const onDismissColumn = React.useCallback(
    (columnIndex: number, dismissed: boolean, reason?: string) => {
      if (demo) return;
      dismissColumn.mutate({ columnIndex, dismissed, reason: reason ?? null });
    },
    [demo, dismissColumn],
  );

  const controller: ScheduleGridController = {
    columns,
    phaseGroups,
    valueFor,
    setDraft,
    commit,
    resolveProduct: onResolveProduct,
    poOptions,
    canEdit,
    learnedColumns,
    registerColumnRef,
    focusRequest,
    metaFor: (phaseId, columnKey) => cellMeta.get(cellMapKey(phaseId, columnKey)),
  };

  /**
   * The PO this schedule is checked against, for the gear menu.
   *
   * The PO record (`pos/{id}`, its lines and documents) rather than the document confirm
   * screen: amending a PO is what the reviewer comes here to do. `purchase_order_id` arrives
   * on the schedule version; the PO version we already read for the pickers is the fallback,
   * and the version review screen the last resort. Null when this schedule was checked
   * against no PO at all - a dead link is worse than no link.
   */
  const poHref = version?.purchase_order_id
    ? `/project-sales/${projectId}/pos/${version.purchase_order_id}`
    : poVersion.data?.purchase_order_id
      ? `/project-sales/${projectId}/pos/${poVersion.data.purchase_order_id}`
      : version?.po_version_id
        ? `/project-sales/${projectId}/purchase-orders/${version.po_version_id}`
        : null;

  if (view.isLoading) {
    return <ReviewSkeleton />;
  }

  if (view.isError || !version) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This schedule could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {view.error instanceof Error ? view.error.message : 'It may have been deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=schedules`}>
            Back to delivery schedules
          </Link>
        </Button>
      </div>
    );
  }

  const readingNow = phase === 'queued' || phase === 'running';

  return (
    <div className="space-y-5">
      {/* flex-col until sm: a wrapping title and the actions cannot share a row on a phone. */}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">
            {version.po_number
              ? `Delivery schedule for ${version.po_number}`
              : 'Delivery schedule'}
          </h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            <span>{`Version ${version.version_no}`}</span>
            {version.revision_label && <span>{version.revision_label}</span>}
            {version.issuer_party_label && (
              <span>{`Issued by ${version.issuer_party_label}`}</span>
            )}
            {version.schedule_date && (
              <span>{`Dated ${formatDateInMalaysia(version.schedule_date)}`}</span>
            )}
            {version.po_version_no !== null && version.po_version_no !== undefined && (
              <span>{`Checked against PO version ${version.po_version_no}`}</span>
            )}
            {readingTime && <span>{readingTime}</span>}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* This schedule's own revisions, walked one after another rather than through the
              project tab between each. Same pager as the user record. */}
          <RecordNavigation
            basePath={`/project-sales/${projectId}/delivery-schedules`}
            prevId={neighbours.prevId}
            nextId={neighbours.nextId}
            currentIndex={neighbours.index != null ? neighbours.index - 1 : undefined}
            totalCount={neighbours.total}
            isLoading={neighbours.isLoading}
            ariaLabel="schedule version"
          />
          {/* Everything that only takes you somewhere lives behind the gear. The header used
              to carry a button per destination, and the row of them competed with Confirm,
              which is the one thing this screen is for. Both open in a new tab: the reviewer
              is mid-reconciliation and leaving the page loses the cells they have typed. */}
          {(poHref || version.document_url) && (
            <DetailActionsMenu ariaLabel="Schedule actions">
              {poHref && (
                <DropdownMenuItem asChild>
                  <a href={poHref} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="size-4" aria-hidden />
                    View PO
                  </a>
                </DropdownMenuItem>
              )}
              {version.document_url && (
                <DropdownMenuItem asChild>
                  <a href={version.document_url} target="_blank" rel="noopener noreferrer">
                    <FileText className="size-4" aria-hidden />
                    View document
                  </a>
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          )}
          {!version.confirmed_at && (
            <Button
              type="button"
              size="sm"
              disabled={!canEdit || readingNow || columns.length === 0}
              onClick={() => setConfirming(true)}
            >
              Confirm
            </Button>
          )}
        </div>
      </header>

      {version.confirmed_at && (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-accent px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <CheckCircle2 className="size-4 text-[var(--color-success-accent,var(--color-green-500))]" aria-hidden />
            <span className="break-words">
              {`Confirmed ${formatDateTimeInMalaysia(version.confirmed_at)}`}
              {version.confirmed_by_name ? ` by ${version.confirmed_by_name}` : ''}
            </span>
          </div>
          {/* Confirming is the end of this screen's job and the start of the next one.
              Without a way onward, the person who just finished has to work out for
              themselves that sales orders live back on the project, which is exactly
              the dead end they hit after confirming a PO. */}
          <Button asChild size="sm" variant="outline" className="shrink-0">
            <Link href={`/project-sales/${projectId}?tab=sales-orders`}>
              Back to the project to build the sales orders
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </Button>
        </div>
      )}

      {version.amendment_preview_url && (
        <div
          data-testid="amendment-needed-banner"
          className="flex flex-col gap-3 rounded-lg border border-[var(--color-warning-accent,var(--color-yellow-500))]/50 bg-[var(--color-warning-soft,var(--color-yellow-100))] px-3 py-2 text-sm dark:bg-[var(--color-warning-soft,var(--color-yellow-950))] sm:flex-row sm:items-center sm:justify-between"
        >
          <span className="break-words">
            This schedule is confirmed; the linked sales order has not been amended yet.
          </span>
          <Button asChild size="sm" variant="outline" className="shrink-0">
            <Link href={version.amendment_preview_url}>Review the amendment</Link>
          </Button>
        </div>
      )}

      {readingNow && <ExtractionProgress version={version} />}

      {phase === 'failed' && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            This document could not be read
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground break-words">
            {version.extraction_error ?? 'Nothing was extracted from the file.'}
          </p>
          {/* Reading it again leads, because the commonest failure is not the document:
              a reader that was killed part-way says nothing about the scan, and asking
              for a better one is advice that cannot help. Re-uploading stays available
              for the case where the document really is the problem. */}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            {!demo && (
              <Button
                type="button"
                disabled={retryExtraction.isPending}
                onClick={() => void retryExtraction.mutateAsync().catch(() => undefined)}
              >
                <RefreshCw
                  className={`size-4 ${retryExtraction.isPending ? 'animate-spin' : ''}`}
                  aria-hidden
                />
                {retryExtraction.isPending ? 'Starting…' : 'Read it again'}
              </Button>
            )}
            <Button asChild variant="outline">
              <Link href={`/project-sales/${projectId}?tab=schedules`}>
                Upload it again
              </Link>
            </Button>
          </div>
        </div>
      )}

      {phase === 'partial' && (
        <div className="flex flex-col gap-1 rounded-lg border border-[var(--color-warning-accent,var(--color-yellow-500))]/50 bg-[var(--color-warning-soft,var(--color-yellow-100))] px-3 py-2.5 text-sm dark:bg-[var(--color-warning-soft,var(--color-yellow-950))]">
          <span className="flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" aria-hidden />
            {typeof version.pages_extracted === 'number' &&
            typeof version.page_count === 'number'
              ? `Only ${version.pages_extracted} of ${version.page_count} pages were read`
              : 'Some of this document was not read'}
          </span>
          <span className="text-muted-foreground">
            {version.extraction_error ??
              'The columns below are only what came out of the pages that were read.'}
          </span>
        </div>
      )}

      {!readingNow && phase !== 'failed' && columns.length === 0 && (
        <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
          <h2 className="text-sm font-semibold">No columns came out of this document</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Nothing was read that looks like a product column. Check the file is the schedule
            itself and upload it again.
          </p>
          <Button asChild variant="outline" className="mt-4">
            <Link href={`/project-sales/${projectId}?tab=schedules`}>
              Back to delivery schedules
            </Link>
          </Button>
        </div>
      )}

      {!readingNow && columns.length > 0 && (
        <>
          <DeliveryScheduleNotes notes={version.notes ?? []} />

          <DeliveryScheduleRevisionProposals
            proposals={version.revision_proposals ?? []}
            canDecide={canEdit}
            pendingIndex={pendingProposalIndex}
            onAccept={(index) => {
              if (demo) return;
              setPendingProposalIndex(index);
              acceptProposal.mutate(index, {
                onSettled: () => setPendingProposalIndex(null),
              });
            }}
            onReject={(index) => {
              if (demo) return;
              setPendingProposalIndex(index);
              rejectProposal.mutate(index, {
                onSettled: () => setPendingProposalIndex(null),
              });
            }}
          />

          {version.version_no > 1 && (
            <DeliveryScheduleRevisionDiff
              version={version}
              priorVersion={priorVersion.data}
              priorLoading={priorVersion.isLoading}
            />
          )}

          <Card>
            <CardHeader className="flex flex-col gap-2 pb-2 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="text-sm">Reconciliation</CardTitle>
              <ReconciliationBadge reconciled={reconciledCount} total={columns.length} />
            </CardHeader>
            <CardContent className="space-y-3">
              {/* What the section is for, in one line. Without it the rows read as a list
                  of complaints with no stated purpose, which is what "what do I need to do
                  with them" was asking. */}
              <p className="text-sm text-muted-foreground">
                {canEdit
                  ? 'Every column has to agree with the PO before this schedule can be confirmed.'
                  : 'This schedule is confirmed, so nothing here can be changed. What follows is what did not agree with the PO at the time it was confirmed.'}
              </p>
              {listedColumns.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing to fix. Every one of them matches the PO and the schedule&apos;s
                  own totals.
                </p>
              ) : (
                <>
                  {/* How much is left, so a column fixed is a number going down rather than
                      a row quietly leaving a list. */}
                  {/* "Still to fix" is a to-do. On a confirmed schedule there is nothing
                      to do, so the same number has to be reported as a finding instead, or
                      the screen asks for work it will not accept. */}
                  <p data-testid="reconciliation-remaining" className="text-sm font-medium">
                    {blocking.length === 0
                      ? 'Nothing left to fix. What follows was dismissed, or carries a warning that does not block.'
                      : canEdit
                        ? blocking.length === 1
                          ? '1 column still to fix.'
                          : `${blocking.length} columns still to fix.`
                        : blocking.length === 1
                          ? '1 column did not agree.'
                          : `${blocking.length} columns did not agree.`}
                  </p>
                  <DeliveryScheduleReconciliationList
                    columns={listedColumns}
                    canEdit={canEdit}
                    poOptions={poOptions}
                    onJump={jumpToColumn}
                    onFixQuantities={jumpAndFocusColumn}
                    onResolveProduct={onResolveProduct}
                    onDismissColumn={demo ? undefined : onDismissColumn}
                  />
                </>
              )}
            </CardContent>
          </Card>

          {/* By phase is the document's own columns, unchanged; By date turns the same
              cells round by their EFFECTIVE date, so an accepted re-date shows the quantity
              sitting under the date it now goes out on, not the one it left (the captain's
              own question, 19 Aug). */}
          <div className="flex flex-wrap items-center gap-2">
            <ToggleGroup
              type="single"
              variant="outline"
              value={viewMode}
              onValueChange={(next) => next && setViewMode(next as 'phase' | 'date')}
            >
              <ToggleGroupItem value="phase" className="px-3">
                By phase
              </ToggleGroupItem>
              <ToggleGroupItem value="date" className="px-3">
                By date
              </ToggleGroupItem>
            </ToggleGroup>
            {viewMode === 'phase' && overrideCount > 0 && (
              <button
                type="button"
                onClick={() => setViewMode('date')}
                className="rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
              >
                {`${overrideCount} cell${overrideCount === 1 ? '' : 's'} re-dated - view by date`}
              </button>
            )}
          </div>

          {viewMode === 'phase' ? (
            /* One grid, two shapes. The matrix needs room; a phone gets the per-column view. */
            <>
              <div className="hidden md:block">
                <DeliveryScheduleMatrix controller={controller} />
              </div>
              <div className="md:hidden">
                <DeliveryScheduleColumnCards controller={controller} />
              </div>
            </>
          ) : (
            /* Read-only, on every width: the inputs live in By phase, and building a
               phone-specific by-date card view is not the trivial change the phone view
               otherwise gets left alone for. */
            <DeliveryScheduleByDateMatrix controller={controller} dateColumns={dateColumnsData} />
          )}
        </>
      )}

      <DeliveryScheduleConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        blocking={blocking}
        pending={confirm.isPending}
        onConfirm={async (body: DeliveryScheduleConfirmBody) => {
          try {
            await confirm.mutateAsync(body);
            setConfirming(false);
          } catch {
            // The mutation hook already surfaced the message; keep the dialog open so the
            // reviewer can acknowledge and try again without losing what they typed.
          }
        }}
      />
    </div>
  );
}

/** Honest progress: page counts when the backend gives them, no invented percentage. */
function ExtractionProgress({
  version,
}: {
  version: {
    extraction_state: string;
    page_count?: number | null;
    pages_extracted?: number | null;
    extraction_started_at?: string | null;
  };
}) {
  const read = version.pages_extracted;
  const total = version.page_count;
  const waitingFor = describeWaitingFor(version.extraction_started_at);
  const detail =
    version.extraction_state === 'queued'
      ? typeof total === 'number'
        ? `${total} page${total === 1 ? '' : 's'} waiting to be read.`
        : 'Waiting to be read.'
      : typeof read === 'number' && typeof total === 'number'
        ? `Page ${Math.min(read + 1, total)} of ${total}.`
        : 'Reading the document.';

  return (
    <Card>
      <CardContent className="space-y-4 py-6">
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          <span className="font-medium">
            {version.extraction_state === 'queued' ? 'Queued' : 'Reading the schedule'}
          </span>
          <Badge variant="secondary" size="sm">
            {detail}
          </Badge>
          {waitingFor ? (
            <span className="text-xs text-muted-foreground">{waitingFor}</span>
          ) : null}
        </div>
        <MatrixSkeleton />
      </CardContent>
    </Card>
  );
}

function MatrixSkeleton() {
  return (
    <div className="space-y-2" aria-hidden>
      <div className="flex gap-2">
        <Skeleton className="h-9 w-[200px] shrink-0" />
        <Skeleton className="h-9 flex-1" />
      </div>
      {[0, 1, 2, 3, 4].map((row) => (
        <div key={row} className="flex gap-2">
          <Skeleton className="h-7 w-[200px] shrink-0" />
          <Skeleton className="h-7 flex-1" />
        </div>
      ))}
    </div>
  );
}

/** Matches the shape the page settles into, so nothing jumps when the data lands. */
function ReviewSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-2">
          <Skeleton className="h-7 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <Skeleton className="h-8 w-40" />
      </div>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-80 w-full" />
    </div>
  );
}
