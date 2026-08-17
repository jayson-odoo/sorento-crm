'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Ruler } from 'lucide-react';
import type { ColumnDef, RowSelectionState } from '@tanstack/react-table';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { useHasPermission } from '@/hooks/usePermissions';

import type {
  DimensionApplyResult,
  DimensionCandidate,
} from '../../services/flyerReadingService';
import { useApplyDimensions } from '../hooks/useFlyerReadings';
import { Empty, Section, printedOn, size } from './ReportSection';
import { ReportGrid } from './ReportGrid';

/**
 * The sizes the flyer prints, beside the sizes the product master holds - and
 * the one control on this screen that changes anything outside the Kit (S7.6).
 *
 * Reading a flyer still writes nothing to `products` (AC-D4). Applying is a
 * separate, deliberate act, and everything here is shaped around making it stay
 * deliberate:
 *
 * - **Nothing is ticked by default.** There is no "apply all": a selection is
 *   the request, and an empty one is refused by the server rather than read as
 *   everything.
 * - **A conflict is not a correction.** A row where the master already holds a
 *   size somebody entered is a different thing from a blank one, and the
 *   confirmation names the value about to be destroyed. Ticking one is what
 *   sets `overwriteConflicts`; a selection of blanks alone never asks for it.
 * - **Rows the master already agrees with cannot be ticked.** There is nothing
 *   to apply, and a tick that does nothing reads as a broken control.
 * - **The result names every refusal.** 20 applied and 3 refused is shown as
 *   both, because nobody chases what they were not told about.
 * - **No master-data permission, no control.** The report stays readable -
 *   knowing the flyer disagrees is useful to somebody who cannot fix it.
 */

const VERDICT_LABEL: Record<string, string> = {
  conflicts: 'Disagrees with the master',
  missing: 'Master has no size',
  agrees: 'Agrees',
};

/** The slug that authorises a write to `products`, everywhere in the system. */
const MASTER_DATA_EDIT = 'master_data.products.edit';

export interface DimensionReviewSectionProps {
  readingId: string;
  candidates: DimensionCandidate[];
}

export function DimensionReviewSection({
  readingId,
  candidates,
}: DimensionReviewSectionProps) {
  const canWriteMaster = useHasPermission(MASTER_DATA_EDIT);
  const [selection, setSelection] = useState<RowSelectionState>({});
  // What the confirmation is asking about, snapshotted when it opens. The
  // selection is cleared the moment the write lands, and a dialog reading its
  // numbers off live state animates out saying "write 0 sizes".
  const [pending, setPending] = useState<DimensionCandidate[] | null>(null);
  const [result, setResult] = useState<DimensionApplyResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const { mutate, isPending } = useApplyDimensions(readingId);

  // Conflicts first. They are the entries that mean either a reprint or a wrong
  // box arriving at a customer, and burying them on page four of a table sorted
  // by code is the same as not reporting them. Rows that already agree sink to
  // the bottom: they are evidence that an apply worked, not work to do.
  const rows = useMemo(() => {
    const rank = { conflicts: 0, missing: 1, agrees: 2 } as Record<string, number>;
    return [...candidates].sort(
      (left, right) => (rank[left.verdict] ?? 9) - (rank[right.verdict] ?? 9),
    );
  }, [candidates]);

  const conflicts = rows.filter((row) => row.verdict === 'conflicts').length;

  // Keyed by code, which is what `getRowId` returns and what the API takes.
  const selected = useMemo(
    () => rows.filter((row) => selection[row.code]),
    [rows, selection],
  );
  const asked = pending ?? selected;
  const askedConflicts = asked.filter((row) => row.verdict === 'conflicts');

  const columns = useMemo<ColumnDef<DimensionCandidate>[]>(() => {
    const base: ColumnDef<DimensionCandidate>[] = [
      {
        accessorKey: 'code',
        header: 'Printed code',
        cell: ({ row }) => (
          <div className="truncate font-mono text-sm" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 170,
        minSize: 120,
        meta: { headerTitle: 'Printed code' },
      },
      {
        id: 'printed',
        header: 'On the flyer',
        cell: ({ row }) => {
          const value = size(
            row.original.printedLengthMm,
            row.original.printedWidthMm,
            row.original.printedHeightMm,
          );
          return (
            <span className="truncate text-sm" title={value ?? ''}>
              {value}
            </span>
          );
        },
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'On the flyer' },
      },
      {
        id: 'current',
        header: 'In the master',
        cell: ({ row }) => {
          const value = size(
            row.original.currentLengthMm,
            row.original.currentWidthMm,
            row.original.currentHeightMm,
          );
          return value ? (
            <span className="truncate text-sm" title={value}>
              {value}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Not recorded</span>
          );
        },
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'In the master' },
      },
      {
        id: 'verdict',
        header: 'Verdict',
        cell: ({ row }) => (
          <Badge
            variant={row.original.verdict === 'conflicts' ? 'warning' : 'outline'}
            appearance="ghost"
            className="font-normal"
          >
            {VERDICT_LABEL[row.original.verdict] ?? row.original.verdict}
          </Badge>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Verdict' },
      },
      {
        id: 'pages',
        header: 'Printed on',
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">{printedOn(row.original.pages)}</span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Printed on' },
      },
    ];

    if (!canWriteMaster) return base;
    return [
      buildSelectColumn<DimensionCandidate>({
        // An agreement has nothing to apply. Disabled rather than absent so the
        // column still lines up and the row still reads as a row.
        enableRow: (row) => row.original.verdict !== 'agrees',
      }),
      ...base,
    ];
  }, [canWriteMaster]);

  const apply = () => {
    const codes = asked.map((row) => row.code);
    const overwriting = askedConflicts.length > 0;
    setFailure(null);
    mutate(
      {
        codes,
        // Asked for ONLY when a conflicting row was ticked. Sending it always
        // would turn a race - somebody else filling the size in while this
        // screen was open - from a refusal into a silent overwrite.
        overwriteConflicts: overwriting,
      },
      {
        onSuccess: (answer) => {
          setResult(answer);
          // The rows have moved: what applied now agrees, and holding a stale
          // tick would re-send it on the next click.
          setSelection({});
        },
        onError: (error) => setFailure(error.message),
      },
    );
  };

  return (
    <Section
      id="dimensions"
      icon={<Ruler className="size-4" />}
      title="Sizes printed on the flyer"
      description={
        conflicts > 0
          ? `${conflicts} of ${rows.length} disagree with what the master holds. Only the rows you tick are written.`
          : 'Only the rows you tick are written to the product master.'
      }
      action={
        canWriteMaster && rows.length > 0 ? (
          <Button
            size="sm"
            variant="outline"
            data-testid="dk-fr-dimensions-apply"
            disabled={selected.length === 0 || isPending}
            onClick={() => setPending(selected)}
          >
            {isPending
              ? 'Writing to the master'
              : selected.length > 0
                ? `Apply ${selected.length} to the product master`
                : 'Apply to the product master'}
          </Button>
        ) : undefined
      }
    >
      {!canWriteMaster && rows.length > 0 && (
        <p
          className="rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground"
          data-testid="dk-fr-dimensions-readonly"
        >
          Reported only. Writing a size to the product master needs the product
          master permission, which your role does not have.
        </p>
      )}

      <ReportGrid
        data-testid="dk-fr-dimensions-grid"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.code}
        rowSelection={selection}
        onRowSelectionChange={setSelection}
        enableRowSelection={(row) => canWriteMaster && row.original.verdict !== 'agrees'}
        emptyMessage={
          <Empty tone="neutral" title="No card on this flyer printed a size">
            Sizes are read from the L x W x H line under a product code.
          </Empty>
        }
      />

      {failure && (
        <div
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          data-testid="dk-fr-dimensions-error"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <p>{failure}</p>
        </div>
      )}

      {result && <ApplyResult result={result} />}

      {/* Open when there is a snapshot to confirm; closing drops it. */}
      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      >
        {/* Scrolls: a confirmation listing thirty replaced sizes is taller than
            a phone, and a dialog that cannot reach its own button is a dialog
            nobody can refuse either. */}
        <AlertDialogContent className="max-h-[85vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>
              Write {asked.length} size{asked.length === 1 ? '' : 's'} to the product master?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {askedConflicts.length > 0
                ? `${askedConflicts.length} of them replace a size the product master already holds. This action cannot be undone.`
                : 'These products have no size recorded, so nothing is replaced.'}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {askedConflicts.length > 0 ? (
            <ul className="flex flex-col gap-2 text-sm" data-testid="dk-fr-dimensions-replacing">
              {askedConflicts.map((row) => (
                <li key={row.code} className="flex flex-col">
                  <span className="font-mono text-foreground">{row.code}</span>
                  <span className="text-muted-foreground">
                    {size(row.currentLengthMm, row.currentWidthMm, row.currentHeightMm) ??
                      'Not recorded'}{' '}
                    becomes{' '}
                    {size(row.printedLengthMm, row.printedWidthMm, row.printedHeightMm)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="font-mono text-sm text-muted-foreground">
              {asked.map((row) => row.code).join(', ')}
            </p>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="dk-fr-dimensions-confirm"
              className={
                askedConflicts.length > 0
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : undefined
              }
              onClick={apply}
            >
              {askedConflicts.length > 0 ? 'Overwrite and apply' : 'Apply'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Section>
  );
}

/**
 * What was written, and what was not.
 *
 * The refusals are the half that matters. A screen that reported "1 applied"
 * over a code that silently failed would leave a product wrong indefinitely,
 * because nobody goes looking for a failure they were never shown.
 */
function ApplyResult({ result }: { result: DimensionApplyResult }) {
  const wrote = result.appliedCount > 0;

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-border px-3 py-3 text-sm"
      data-testid="dk-fr-dimensions-result"
    >
      <p className="flex items-start gap-2 font-medium text-foreground">
        {wrote ? (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600" />
        ) : (
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
        )}
        {wrote
          ? `${result.appliedCount} size${result.appliedCount === 1 ? '' : 's'} written to the product master`
          : 'Nothing was written to the product master'}
      </p>

      {result.applied.length > 0 && (
        <ul className="flex flex-col gap-1 text-muted-foreground">
          {result.applied.map((entry) => (
            <li key={entry.code} className="min-w-0 break-words">
              <span className="font-mono text-foreground">{entry.code}</span>{' '}
              {size(entry.lengthMm, entry.widthMm, entry.heightMm)}
              {entry.wasConflict && (
                <>
                  {', replacing '}
                  {size(
                    entry.previousLengthMm,
                    entry.previousWidthMm,
                    entry.previousHeightMm,
                  ) ?? 'nothing'}
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {result.refused.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="font-medium text-foreground">
            {result.refusedCount} not written
          </p>
          <ul className="flex flex-col gap-1 text-muted-foreground">
            {result.refused.map((entry) => (
              <li key={entry.code} className="min-w-0 break-words">
                <span className="font-mono text-foreground">{entry.code}</span>{' '}
                {entry.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
