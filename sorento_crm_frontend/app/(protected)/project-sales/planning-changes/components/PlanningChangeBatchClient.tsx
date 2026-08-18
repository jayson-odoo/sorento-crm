'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { ArrowLeft, CheckCircle2 } from 'lucide-react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { ReactionPill } from '../../_shared/components/PlanningChangeReactionPill';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { usePlanningChangeBatch, usePlanningChangeMutations } from '../../_shared/hooks/usePlanningChanges';
import type {
  PlanningChangeOrder,
  PlanningChangeRow,
} from '../../_shared/types/planningChange.types';
import { BoardTrailPopover } from '../../fulfilment-planning/components/BoardTrailPopover';
import { sourceAt, sourceLabel } from '../../fulfilment-planning/components/BoardCellBreakdownDialog';
import { PlanningChangeDecisionControl } from './PlanningChangeDecisionControl';

/**
 * The batch of planning changes a re-uploaded AutoCount book raised (PLAN-so-book-diff-
 * replanning.md, journey step 1-3).
 *
 * One section per planned order, each a `PanelDataGrid` of the lines that changed: what
 * changed, what the line's decision holds today, the ladder's suggestion and why, and the one
 * decision the planner takes per row. Nothing is written until Apply, which revises every
 * accepted order in one press.
 */
export function PlanningChangeBatchClient({ batchId }: { batchId: string }) {
  const batch = usePlanningChangeBatch(batchId);
  const { updateDecision, apply } = usePlanningChangeMutations(batchId);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const acceptedCount = React.useMemo(() => {
    if (!batch.data) return 0;
    return batch.data.orders.reduce(
      (total, order) =>
        total +
        order.rows.filter(
          (row) => row.decision === 'accept' && row.applied_state === 'pending',
        ).length,
      0,
    );
  }, [batch.data]);

  const alreadyApplied = Boolean(batch.data?.applied_at);
  const failedCount = React.useMemo(
    () =>
      batch.data
        ? batch.data.orders.reduce(
            (total, order) =>
              total + order.rows.filter((row) => row.applied_state === 'failed').length,
            0,
          )
        : 0,
    [batch.data],
  );

  if (batch.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (batch.isError || !batch.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This planning change batch could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {batch.error instanceof Error ? batch.error.message : 'Try again in a moment.'}
        </p>
      </div>
    );
  }

  const data = batch.data;

  return (
    <div className="space-y-5">
      <Link
        href="/project-sales/planning-changes"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Planning changes
      </Link>

      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">{data.source.file_name}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {`Uploaded ${formatDateTimeInMalaysia(data.created_at)} by ${data.created_by_name}`}
          </p>
          <div className="mt-2">
            <AppliedStateBadge
              appliedAt={data.applied_at}
              appliedByName={data.applied_by_name}
              failedCount={failedCount}
            />
          </div>
        </div>
        <Button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={acceptedCount === 0 || alreadyApplied || apply.isPending}
        >
          {alreadyApplied ? 'Applied' : `Apply ${acceptedCount} change${acceptedCount === 1 ? '' : 's'}`}
        </Button>
      </header>

      {data.orders.map((order) => (
        <OrderSection
          key={order.project_sales_order_id}
          order={order}
          onDecide={(rowId, decision) =>
            updateDecision.mutate({ rowId, decision })
          }
          pendingRowId={
            updateDecision.isPending ? updateDecision.variables?.rowId : undefined
          }
        />
      ))}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Apply planning changes</AlertDialogTitle>
            <AlertDialogDescription>
              {`This revises every affected order: holds released or kept, decisions re-issued, `}
              {`and Order Inquiry rows updated. ${acceptedCount} row${
                acceptedCount === 1 ? '' : 's'
              } will be applied. This cannot be undone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={apply.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={apply.isPending}
              onClick={() => {
                apply.mutate(undefined, { onSuccess: () => setConfirmOpen(false) });
              }}
            >
              {apply.isPending ? 'Applying…' : 'Apply'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function AppliedStateBadge({
  appliedAt,
  appliedByName,
  failedCount,
}: {
  appliedAt?: string | null;
  appliedByName?: string | null;
  failedCount: number;
}) {
  if (!appliedAt) {
    return (
      <Badge variant="warning" appearance="light">
        Pending review
      </Badge>
    );
  }
  if (failedCount > 0) {
    return (
      <Badge variant="destructive" appearance="light">
        {`Partly failed - ${failedCount} row${failedCount === 1 ? '' : 's'} could not be written`}
      </Badge>
    );
  }
  return (
    <Badge variant="success" appearance="light">
      <CheckCircle2 className="size-3.5" aria-hidden />
      {`Applied ${formatDateTimeInMalaysia(appliedAt)}${appliedByName ? ` by ${appliedByName}` : ''}`}
    </Badge>
  );
}

function OrderSection({
  order,
  onDecide,
  pendingRowId,
}: {
  order: PlanningChangeOrder;
  onDecide: (rowId: string, decision: PlanningChangeRow['decision']) => void;
  pendingRowId?: string;
}) {
  const columns = React.useMemo<ColumnDef<PlanningChangeRow>[]>(
    () => [
      {
        id: 'line_no',
        accessorFn: (row) => row.line_no,
        header: () => 'Line',
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_no}</span>,
        size: 60,
        minSize: 50,
        meta: { headerTitle: 'Line' },
      },
      {
        id: 'item_code',
        accessorFn: (row) => row.item_code,
        header: () => 'Product',
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate text-sm font-medium" title={row.original.item_code}>
              {row.original.item_code}
            </div>
            {row.original.product_name && (
              <div
                className="truncate text-xs text-muted-foreground"
                title={row.original.product_name}
              >
                {row.original.product_name}
              </div>
            )}
          </div>
        ),
        size: 170,
        minSize: 130,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'change',
        header: () => 'Change',
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums" title={changeText(row.original)}>
            {changeText(row.original)}
          </span>
        ),
        size: 220,
        minSize: 160,
        meta: { headerTitle: 'Change' },
      },
      {
        id: 'held',
        header: () => 'Held today',
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={heldText(row.original)}>
            {heldText(row.original)}
          </span>
        ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Held today' },
      },
      {
        id: 'facts',
        header: () => 'Facts',
        cell: ({ row }) => <FactChips row={row.original} />,
        size: 180,
        minSize: 130,
        meta: { headerTitle: 'Facts' },
      },
      {
        id: 'suggested',
        header: () => 'Suggested',
        cell: ({ row }) => <SuggestedCell row={row.original} />,
        size: 210,
        minSize: 150,
        meta: { headerTitle: 'Suggested' },
      },
      {
        id: 'why',
        header: () => 'Why',
        cell: ({ row }) => (
          <span className="block truncate text-sm text-muted-foreground" title={row.original.why}>
            {row.original.why}
          </span>
        ),
        size: 260,
        minSize: 160,
        meta: { headerTitle: 'Why' },
      },
      {
        id: 'decision',
        header: () => 'Decision',
        cell: ({ row }) => (
          <PlanningChangeDecisionControl
            row={row.original}
            onChange={(decision) => onDecide(row.original.id, decision)}
            pending={pendingRowId === row.original.id}
            boardHref={row.original.board_link}
          />
        ),
        size: 240,
        minSize: 190,
        meta: { headerTitle: 'Decision' },
      },
    ],
    [onDecide, pendingRowId],
  );

  return (
    <PanelDataGrid<PlanningChangeRow>
      title={`${order.so_number} · ${order.customer_name ?? 'No customer'} · rev ${order.revision_no}`}
      columns={columns}
      rows={order.rows}
      getRowId={(row) => row.id}
      listingKey="projects.projects.view::project-planning-change-order"
      emptyTitle="Nothing changed on this order"
      pageSize={25}
    />
  );
}

// ── cell content helpers ─────────────────────────────────────────────────────

/** `Required 04 Feb 2027 -> 18 Feb 2027 (+14 d)`, `Qty 72 -> 66`, `Closed`, `New line`. */
function changeText(row: PlanningChangeRow): string {
  if (row.kind === 'closed') return 'Closed';
  if (row.kind === 'added') return 'New line';
  if (row.kind === 'delayed' || row.kind === 'advanced') {
    const from = row.from.required_date ? formatDateInMalaysia(row.from.required_date) : '-';
    const to = row.to.required_date ? formatDateInMalaysia(row.to.required_date) : '-';
    const days = row.days_moved ?? 0;
    const sign = days > 0 ? '+' : '';
    return `Required ${from} -> ${to} (${sign}${days} d)`;
  }
  // qty_up / qty_down
  return `Qty ${row.from.qty ?? '-'} -> ${row.to.qty ?? '-'}`;
}

/** `Reserve 66 at BRW-BB · Buy 6`, or `Not decided`. */
function heldText(row: PlanningChangeRow): string {
  const held = row.held;
  if (!held) return 'Not decided';
  const parts: string[] = [];
  for (const reserve of held.reserve) {
    parts.push(`Reserve ${reserve.qty} at ${reserve.location}`);
  }
  for (const borrow of held.borrow) {
    parts.push(`Borrow ${borrow.qty} from ${borrow.location}`);
  }
  if (held.timely_spo_qty && held.timely_spo_qty !== '0') {
    parts.push(`Incoming ${held.timely_spo_qty}`);
  }
  if (held.buy_qty && held.buy_qty !== '0') {
    parts.push(`Buy ${held.buy_qty}`);
  }
  return parts.length > 0 ? parts.join(' · ') : 'Nothing held';
}

/** `hot-selling`, `discontinued`, `+14 d` / `-14 d`, `PO placed`, `in window` / `beyond window`. */
function FactChips({ row }: { row: PlanningChangeRow }) {
  const facts = row.facts;
  const chips: Array<{ key: string; label: string; title: string }> = [];
  if (facts.dealer_hot_selling) {
    chips.push({
      key: 'hot-selling',
      label: 'hot-selling',
      title: 'Dealer hot-selling: BRW stock is kept for retail.',
    });
  }
  if (facts.discontinued) {
    chips.push({
      key: 'discontinued',
      label: 'discontinued',
      title: 'Discontinued: it cannot be bought again.',
    });
  }
  if (row.days_moved) {
    const sign = row.days_moved > 0 ? '+' : '';
    chips.push({
      key: 'days-moved',
      label: `${sign}${row.days_moved} d`,
      title: `The required date moved by ${Math.abs(row.days_moved)} day${
        Math.abs(row.days_moved) === 1 ? '' : 's'
      }.`,
    });
  }
  if (facts.buy_actioned) {
    chips.push({ key: 'po-placed', label: 'PO placed', title: 'Purchasing already placed this Buy.' });
  }
  if (row.kind === 'delayed' || row.kind === 'advanced') {
    chips.push(
      facts.within_reserve_window
        ? {
            key: 'in-window',
            label: 'in window',
            title: 'The new date is inside the reserve window.',
          }
        : {
            key: 'beyond-window',
            label: 'beyond window',
            title: 'The new date is beyond the reserve window.',
          },
    );
  }
  if (chips.length === 0) return <span className="text-sm text-muted-foreground">-</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {chips.map((chip) => (
        <span
          key={chip.key}
          title={chip.title}
          className="inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-2xs font-medium text-amber-800"
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}

/** The verb pill, plus - for replan/qty_up - the fresh proposal in the board's own words. */
function SuggestedCell({ row }: { row: PlanningChangeRow }) {
  const proposal = row.proposal;
  return (
    <div className="min-w-0 space-y-1">
      <ReactionPill reaction={row.suggested} />
      {proposal && (
        <div className="flex min-w-0 items-start gap-1">
          <span
            className="min-w-0 flex-1 truncate text-xs tabular-nums text-muted-foreground"
            title={proposal.sources.map((source) => source.reason).join(' ')}
          >
            {proposal.sources
              .map((source) => `${sourceLabel(source.kind)} ${source.qty}${sourceAt(source)}`)
              .join(' · ')}
          </span>
          <BoardTrailPopover contribution={proposal} />
        </div>
      )}
    </div>
  );
}

export default PlanningChangeBatchClient;
