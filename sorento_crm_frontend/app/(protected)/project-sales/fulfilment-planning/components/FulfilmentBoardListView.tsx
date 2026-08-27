'use client';

import * as React from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { BoardDecidedMarker, decidedRevisions } from './BoardDecidedMarker';
import { BoardDecisionPill } from './BoardDecisionPill';
import { BoardLineDecisionPanel } from './BoardLineDecisionPanel';
import { UnsavedDecisionPrompt, useDecisionRowExpansion } from './decisionRowExpansion';
import { SupplyBar } from '../../_shared/components/SupplyBar';
import {
  COLOURS,
  LABELS,
  contributionDecision,
  contributionSuggestion,
  contributionSupply,
  // Aliased the way `SalesOrderDetail` aliases it: bare `describe` is vitest's, and a file
  // that imports both reads as though the test runner were writing the column.
  describe as describeSupply,
  segmentsOf,
} from '../../_shared/lib/supplyVocabulary';
import type {
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

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
  /**
   * Which row is open, ONE at a time - the same STATE the cell breakdown keeps, and the same
   * panel inside it. The list used to carry Approve / Amend / Reject buttons in its Verdict
   * column and open the amend MODAL over the board; a decision is taken in the row on both
   * readings now, or the two would teach different gestures for one act - including the
   * question asked before an unsaved composition is thrown away (C5).
   */
  const expansion = useDecisionRowExpansion();
  const { expanded, setExpanded, setDirty, requestRow } = expansion;

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
                {/* A state indicator, not a control: the whole row opens the decision. */}
                {row.getIsExpanded() ? (
                  <ChevronDown
                    className="size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                ) : (
                  <ChevronRight
                    className="size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                )}
                <span className="truncate text-sm font-medium tabular-nums">
                  {contribution.so_number}
                </span>
                {/* The same tick the grid puts on a fully-decided cell, here per row: one
                    row IS one contribution, so it is decided or it is not. */}
                <BoardDecidedMarker
                  revisions={decidedRevisions([contribution])}
                />
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
        meta: {
          // The SAME editor the cell breakdown expands, so a decision reads and is taken
          // identically whichever way the planner came at the line - the per-location
          // Available included (C4). The figures ride on the CONTRIBUTION, netted of this
          // line's own quantity, so the list does not have to know which cell the line sits
          // in to quote the right pile.
          expandedContent: (contribution: BoardContribution) => (
            <BoardLineDecisionPanel
              contribution={contribution}
              decision={draft[contribution.key] ?? null}
              locations={contribution.locations ?? []}
              onDecide={(next) => onDecide(contribution.key, next)}
              onDirtyChange={setDirty}
            />
          ),
        },
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
          <span
            className="block truncate tabular-nums"
            title={row.original.item_code}
          >
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
        // AC-D4: what the ENGINE said, in PLAN section 2's own words. Split off the old
        // single "Proposal" column, which showed the decision on a decided line and the
        // proposal on an undecided one - so the two could never be compared, which is the
        // one thing the planner opens this view to do.
        id: 'suggested',
        accessorFn: () => '',
        header: 'Suggested',
        cell: ({ row }) => {
          const contribution = row.original;
          if (contribution.unplannable) {
            // The ladder was never walked for it (AC-FP16), so there is nothing to suggest -
            // and the reason is the one thing worth saying in its place.
            return (
              <span className="text-muted-foreground">Needs a location</span>
            );
          }
          const parts = contributionSuggestion(contribution);
          if (!parts) {
            // A decision frozen before the proposal was recorded. Not "nothing suggested".
            return <span className="text-muted-foreground">Not recorded</span>;
          }
          const text = describeSupply(parts, contribution.fulfilment_location);
          return (
            <div className="min-w-0 space-y-1">
              <span className="block truncate" title={text}>
                {text || (
                  <span className="text-muted-foreground">
                    Nothing proposed
                  </span>
                )}
              </span>
              {/* Faded: a suggestion is not a decision. */}
              <SupplyBar
                segments={segmentsOf(parts, contribution.fulfilment_location)}
                decided={false}
                labels={LABELS}
                colours={COLOURS}
              />
            </div>
          );
        },
        size: 240,
        minSize: 170,
      },
      {
        id: 'decided',
        accessorFn: () => '',
        header: 'Decided',
        cell: ({ row }) => {
          const contribution = row.original;
          const drafted = draft[contribution.key] ?? null;
          const parts = contributionDecision(contribution, drafted);
          if (!parts) {
            return <span className="text-muted-foreground">Not decided</span>;
          }
          // The SAME bar the grid draws, off the same draft, so the two views cannot
          // disagree about what this line is going to be supplied from.
          const supply = contributionSupply(contribution, drafted);
          // The composition alone, in section 2's words. NOT "Confirmed rev 1 · Buy 43":
          // the revision is already on the Verdict column and on the row's tick, and
          // repeating it here would cost the width the composition needs.
          const text = describeSupply(parts, contribution.fulfilment_location);
          return (
            <div className="min-w-0 space-y-1">
              <span className="block truncate" title={text}>
                {text}
              </span>
              <SupplyBar
                segments={supply.segments}
                decided={supply.decided}
                labels={LABELS}
                colours={COLOURS}
              />
            </div>
          );
        },
        size: 240,
        minSize: 170,
      },
      {
        id: 'rank',
        accessorFn: (row) => row.rank_score,
        header: 'Rank',
        cell: ({ row }) =>
          row.original.covered || row.original.unplannable ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span className="tabular-nums">
              {row.original.rank_score.toFixed(2)}
            </span>
          ),
        size: 80,
        minSize: 70,
      },
      {
        id: 'verdict',
        accessorFn: () => '',
        header: 'Verdict',
        // A PILL, and nothing else. The three verbs are in the expanded row, where the
        // numbers the decision is made against are.
        cell: ({ row }) => (
          <BoardDecisionPill
            contribution={row.original}
            decision={draft[row.original.key] ?? null}
          />
        ),
        size: 160,
        minSize: 120,
        enableResizing: false,
      },
    ],
    [draft, onDecide, setDirty],
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
      expanded={expanded}
      onExpandedChange={setExpanded}
      onRowClick={(row) => requestRow(row.key)}
      pageSize={25}
    />
    <UnsavedDecisionPrompt state={expansion} />
    </>
  );
}
