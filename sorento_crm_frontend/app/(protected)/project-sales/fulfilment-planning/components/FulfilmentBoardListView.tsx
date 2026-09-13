'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Undo2,
} from 'lucide-react';
import { ColumnDef, RowSelectionState } from '@tanstack/react-table';
import { formatDateInMalaysia } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { BoardDecidedMarker, decidedRevisions } from './BoardDecidedMarker';
import { BoardDecisionPill } from './BoardDecisionPill';
import { BoardLineDecisionPanel } from './BoardLineDecisionPanel';
import { UnsavedDecisionPrompt, useDecisionRowExpansion } from './decisionRowExpansion';
import { BoardChangeTable } from './BoardChangeTable';
import { changedFieldsOf } from '../../_shared/lib/boardChangeAnnotations';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';
import { canQuickSave, suggestedDecisionFor } from '../../_shared/lib/boardAmend';
import {
  contributionDecision,
  contributionSuggestion,
  // Aliased the way `SalesOrderDetail` aliases it: bare `describe` is vitest's, and a file
  // that imports both reads as though the test runner were writing the column.
  describe as describeSupply,
} from '../../_shared/lib/supplyVocabulary';
import type { SupplyPart } from '../../_shared/lib/supplyVocabulary';
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
  onDecideMany,
  annotations,
}: {
  contributions: BoardContribution[];
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => Promise<boolean> | void;
  /**
   * D15: the quiet-bulk path the board-wide "Save all suggested" and this view's own header
   * button both post through, so several rows saved together toast once ("N lines saved · M
   * to confirm") rather than the N separate "Line N saved" toasts D14 shipped with.
   */
  onDecideMany: (keys: string[]) => Promise<{ saved: number; failed: number }>;
  /**
   * What the re-uploaded book did to each line, keyed by planning line (AC-C9). The row
   * shows it as a hazard icon in the column that moved, and the lightbox behind the icon
   * says the rest - the same component the grid cell uses.
   */
  annotations?: Map<string, BoardChangeAnnotation[]>;
}) {
  /**
   * Which rows are open - the same STATE the cell breakdown keeps, and the same panel inside
   * it, opened as MANY at a time here (AC-C12: Expand all would mean nothing on a list that
   * closes each row as the next one opens). The list used to carry Approve / Amend / Reject buttons in its Verdict
   * column and open the amend MODAL over the board; a decision is taken in the row on both
   * readings now, or the two would teach different gestures for one act - including the
   * question asked before an unsaved composition is thrown away (C5).
   */
  const expansion = useDecisionRowExpansion();
  const {
    expanded,
    setExpanded,
    openKeys,
    dirtySetterFor,
    requestRow,
    expandAll,
    requestCollapseAll,
  } = expansion;

  /**
   * D14 (the captain: a quick save for the lines that need nothing amended). Selection is
   * the SAME `RowSelectionState` `BoardCellBreakdownDialog` keeps for its own bulk verbs -
   * ticked here, applied with `suggestedDecisionFor`, cleared once applied. A row that is
   * already covered or already carries a draft is not offered a box at all (`buildSelectColumn`
   * below): there is nothing a quick save would change on either.
   */
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const selectedKeys = React.useMemo(
    () => Object.keys(rowSelection).filter((key) => rowSelection[key]),
    [rowSelection],
  );
  const saveSelectedAsSuggested = React.useCallback(() => {
    void onDecideMany(selectedKeys);
    setRowSelection({});
  }, [selectedKeys, onDecideMany]);

  /**
   * The change icon this row shows in this column, or nothing (AC-C9).
   *
   * The column is read off what MOVED, through the same `changedFieldsOf` the lightbox
   * prints, so a date icon can never sit on a row whose date did not move. A line the book
   * touched without moving its quantity or its date still has a composed suggestion to
   * read, and that is what the Suggested column's icon is for.
   */
  const changeIcons = React.useCallback(
    (
      contribution: BoardContribution,
      column: 'required_date' | 'outstanding' | 'suggested',
    ) => {
      const lineId = contribution.project_line_id;
      const forLine = lineId ? annotations?.get(lineId) ?? [] : [];
      return forLine
        .filter((annotation) => {
          const keys = changedFieldsOf(annotation).map((field) => field.key);
          if (column === 'required_date') return keys.includes('date');
          if (column === 'outstanding') return keys.includes('qty');
          return !keys.includes('date') && !keys.includes('qty');
        })
        .map((annotation) => (
          <BoardChangeTable
            key={`${annotation.rowId}-${column}`}
            annotation={annotation}
            column={column}
            compact
          />
        ));
    },
    [annotations],
  );

  const columns = React.useMemo<ColumnDef<BoardContribution>[]>(
    () => [
      // The repo's own select column (the users list uses the same one), so a quick save is
      // a bulk action like any other rather than a second selection mechanism.
      buildSelectColumn<BoardContribution>({
        enableRow: (row) => canQuickSave(row.original, draft),
        disabledReason: (row) =>
          row.original.covered
            ? 'This line is already confirmed. Amend it to change what was decided.'
            : row.original.unplannable
              ? 'This line cannot be decided here: its sales order states no fulfilment location.'
              : draft[row.original.key]
                ? 'Already saved. Undo it before saving it again.'
                : undefined,
        rowLabel: (row) => `Select ${row.original.so_number} line ${row.original.line_no}`,
      }),
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
                {/* ONE line, the line number folded in beside the sales order number
                    (AC-C13, owner feedback 13 September 2026: "SOxxx (Line 1), so each row
                    is thinner"). Two STACKED lines made every row two text lines tall for a
                    fact that fits beside the first. Two spans rather than one string: the
                    order number is what a reader scans for and what a search matches, and
                    the line is a quieter qualifier of it. */}
                <span
                  className="truncate text-sm font-medium tabular-nums"
                  title={`${contribution.so_number} (Line ${contribution.line_no})`}
                >
                  {contribution.so_number}
                </span>{' '}
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {`(Line ${contribution.line_no})`}
                </span>
                {/* The same tick the grid puts on a fully-decided cell, here per row: one
                    row IS one contribution, so it is decided or it is not. */}
                <BoardDecidedMarker
                  revisions={decidedRevisions([contribution])}
                />
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
              onDirtyChange={dirtySetterFor(contribution.key)}
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
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1">
            {row.original.required_date ? (
              <span className="block min-w-0 truncate tabular-nums">
                {formatDateInMalaysia(row.original.required_date)}
              </span>
            ) : (
              <span className="text-muted-foreground">No date</span>
            )}
            {changeIcons(row.original, 'required_date')}
          </span>
        ),
        size: 130,
        minSize: 110,
      },
      {
        id: 'owed_qty',
        accessorFn: (row) => row.qty_outstanding ?? row.qty,
        header: 'Outstanding qty',
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1">
            <span className="block min-w-0 truncate tabular-nums">
              {row.original.qty_outstanding ?? row.original.qty}
            </span>
            {changeIcons(row.original, 'outstanding')}
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
          // NO BAR (AC-C13). The composition is already written out beside it in words, and
          // the bar cost the row a second text line to say the same thing less precisely.
          return (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="block min-w-0 truncate" title={text}>
                {text || (
                  <span className="text-muted-foreground">Nothing proposed</span>
                )}
              </span>
              {contribution.buy_origin === 'local' && hasBuy(parts) && (
                <Badge variant="secondary">Local</Badge>
              )}
              {changeIcons(contribution, 'suggested')}
            </span>
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
          // The composition alone, in section 2's words. NOT "Confirmed rev 1 · Buy 43":
          // the revision is already on the Verdict column and on the row's tick, and
          // repeating it here would cost the width the composition needs. No bar either
          // (AC-C13) - the words carry it, and the grid still draws one where a cell has
          // the room.
          const text = describeSupply(parts, contribution.fulfilment_location);
          return (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="block min-w-0 truncate" title={text}>
                {text}
              </span>
              {contribution.buy_origin === 'local' && hasBuy(parts) && (
                <Badge variant="secondary">Local</Badge>
              )}
            </span>
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
        // A PILL, and (D14) an Undo beside it once there is something a saved line can be
        // undone FROM - the only other way to shed one saved line today is the board-wide
        // "Undo all", which is not this line's answer to a quick save taken by mistake. D15
        // adds the OTHER icon, for the line that has not been saved at all: exactly one of
        // the two ever shows, since `canQuickSave` already requires no draft.
        cell: ({ row }) => {
          const contribution = row.original;
          const key = contribution.key;
          const drafted = Boolean(draft[key]);
          return (
            <div className="flex min-w-0 items-center gap-1">
              <BoardDecisionPill contribution={contribution} decision={draft[key] ?? null} />
              {canQuickSave(contribution, draft) ? (
                <Button
                  type="button"
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  title="Save as suggested"
                  aria-label={`Save ${contribution.so_number} line ${contribution.line_no} as suggested`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDecide(key, suggestedDecisionFor(contribution));
                  }}
                >
                  <Check className="size-3.5" aria-hidden />
                </Button>
              ) : null}
              {drafted ? (
                <Button
                  type="button"
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  aria-label={`Undo ${contribution.so_number} line ${contribution.line_no}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDecide(key, null);
                  }}
                >
                  <Undo2 className="size-3.5" aria-hidden />
                </Button>
              ) : null}
            </div>
          );
        },
        size: 190,
        minSize: 150,
        enableResizing: false,
      },
    ],
    [changeIcons, dirtySetterFor, draft, onDecide],
  );

  return (
    <>
    <PanelDataGrid
      title="Every contributing line"
      columns={columns}
      rows={contributions}
      getRowId={(row) => row.key}
      listingKey="projects.projects.view::project-fulfilment-board-list-v1"
      emptyTitle="Nothing is outstanding on this board"
      searchPlaceholder="Search sales order, customer, agent or product"
      searchOf={(row) =>
        [row.so_number, row.customer_name, row.agent_code, row.item_code]
          .filter(Boolean)
          .join(' ')
      }
      rowSelection={rowSelection}
      onRowSelectionChange={setRowSelection}
      enableRowSelection={(row) => canQuickSave(row.original, draft)}
      toolbar={
        <div className="flex flex-wrap items-center gap-2">
          {/* The same pair reorder planning carries, in the same place and the same shape
              (AC-C12): two icon buttons, each dead when it has nothing to do, so the
              control itself says whether the list is open or closed. */}
          <Button
            type="button"
            variant="outline"
            size="sm"
            mode="icon"
            className="h-8 w-8"
            data-testid="board-list-expand-all"
            title="Expand all"
            aria-label="Expand all"
            disabled={openKeys.length >= contributions.length}
            onClick={() => expandAll(contributions.map((row) => row.key))}
          >
            <ChevronsUpDown className="size-4" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            mode="icon"
            className="h-8 w-8"
            data-testid="board-list-collapse-all"
            title="Collapse all"
            aria-label="Collapse all"
            disabled={openKeys.length === 0}
            onClick={requestCollapseAll}
          >
            <ChevronsDownUp className="size-4" aria-hidden />
          </Button>
          {selectedKeys.length > 0 ? (
            <>
              <Badge variant="secondary" className="h-8 gap-1 px-2.5 text-sm">
                {`${selectedKeys.length} selected`}
              </Badge>
              <Button type="button" size="sm" onClick={saveSelectedAsSuggested}>
                {`Save as suggested (${selectedKeys.length})`}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setRowSelection({})}
              >
                Clear
              </Button>
            </>
          ) : null}
        </div>
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

/** Whether a Buy actually contributed to this composition (S3, R-Local). */
function hasBuy(parts: SupplyPart[] | null): boolean {
  return Boolean(parts?.some((part) => part.kind === 'buy' && Number(part.qty) > 0));
}
