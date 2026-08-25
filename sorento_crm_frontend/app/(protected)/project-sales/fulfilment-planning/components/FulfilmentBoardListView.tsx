'use client';

import * as React from 'react';
import Link from 'next/link';
import { Check, Pencil, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ColumnDef } from '@tanstack/react-table';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { proposalSummaryFor } from '../../_shared/lib/fulfilmentBoard';
import { amendSummary } from '../../_shared/lib/boardAmend';
import { confirmedSummary } from './BoardCellBreakdownDialog';
import { BoardAmendDialog } from './BoardAmendDialog';
import { BoardDecidedMarker, decidedRevisions } from './BoardDecidedMarker';
import type { BoardContribution, BoardDecision, BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

const VERDICT_PALETTE: Record<BoardDecision['verdict'], string> = {
  approved: 'approved',
  amended: 'approved',
  rejected: 'rejected',
};

/**
 * The board as a LIST, not a grid: one row per contributing line across every cell (D2,
 * PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so Approve all can be seen
 * from an overview").
 *
 * The captain's ask was to see the whole draft at once - the grid answers "what does this
 * product owe by this date", the list answers "what is about to be committed, across every
 * order, in one scan". Same draft, same `onDecide`, same write path (there is none here
 * either - see `FulfilmentBoardPanel`'s own note): this is a second READING of the identical
 * data, never a second source of it.
 */
export function FulfilmentBoardListView({
  contributions,
  draft,
  onDecide,
  isLoading,
}: {
  contributions: BoardContribution[];
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => void;
  isLoading?: boolean;
}) {
  const [amending, setAmending] = React.useState<BoardContribution | null>(null);

  const columns = React.useMemo<ColumnDef<BoardContribution>[]>(
    () => [
      {
        id: 'so_number',
        accessorFn: (row) => row.so_number,
        header: 'Sales order',
        cell: ({ row }) => {
          const contribution = row.original;
          const body = (
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="truncate text-sm font-medium tabular-nums">
                  {contribution.so_number}
                </span>
                {/* The same tick the grid puts on a fully-decided cell, here per row: one
                    row IS one contribution, so it is decided or it is not. */}
                <BoardDecidedMarker revisions={decidedRevisions([contribution])} />
              </div>
              <div className="truncate text-xs text-muted-foreground">
                {`Line ${contribution.line_no}`}
              </div>
            </div>
          );
          return contribution.sales_order_id ? (
            <Link
              href={`/scm/sales-orders/${contribution.sales_order_id}`}
              onClick={(event) => event.stopPropagation()}
              className="block min-w-0 hover:underline"
            >
              {body}
            </Link>
          ) : (
            body
          );
        },
        size: 150,
        minSize: 120,
      },
      {
        id: 'agent',
        accessorFn: (row) => row.agent_code ?? '',
        header: 'Agent',
        cell: ({ row }) =>
          row.original.agent_code ? (
            <span
              className="block truncate tabular-nums"
              title={row.original.agent_label ?? row.original.agent_code}
            >
              {row.original.agent_code}
            </span>
          ) : (
            <span className="text-muted-foreground">Not stated</span>
          ),
        size: 110,
        minSize: 90,
      },
      {
        id: 'customer',
        accessorFn: (row) => row.customer_name ?? '',
        header: 'Customer',
        cell: ({ row }) =>
          row.original.customer_name ? (
            <span className="block truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Not recorded</span>
          ),
        size: 180,
        minSize: 130,
      },
      {
        id: 'product',
        accessorFn: (row) => row.item_code,
        header: 'Product',
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.item_code}>
            {row.original.item_code}
          </span>
        ),
        size: 140,
        minSize: 110,
      },
      {
        id: 'required_date',
        accessorFn: (row) => row.required_date ?? '',
        header: 'Required date',
        cell: ({ row }) =>
          row.original.required_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.required_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">No date</span>
          ),
        size: 130,
        minSize: 110,
      },
      {
        id: 'owed_qty',
        accessorFn: (row) => row.qty_outstanding ?? row.qty,
        header: 'Outstanding qty',
        cell: ({ row }) => (
          <span className="block truncate tabular-nums">
            {row.original.qty_outstanding ?? row.original.qty}
          </span>
        ),
        size: 100,
        minSize: 90,
      },
      {
        id: 'proposal',
        accessorFn: () => '',
        header: 'Proposal',
        cell: ({ row }) => {
          const contribution = row.original;
          const text =
            contribution.covered && contribution.decision
              ? confirmedSummary(contribution.decision)
              : proposalSummaryFor(contribution);
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 260,
        minSize: 180,
      },
      {
        id: 'rank',
        accessorFn: (row) => row.rank_score,
        header: 'Rank',
        cell: ({ row }) =>
          row.original.covered || row.original.unplannable ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span className="tabular-nums">{row.original.rank_score.toFixed(2)}</span>
          ),
        size: 80,
        minSize: 70,
      },
      {
        id: 'verdict',
        accessorFn: () => '',
        header: 'Verdict',
        cell: ({ row }) => {
          const contribution = row.original;
          const decision = draft[contribution.key] ?? null;

          if (contribution.unplannable) {
            return (
              <span
                className="block truncate text-sm text-destructive"
                title="This line cannot be decided here: its sales order states no fulfilment location."
              >
                Needs a location
              </span>
            );
          }

          if (!decision && contribution.covered && contribution.decision) {
            return (
              <div className="flex min-w-0 flex-wrap items-center gap-1">
                <span
                  className={`${STATUS_PILL_BASE} max-w-full whitespace-normal break-words text-start normal-case ${statusPillClass('closed')}`}
                >
                  {`Confirmed rev ${contribution.decision.revision_no}`}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setAmending(contribution)}
                >
                  <Pencil className="size-4" aria-hidden />
                  Amend
                </Button>
              </div>
            );
          }

          if (decision) {
            return (
              <div className="flex min-w-0 flex-wrap items-center gap-1">
                <span
                  className={`${STATUS_PILL_BASE} max-w-full whitespace-normal break-words text-start normal-case ${statusPillClass(VERDICT_PALETTE[decision.verdict])}`}
                  title={decision.reason ?? ''}
                >
                  {decision.verdict === 'approved'
                    ? 'Approved'
                    : decision.verdict === 'amended'
                      ? amendSummary(decision)
                      : 'Rejected'}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => onDecide(contribution.key, null)}
                >
                  Undo
                </Button>
              </div>
            );
          }

          return (
            <div className="flex flex-wrap items-center gap-1">
              <Button
                type="button"
                size="sm"
                onClick={() => onDecide(contribution.key, { verdict: 'approved' })}
              >
                <Check className="size-4" aria-hidden />
                Approve
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setAmending(contribution)}
              >
                <Pencil className="size-4" aria-hidden />
                Amend
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  onDecide(contribution.key, {
                    verdict: 'rejected',
                    reason: 'Rejected on the planning board.',
                  })
                }
              >
                <X className="size-4" aria-hidden />
                Reject
              </Button>
            </div>
          );
        },
        size: 260,
        minSize: 220,
        enableResizing: false,
      },
    ],
    [draft, onDecide],
  );

  return (
    <>
      <PanelDataGrid
        title="Every contributing line"
        columns={columns}
        rows={contributions}
        getRowId={(row) => row.key}
        listingKey="projects.projects.view::project-fulfilment-board-list-v1"
        isLoading={isLoading}
        emptyTitle="Nothing is outstanding on this board"
        searchPlaceholder="Search sales order, customer, agent or product"
        searchOf={(row) =>
          [row.so_number, row.customer_name, row.agent_code, row.item_code]
            .filter(Boolean)
            .join(' ')
        }
        pageSize={25}
      />

      {amending && (
        <BoardAmendDialog
          contribution={amending}
          onCancel={() => setAmending(null)}
          onSave={(decision) => {
            onDecide(amending.key, decision);
            setAmending(null);
          }}
        />
      )}
    </>
  );
}
