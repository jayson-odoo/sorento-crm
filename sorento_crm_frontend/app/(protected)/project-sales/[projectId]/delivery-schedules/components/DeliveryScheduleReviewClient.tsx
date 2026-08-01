'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { useProject } from '../../../_shared/hooks/useProjects';
import {
  useDeliveryScheduleVersion,
  useDeliveryScheduleVersionMutations,
} from '../../../_shared/hooks/useDeliverySchedules';
import { resolveExtractionPhase } from '../../../_shared/types/deliverySchedule.types';
import type { DeliveryScheduleConfirmBody } from '../../../_shared/types/deliverySchedule.types';
import { ReconciliationBadge } from '../../components/DeliverySchedulesPanel';
import {
  demoScheduleVersionState,
  useDemoScheduleState,
} from '../_demo/scheduleDemo';
import {
  buildCellMap,
  buildColumnStates,
  cellMapKey,
  groupPhasesByArea,
  isQty,
  normaliseQty,
} from '../lib/scheduleTotals';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleColumnCards } from './DeliveryScheduleColumnCards';
import { DeliveryScheduleConfirmDialog } from './DeliveryScheduleConfirmDialog';
import { DeliveryScheduleMatrix } from './DeliveryScheduleMatrix';
import type { ScheduleGridController } from './DeliveryScheduleMatrix';

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

  const { saveCells, resolveProduct, confirm } = useDeliveryScheduleVersionMutations(
    projectId,
    versionId,
  );

  const [drafts, setDrafts] = React.useState<Map<string, string>>(new Map());
  const [learnedColumns, setLearnedColumns] = React.useState<number[]>([]);
  const [confirming, setConfirming] = React.useState(false);
  const columnRefs = React.useRef<Map<string, HTMLElement>>(new Map());

  const phase = version ? resolveExtractionPhase(version) : 'queued';
  const canEdit =
    (demo ? true : (project.data?.can_edit ?? false)) && !version?.confirmed_at;

  const storedCells = React.useMemo(
    () => buildCellMap(version?.cells ?? []),
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

  const registerColumnRef = React.useCallback((key: string, node: HTMLElement | null) => {
    if (node) columnRefs.current.set(key, node);
    else columnRefs.current.delete(key);
  }, []);

  // jsdom implements no scrollIntoView, hence the optional call.
  const jumpToColumn = React.useCallback((key: string) => {
    columnRefs.current
      .get(key)
      ?.scrollIntoView?.({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, []);

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

  const controller: ScheduleGridController = {
    columns,
    phaseGroups,
    valueFor,
    setDraft,
    commit,
    resolveProduct: onResolveProduct,
    canEdit,
    learnedColumns,
    registerColumnRef,
  };

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
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {version.document_url && (
            <Button asChild variant="outline" size="sm">
              <a href={version.document_url} target="_blank" rel="noreferrer">
                <ExternalLink className="size-4" aria-hidden />
                View document
              </a>
            </Button>
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
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-accent px-3 py-2 text-sm">
          <CheckCircle2 className="size-4 text-[var(--color-success-accent,var(--color-green-500))]" aria-hidden />
          <span>
            {`Confirmed ${formatDateTimeInMalaysia(version.confirmed_at)}`}
            {version.confirmed_by_name ? ` by ${version.confirmed_by_name}` : ''}
          </span>
        </div>
      )}

      {readingNow && <ExtractionProgress version={version} />}

      {phase === 'failed' && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            This document could not be read
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {version.extraction_error ?? 'Nothing was extracted from the file.'}
          </p>
          <Button asChild variant="outline" className="mt-4">
            <Link href={`/project-sales/${projectId}?tab=schedules`}>
              Upload it again
            </Link>
          </Button>
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
          <Card>
            <CardHeader className="flex flex-col gap-2 pb-2 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="text-sm">Reconciliation</CardTitle>
              <ReconciliationBadge reconciled={reconciledCount} total={columns.length} />
            </CardHeader>
            <CardContent>
              {blocking.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Every column agrees with the PO and with the schedule&apos;s own totals.
                </p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {blocking.map((column) => (
                    <li key={column.key}>
                      <button
                        type="button"
                        onClick={() => jumpToColumn(column.key)}
                        className="rounded-md border border-destructive/40 bg-destructive/5 px-2.5 py-1.5 text-start text-xs hover:bg-destructive/10"
                      >
                        <span className="block max-w-[220px] truncate font-medium">
                          {column.productCode ??
                            column.customerCode ??
                            'Unidentified column'}
                        </span>
                        <span className="block max-w-[260px] truncate text-muted-foreground">
                          {column.blockers[0]?.detail}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* One grid, two shapes. The matrix needs room; a phone gets the per-column view. */}
          <div className="hidden md:block">
            <DeliveryScheduleMatrix controller={controller} />
          </div>
          <div className="md:hidden">
            <DeliveryScheduleColumnCards controller={controller} />
          </div>
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
  version: { extraction_state: string; page_count?: number | null; pages_extracted?: number | null };
}) {
  const read = version.pages_extracted;
  const total = version.page_count;
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
