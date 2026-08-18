'use client';

import * as React from 'react';
import { ArrowLeft, PackageSearch } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePlanningBoard } from '../../_shared/hooks/useFulfilmentPlanning';
import {
  confirmBlockedReason,
  standingsFor,
} from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardDecision,
  BoardDraft,
  BoardGranularity,
  BoardOrderStanding,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';

const GRANULARITY_OPTIONS = [
  { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' },
];

/**
 * Planning several sales orders at once (PLAN section 13).
 *
 * The board is a LENS. It reads across the selection and writes nothing of its own: approve /
 * amend / reject go into a draft held here, and the thing that commits is still the existing
 * per-order confirmation, one call per order, atomic across that order's lines (13.4, 13.6).
 *
 * Which is why the commit rail is not decoration. A cell holds one product on one date and an
 * order spans many lines across many dates, so approving a cell almost never finishes an
 * order. The rail says "4 of 12 lines decided" per order and keeps Confirm disabled with that
 * sentence as its reason, because the alternative - a Confirm that looks ready - would imply
 * the cell committed something it did not.
 */
export function FulfilmentBoardPanel({
  soNumbers,
  onBack,
}: {
  soNumbers: string[];
  onBack: () => void;
}) {
  const [granularity, setGranularity] = React.useState<BoardGranularity>('week');
  const [draft, setDraft] = React.useState<BoardDraft>({});
  const [openCell, setOpenCell] = React.useState<BoardCell | null>(null);

  const board = usePlanningBoard(soNumbers, granularity);

  const decide = React.useCallback((key: string, decision: BoardDecision | null) => {
    setDraft((current) => {
      const next = { ...current };
      if (decision) next[key] = decision;
      else delete next[key];
      return next;
    });
  }, []);

  const decidedKeys = React.useMemo(() => new Set(Object.keys(draft)), [draft]);

  // Recomputed from the board's own contributions rather than from the raw lines, so the
  // counter and the cells can never disagree about which line is which.
  const standings = React.useMemo<BoardOrderStanding[]>(() => {
    if (!board.data) return [];
    const lines = board.data.cells.flatMap((cell) =>
      cell.contributions.map((contribution) => ({
        sales_order_id: contribution.sales_order_id,
        so_number: contribution.so_number,
        customer_name: contribution.customer_name,
        line_no: contribution.line_no,
        item_code: contribution.item_code,
        qty: contribution.qty,
        required_date: contribution.required_date,
        fulfilment_location: contribution.fulfilment_location,
      })),
    );
    return standingsFor(lines, draft, {
      today: board.data.as_of,
      granularity: board.data.granularity,
    });
  }, [board.data, draft]);

  const bucketLabel = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const bucket of board.data?.dateBuckets ?? []) map.set(bucket.key, bucket.label);
    return map;
  }, [board.data]);

  // The cell the dialog is showing has to be re-read from the board on every render, or the
  // decision pills inside it would keep the shape they had when it was opened.
  const liveCell = React.useMemo(() => {
    if (!openCell || !board.data) return null;
    return (
      board.data.cells.find(
        (cell) =>
          cell.item_code === openCell.item_code && cell.bucket_key === openCell.bucket_key,
      ) ?? null
    );
  }, [openCell, board.data]);

  const overdueTotal = React.useMemo(() => {
    const cells = (board.data?.cells ?? []).filter((cell) => cell.bucket_key === 'overdue');
    const lines = cells.reduce((total, cell) => total + cell.contributions.length, 0);
    const allLines = (board.data?.cells ?? []).reduce(
      (total, cell) => total + cell.contributions.length,
      0,
    );
    return { lines, allLines };
  }, [board.data]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onBack}>
            <ArrowLeft className="size-4" aria-hidden />
            Back to the worklist
          </Button>
          <h2 className="min-w-0 truncate text-lg font-semibold">
            {`Planning ${soNumbers.length} sales orders together`}
          </h2>
        </div>
        <div className="w-full sm:w-44">
          <SearchableSelect
            value={granularity}
            onChange={(value) => setGranularity(value as BoardGranularity)}
            options={GRANULARITY_OPTIONS}
          />
        </div>
      </div>

      {board.isError ? (
        <Alert variant="destructive" appearance="light">
          <AlertIcon>
            <AlertTriangle />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>The planning board could not be loaded</AlertTitle>
            <AlertDescription>
              {board.error instanceof Error ? board.error.message : 'Try again in a moment.'}
              <div className="mt-3">
                <Button type="button" size="sm" variant="outline" onClick={() => board.refetch()}>
                  Try again
                </Button>
              </div>
            </AlertDescription>
          </AlertContent>
        </Alert>
      ) : board.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      ) : !board.data || board.data.cells.length === 0 ? (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
            <h3 className="mt-2 text-sm font-semibold">
              These sales orders owe nothing that can be planned
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Every line of the selection is already delivered, closed or covered.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {overdueTotal.lines > 0 && (
            <Alert appearance="light">
              <AlertIcon>
                <AlertTriangle />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>
                  {`${overdueTotal.lines} of ${overdueTotal.allLines} lines are already past their required date`}
                </AlertTitle>
                <AlertDescription>
                  They are held in the Overdue column, first on the board, rather than spread
                  back across the dates they were due on.
                </AlertDescription>
              </AlertContent>
            </Alert>
          )}

          <FulfilmentBoardMatrix
            dateBuckets={board.data.dateBuckets}
            productRows={board.data.productRows}
            cells={board.data.cells}
            decidedKeys={decidedKeys}
            onOpenCell={(cell) => setOpenCell(cell)}
          />

          <Card>
            <CardHeader className="block">
              <h3 className="text-sm font-semibold">Commit</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                One confirmation per sales order, each atomic across that order&apos;s lines.
              </p>
            </CardHeader>
            <CardContent className="space-y-2">
              {standings.map((standing) => (
                <OrderCommitRow key={standing.sales_order_id} standing={standing} />
              ))}
            </CardContent>
          </Card>
        </>
      )}

      {liveCell && (
        <BoardCellBreakdownDialog
          cell={liveCell}
          bucketLabel={bucketLabel.get(liveCell.bucket_key) ?? liveCell.bucket_key}
          draft={draft}
          onDecide={decide}
          onClose={() => setOpenCell(null)}
        />
      )}
    </div>
  );
}

/**
 * One selected order's standing and its Confirm.
 *
 * The disabled Confirm always states its reason. A button that is off without saying why is
 * what makes a screen feel broken, and here the reason is the honest shape of the design: the
 * board decides by cell, the database commits by order, and until every line of an order has a
 * verdict there is nothing to commit.
 */
function OrderCommitRow({ standing }: { standing: BoardOrderStanding }) {
  const blocked = confirmBlockedReason(standing);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium tabular-nums">{standing.so_number}</div>
        <div
          className="truncate text-sm text-muted-foreground"
          title={standing.customer_name ?? ''}
        >
          {standing.customer_name || 'Customer not recorded'}
        </div>
      </div>
      <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
        <span className="text-sm tabular-nums">
          {`${standing.decided_count} of ${standing.line_count} lines decided`}
        </span>
        {blocked ? (
          <span className="min-w-0 text-sm text-muted-foreground break-words">{blocked}</span>
        ) : null}
        <Button type="button" size="sm" disabled={Boolean(blocked)}>
          Confirm this order
        </Button>
      </div>
    </div>
  );
}
