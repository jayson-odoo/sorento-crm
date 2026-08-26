'use client';

import * as React from 'react';
import { AlertTriangle, Check, Info, Pencil, X } from 'lucide-react';
import { ColumnDef, RowSelectionState } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { OrderInquiryStatePill } from '../../_shared/components/OrderInquiryVerbPill';
import { rankingNote } from '../../_shared/lib/fulfilmentBoard';
import {
  SHORT_LABELS,
  contributionSuggestion,
  decisionBreakdown,
  movesOf,
  movesText,
  rowOf,
  rowText,
  suggestionBreakdown,
  takenByLocation,
} from '../../_shared/lib/supplyVocabulary';
import type { SuggestionRow } from '../../_shared/lib/supplyVocabulary';
import { amendSummary } from '../../_shared/lib/boardAmend';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import { BoardAmendDialog } from './BoardAmendDialog';
import { BoardRankPopover } from './BoardRankPopover';
import { BoardTrailPopover } from './BoardTrailPopover';
import { CellStockTable } from './CellStockTable';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * The breakdown behind one cell, and the decision on it (PLAN 13, journey step 4).
 *
 * A TABLE on the shared DataGrid, and the captain's reason for it is the whole design: "this
 * needs to be more table based instead of card based, so it is easier to see, and you need to
 * show me the SO order quantity, outstanding quantity also in the table ... then need to
 * show summary row whenever relevant". Ten lines as ten cards is a scroll; ten lines as ten rows
 * is a comparison, which is what a planner is actually doing here.
 *
 * The earlier version of this file argued for cards on the grounds that a row carries a
 * two-line explanation and a balance line. That argument does not survive the ask: the
 * per-row reasoning lives in the `title` of the cell that shows the composition, which is the
 * same `truncate` + `title` contract every other grid in this repo uses for long text.
 *
 * ONE VOCABULARY: what is still to go out is **outstanding**, everywhere on this screen. It
 * used to be "owed" in a column header, in a balance equation at the top and in a column of
 * the stock table, while the sales-order screens next door said "outstanding" for the same
 * figure - and a reader cannot tell a deliberate distinction from an accidental one.
 *
 * Approve / amend / reject are a ROW ACTION, and they write into the board's DRAFT, not into
 * the database (13.4): the decision that is persisted is still the whole sales order's, and the
 * order is what commits. Nothing here claims a cell committed anything.
 *
 * LAYOUT IS LOad-BEARING. The dialog is a flex column with its own max height; the body is the
 * only scrolling region and the footer is its SIBLING. Measured before the fix: at a 560px-tall
 * window the footer painted over the row's Approve button, so `document.elementFromPoint` at the
 * button's own centre returned the footer, and a planner on a laptop could not decide anything
 * at all. A modal whose action is unreachable is a modal that does not work (PRINCIPLES:
 * "modals are scrollable so the submit button is reachable").
 */
export function BoardCellBreakdownDialog({
  cell,
  bucketLabel,
  draft,
  onDecide,
  onClose,
}: {
  cell: BoardCell;
  bucketLabel: string;
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => void;
  onClose: () => void;
}) {
  /**
   * What this cell can say about its own ranking, from ONE place (`rankingNote`), so the number
   * in the Rank column and the sentence at the top of the dialog can never drift apart.
   */
  const ranking = rankingNote(cell);
  // Decided in the draft OR decided in the database: a line an active decision covers is as
  // decided as a line the planner has just approved, and counting only the draft made a cell of
  // confirmed lines read "0 decided".
  const decided = cell.contributions.filter(
    (entry) => Boolean(draft[entry.key]) || entry.covered,
  ).length;
  /**
   * Does this cell hold more than one product? On the product axis it never does - the cell IS
   * a product - and on a pivoted axis it routinely does.
   */
  const multiProduct = React.useMemo(
    () => new Set(cell.contributions.map((entry) => entry.item_code)).size > 1,
    [cell.contributions],
  );
  /** What the ladder proposes for the whole cell, by kind of source. */
  const suggestion = React.useMemo(() => suggestionBreakdown(cell), [cell]);
  /**
   * What was DECIDED for it, in the same rows and the same words (AC-D3).
   *
   * Empty until somebody decides something - confirmed on the order, or ticked into this
   * session's draft - and the card is not rendered then: a Decision card reading nothing
   * claims a decision was taken to do nothing.
   */
  const decision = React.useMemo(() => decisionBreakdown(cell, draft), [cell, draft]);
  /**
   * What has to physically MOVE for that decision, before Approve is pressed (section E).
   *
   * Derived from the same decision the card above renders, so the planner sees the
   * transfers their tick is about to raise rather than discovering them on another page.
   */
  const moves = React.useMemo(() => movesText(movesOf(cell, draft)), [cell, draft]);
  /**
   * How much the cell draws from each location, for the Taken column of the table above
   * (AC-B3). The decision when there is one and the suggestion otherwise, which is the same
   * switch the cell's colour bar uses.
   */
  const taken = React.useMemo(() => takenByLocation(cell, draft), [cell, draft]);
  /**
   * Did ANY contributing line record what the engine suggested?
   *
   * A revision frozen before `proposed_components` existed (AC-D1) recorded none, and an
   * empty Suggestion card would then read as "the engine proposed nothing for this" - which
   * is a claim about the ladder rather than about the record. Verified live on SO324132 rev
   * 1, whose four lines all predate the field.
   */
  /**
   * Was this suggestion composed by a ladder that no longer runs?
   *
   * A frozen proposal outlives the rule that made it, and its sentences say so - "MWH-IB
   * has 30 available in the IB group" is v3 reading ONE warehouse's availability, which
   * under v4 is not a reading anybody makes. Shown as a short label on the card's own title
   * rather than a sentence beside it: what a planner needs is to know they are looking at
   * history, and a paragraph explaining ladder versions is a feature explanation in the UI.
   *
   * Only a FROZEN proposal can be old. A live one is today's by definition, so an undecided
   * cell never carries the label.
   */
  const suggestionIsPreV4 = React.useMemo(
    () =>
      cell.contributions.some(
        (entry) =>
          entry.proposed?.components?.some((part) => !part.ladder) ?? false,
      ),
    [cell.contributions],
  );
  const suggestionRecorded = React.useMemo(
    () => cell.contributions.some((entry) => contributionSuggestion(entry) !== null),
    [cell.contributions],
  );
  /** The row being amended, if any. One at a time: two open forms is two half-decisions. */
  const [amending, setAmending] = React.useState<BoardContribution | null>(null);
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});

  const selectedKeys = React.useMemo(
    () => Object.keys(rowSelection).filter((key) => rowSelection[key]),
    [rowSelection],
  );

  /**
   * One verdict, applied to every ticked row.
   *
   * The captain's screenshot was eleven identical rows: deciding those one at a time is eleven
   * presses to say one thing. It writes into the same client draft a single decision does, so
   * nothing posts here and Confirm remains the only write.
   *
   * AMEND is deliberately not offered in bulk: an amendment is a quantity and a reason for ONE
   * line, and a single quantity applied to eleven different outstanding quantities is not a decision
   * anybody meant to make.
   */
  const decideSelected = React.useCallback(
    (decision: BoardDecision) => {
      for (const key of selectedKeys) onDecide(key, decision);
      setRowSelection({});
    },
    [selectedKeys, onDecide],
  );

  const columns = React.useMemo<ColumnDef<BoardContribution>[]>(
    () => [
      // The repo's own select column, the one the users list uses, so the header select-all and
      // its indeterminate state are not a second implementation.
      buildSelectColumn<BoardContribution>({
        enableRow: (row) => !row.original.unplannable && !row.original.covered,
        disabledReason: (row) =>
          row.original.covered
            ? 'This line is already confirmed. Amend it to change what was decided.'
            : 'This line cannot be decided here: its sales order states no fulfilment location.',
        rowLabel: (row) => `Select ${row.original.so_number} line ${row.original.line_no}`,
      }),
      {
        id: 'so_number',
        accessorFn: (row) => row.so_number,
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate text-sm font-medium" title={row.original.so_number}>
              {row.original.so_number}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {`Line ${row.original.line_no}`}
            </div>
          </div>
        ),
        // Labels the totals row under the first column, the way a spreadsheet labels its sum,
        // so the numbers below Ordered and Outstanding need no caption of their own.
        footer: () => <span className="text-muted-foreground">Total</span>,
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Sales order' },
      },
      // The product per line, ONLY when the cell holds more than one. On the product axis the
      // dialog's own title names it and every row repeats it, which is a column of one
      // repeated word on a table that is already wide; on a pivoted axis a sales-order row's
      // cell genuinely holds several products, and a list of lines that does not say which
      // product each one is cannot be read at all.
      ...(multiProduct
        ? [
            {
              id: 'item_code',
              accessorFn: (row: BoardContribution) => row.item_code,
              header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
              cell: ({ row }) => (
                <span className="block truncate text-sm" title={row.original.item_code}>
                  {row.original.item_code}
                </span>
              ),
              size: 150,
              minSize: 120,
              meta: { headerTitle: 'Product' },
            } as ColumnDef<BoardContribution>,
          ]
        : []),
      {
        id: 'customer_name',
        accessorFn: (row) => row.customer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.customer_name ?? ''}>
            {row.original.customer_name || 'Not recorded'}
          </span>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Customer' },
      },
      {
        // Who sold it, so the planner knows who to phone (the captain: agent "useful
        // information" beside every line).
        id: 'agent_code',
        accessorFn: (row) => row.agent_code ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        cell: ({ row }) =>
          row.original.agent_code ? (
            <span
              className="block truncate text-sm"
              title={row.original.agent_label ?? row.original.agent_code}
            >
              {row.original.agent_code}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Not stated</span>
          ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Agent' },
      },
      {
        id: 'project_label',
        accessorFn: (row) => row.project_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.project_label ?? ''}>
            {row.original.project_label || 'Not named on the order'}
          </span>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Project' },
      },
      {
        id: 'qty_ordered',
        accessorFn: (row) => row.qty_ordered ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Ordered" column={column} />,
        cell: ({ row }) =>
          row.original.qty_ordered ? (
            <span className="block truncate text-sm tabular-nums">
              {row.original.qty_ordered}
            </span>
          ) : (
            // Never derived from outstanding plus delivered on this side. A number the client
            // invented is a number nobody can be held to.
            <span className="text-sm text-muted-foreground">Not stated</span>
          ),
        footer: () => <span className="tabular-nums">{sumOf(cell.contributions, orderedOf)}</span>,
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Ordered' },
      },
      {
        id: 'qty_delivered',
        accessorFn: (row) => row.qty_delivered ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Delivered" column={column} />,
        cell: ({ row }) =>
          row.original.qty_delivered ? (
            <span className="block truncate text-sm tabular-nums">
              {row.original.qty_delivered}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Not stated</span>
          ),
        footer: () => (
          <span className="tabular-nums">
            {sumOf(cell.contributions, (row) => row.qty_delivered ?? '0')}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Delivered' },
      },
      {
        id: 'qty',
        accessorFn: (row) => outstandingOf(row),
        header: ({ column }) => <DataGridColumnHeader title="Outstanding" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm font-medium tabular-nums">
            {outstandingOf(row.original)}
          </span>
        ),
        footer: () => (
          <span className="tabular-nums">{sumOf(cell.contributions, outstandingOf)}</span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Outstanding' },
      },
      {
        id: 'required_date',
        accessorFn: (row) => row.required_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums">
            {row.original.required_date
              ? formatDateInMalaysia(row.original.required_date)
              : 'No date'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Delivery date' },
      },
      {
        id: 'fulfilment_location',
        accessorFn: (row) => row.fulfilment_location ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) =>
          row.original.fulfilment_location ? (
            <span className="block truncate text-sm" title={row.original.fulfilment_location}>
              {row.original.fulfilment_location}
            </span>
          ) : (
            <span className="text-sm text-destructive">No location</span>
          ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'sources',
        accessorFn: (row) => row.sources.map((source) => source.kind).join(' '),
        header: ({ column }) => <DataGridColumnHeader title="Sourced from" column={column} />,
        cell: ({ row }) => {
          const strip = row.original.sources
            .map(
              (source) =>
                `${sourceLabel(source, row.original.fulfilment_location)} ${source.qty}${sourceAt(
                  source,
                )}`,
            )
            .join(' · ');
          // The engine's own sentences. `spo_number` and `arrival_date` are always null
          // because the SPO and its date are INSIDE the sentence (deviation 2), so the
          // sentence is the only place the fact exists and it may never be dropped - it moves
          // BEHIND the info icon rather than out of the row.
          const why = row.original.sources.map((source) => source.reason).join(' ');
          const share = shareNote(row.original);
          return (
            <div className="min-w-0">
              <div className="flex items-start gap-1">
                <span className="min-w-0 flex-1 truncate text-sm tabular-nums">{strip}</span>
                {/* The two prose sentences behind the numbers above - why this rung fired,
                    and what was left for this line at its own pile - under one visible icon
                    rather than a silent `title` nobody hovers or two lines of wrapped text
                    (the captain: "don't explain too much", "put it under the tooltip"). The
                    numbers stay in the row; only the prose moves. */}
                {(why || share) && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        mode="icon"
                        variant="ghost"
                        size="sm"
                        aria-label="Why this composition"
                        data-testid={`source-info-${row.original.key}`}
                        className="size-5 shrink-0 text-muted-foreground"
                      >
                        <Info className="size-3.5" aria-hidden />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent
                      data-testid={`source-note-${row.original.key}`}
                      className="max-w-xs space-y-1 break-words"
                    >
                      {why && <p>{why}</p>}
                      {share && <p>{share}</p>}
                    </TooltipContent>
                  </Tooltip>
                )}
                {/* The whole ladder behind that strip, structured, under its own icon (the
                    captain: "need more justification ... STRUCTURED instead of plain text
                    explaining, you can put it under the tooltip"). */}
                <BoardTrailPopover contribution={row.original} />
              </div>
              {row.original.contested && (
                <span className="mt-0.5 inline-flex items-center gap-1 rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">
                  <AlertTriangle className="size-3" aria-hidden />
                  Contested
                </span>
              )}
            </div>
          );
        },
        size: 230,
        minSize: 160,
        meta: { headerTitle: 'Sourced from' },
      },
      {
        id: 'rank',
        accessorFn: (row) => row.rank_score,
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        // The cell is the RANK and nothing else. It used to carry the factor sentence too,
        // which was identical on every row - because the factors are identical there, which is
        // a fact about the POLICY, not about any row - and truncated mid-word. The captain:
        // "the word here is too long already, don't explain too much". The facts are per row
        // and wanted only when comparing two of them, so they are behind the icon; the policy's
        // own flatness is stated once at the top.
        //
        // The icon replaces the hover TITLE the facts used to live in ("how is the rank
        // calculated? can have an information tooltip to show the calculation"): hover prose
        // cannot be read on a touch screen, cannot be compared against a second row, and was
        // the very shape the captain rejected on the justification beside it.
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center justify-end gap-1">
            <span
              data-testid={`rank-factors-${row.original.key}`}
              className="min-w-0 truncate text-sm font-medium tabular-nums text-end"
            >
              {ranking ? ranking.cell : row.original.rank_score.toFixed(2)}
            </span>
            <BoardRankPopover contribution={row.original} note={ranking?.note} />
          </div>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Rank', cellClassName: 'text-end' },
      },
      {
        id: 'order_inquiry',
        accessorFn: (row) => row.order_inquiry?.inquiry_no ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Order inquiry" column={column} />
        ),
        // Beside the Decision, because it is the OTHER half of the same answer: the decision
        // is what was promised, the inquiry is what purchasing was actually told to do about
        // it and how far they have got. A dash means nobody has been told anything yet.
        cell: ({ row }) => {
          const inquiry = row.original.order_inquiry;
          if (!inquiry) return <span className="text-muted-foreground">-</span>;
          return (
            <div className="flex min-w-0 items-center gap-1.5">
              <span
                className="min-w-0 truncate tabular-nums"
                title={inquiry.inquiry_no ?? ''}
              >
                {inquiry.inquiry_no ?? '-'}
              </span>
              <OrderInquiryStatePill state={inquiry.state} />
            </div>
          );
        },
        size: 200,
        minSize: 150,
        meta: { headerTitle: 'Order inquiry' },
      },
      {
        id: 'decision',
        header: ({ column }) => <DataGridColumnHeader title="Decision" column={column} />,
        cell: ({ row }) => (
          <DecisionCell
            contribution={row.original}
            decision={draft[row.original.key] ?? null}
            onApprove={() => onDecide(row.original.key, { verdict: 'approved' })}
            onReject={() =>
              onDecide(row.original.key, {
                verdict: 'rejected',
                reason: 'Rejected on the planning board.',
              })
            }
            onUndo={() => onDecide(row.original.key, null)}
            onAmend={() => setAmending(row.original)}
          />
        ),
        size: 210,
        minSize: 170,
        enableSorting: false,
        meta: { headerTitle: 'Decision' },
      },
    ],
    [cell.contributions, draft, multiProduct, onDecide, ranking],
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        data-testid="cell-dialog-content"
        className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-6xl"
      >
        <DialogHeader className="shrink-0 space-y-2 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">
            {`${cell.item_code} · ${bucketLabel}`}
          </DialogTitle>
          {/* The decision, first and in two small cards: what is being asked for, and what
              the ladder proposes to do about it. The dialog used to open on a sentence and a
              table of lines, and the planner had to read a source strip per row to work out
              what the whole cell was being asked to decide - which is the one thing they came
              for. "across 1 line" is gone with it: the table below is the lines. */}
          <DialogDescription className="sr-only">
            {`${cell.total_qty} outstanding, ${decided} decided`}
          </DialogDescription>
          <div
            className={cn(
              'grid grid-cols-1 gap-3',
              decision.length > 0 ? 'sm:grid-cols-3' : 'sm:grid-cols-2',
            )}
          >
            <div
              data-testid="cell-quantity-needed"
              className="rounded-lg border border-border p-3"
            >
              <p className="text-xs text-muted-foreground">Quantity needed</p>
              <p className="text-2xl font-semibold tabular-nums">{cell.total_qty}</p>
              <p className="text-xs text-muted-foreground">
                {`${decided} decided`}
              </p>
            </div>

            <CompositionCard
              testId="cell-suggestion"
              rowTestId="suggestion"
              title={suggestionIsPreV4 ? 'Suggestion (before ladder v4)' : 'Suggestion'}
              rows={suggestion}
              empty={
                suggestionRecorded
                  ? 'Nothing proposed for this cell'
                  : 'Not recorded for this revision'
              }
            />

            {/* Beside the suggestion, never instead of it (AC-D3). SAME component, two
                inputs: two cards that merely resembled each other would drift, and the whole
                point is that a planner compares them at a glance. Rendered only once
                something IS decided. */}
            {decision.length > 0 ? (
              <CompositionCard
                testId="cell-decision"
                rowTestId="decision"
                title="Decision"
                rows={decision}
                empty=""
                moves={moves}
              />
            ) : null}
          </div>

          {/* Said ONCE, because it is a fact about the policy rather than about any row. It was
              repeated under every rank, eleven identical grey sentences saying nothing
              row-specific. */}
          {ranking?.note ? (
            <p className="text-sm text-muted-foreground break-words">{ranking.note}</p>
          ) : null}

          {/* What is actually AT each location, not only what is outstanding from it - the captain's
              "where will I need to source to fulfil", answered with facts, and the dialog has to
              carry it because a reader who opened it from a cell they can no longer see still
              needs to know one cell can draw on several locations.

              KEYED BY THE CELL, so the locations a reader expanded close when the dialog is
              pointed at a different cell: an expansion left open would otherwise show the
              previous cell's documents under the new cell's row. */}
          <CellStockTable
            key={`${cell.row_key ?? cell.item_code}|${cell.bucket_key}`}
            locations={cell.locations}
            itemCode={cell.item_code}
            groupNote={cell.location_group_note}
            taken={taken}
          />
        </DialogHeader>

        {/* The ONLY scrolling region, and it holds the row actions. The footer below is its
            sibling, so nothing in here can ever be painted over. */}
        <DialogBody
          data-testid="cell-dialog-body"
          className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 sm:p-6"
        >
          <PanelDataGrid<BoardContribution>
            title="Contributing lines"
            columns={columns}
            rows={cell.contributions}
            getRowId={(row) => row.key}
            listingKey="projects.projects.view::project-board-cell-breakdown"
            sortable
            rowSelection={rowSelection}
            onRowSelectionChange={setRowSelection}
            // A covered row is not selectable either: the bulk verbs are Approve and Reject,
            // and a bulk Reject sweeping up a confirmed line would silently un-decide it,
            // which is the very defect the covered state exists to stop.
            enableRowSelection={(row) => !row.original.unplannable && !row.original.covered}
            toolbar={
              selectedKeys.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  {/* Says exactly how many rows the verbs will act on. With a paginated cell
                      the header ticks this page, and this count is what was ticked - so the
                      strip never implies more than it will do. */}
                  <Badge variant="secondary" className="h-8 gap-1 px-2.5 text-sm">
                    {`${selectedKeys.length} selected`}
                  </Badge>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => decideSelected({ verdict: 'approved' })}
                  >
                    <Check className="size-4" aria-hidden />
                    Approve selected
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      decideSelected({
                        verdict: 'rejected',
                        reason: 'Rejected on the planning board.',
                      })
                    }
                  >
                    <X className="size-4" aria-hidden />
                    Reject selected
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setRowSelection({})}
                  >
                    Clear
                  </Button>
                </div>
              ) : undefined
            }
            emptyTitle="No line contributes to this cell"
            emptyBody="Nothing in the selection is outstanding for this product by this date."
            pageSize={25}
          />

        </DialogBody>

        {/* The editor is a DIALOG OVER THIS ONE, not a panel under the table. It used to be
            appended below a 25-row grid inside this same scroll region, with no focus moved
            to it: pressing Amend moved nothing the planner could see, so the form was never
            found and the verb read as broken (the captain: "the amend is not working"). */}
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
      </DialogContent>
    </Dialog>
  );
}

/** The verbs, as pills, so a decided row reads at a glance in a long list. */
const VERDICT_PALETTE: Record<string, string> = {
  approved: 'active',
  amended: 'submitted',
  rejected: 'rejected',
};

/**
 * One row's verdict: the pill once it has one, the three verbs while it does not.
 *
 * A line whose sales order states no location gets no verb at all (AC-FP16) - it cannot be
 * planned here, and offering a button that would refuse is worse than offering none.
 *
 * A line an active decision COVERS gets one verb, Amend. Approve would approve a decision
 * already taken, Reject would silently un-decide it (the confirmation supersedes the revision
 * and writes only what it is sent), and Undo undoes a draft entry that does not exist. The row
 * states which revision decided it and what that revision froze.
 */
/**
 * ONE composition, as the dialog's header states it: a badge per kind and the quantity per
 * location beside it (AC-D3).
 *
 * One component for BOTH the suggestion and the decision, because the two are read against
 * each other: a second card that merely looked like this one would drift the first time
 * either changed, and the comparison is the whole reason they sit side by side.
 *
 * Only the kinds with a quantity, in one fixed order, so Buy sits above the stock rows
 * wherever it appears. The empty kinds used to be listed and muted, and on a real cell that
 * was three lines of nothing around the one line that said what to do.
 */
function CompositionCard({
  testId,
  rowTestId,
  title,
  rows,
  empty,
  moves,
}: {
  testId: string;
  /** Prefix for the per-kind rows: `suggestion-buy`, `decision-shared`. */
  rowTestId: string;
  title: string;
  rows: SuggestionRow[];
  empty: string;
  /**
   * The movements this composition implies ("454 DC1-BB -> BRW-BB"), on the Decision card
   * only. Empty when nothing has to move, and the line is not drawn then: a Moves row
   * reading nothing claims a decision was taken to carry nothing.
   */
  moves?: string;
}) {
  return (
    <div data-testid={testId} className="rounded-lg border border-border p-3">
      <p className="mb-1.5 text-xs text-muted-foreground">{title}</p>
      <div className="space-y-1">
        {rows.length === 0 && empty ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : null}
        {rows.map((row) => (
          <div
            key={row.key}
            data-testid={`${rowTestId}-${row.key}`}
            className="flex flex-wrap items-center gap-1.5 text-sm"
          >
            <Badge variant="primary" appearance="light" size="sm">
              {row.label}
            </Badge>
            {/* The quantity PER LOCATION ("454 from DC1-BB, 267 from MWH-BB"), not a total
                beside a bare list of codes: the split IS the instruction, and somebody has
                to key each movement of it. */}
            <span className="min-w-0 break-words tabular-nums">{rowText(row)}</span>
            {/* The rule's own sentence, and only when every source on the row gives the same
                one: a Buy for "nothing free anywhere" and a Buy for "beyond the lead time
                window" are the same number for opposite reasons, and this card is where that
                is decided. */}
            {row.note ? (
              <span className="w-full text-xs text-muted-foreground">{row.note}</span>
            ) : null}
          </div>
        ))}
      </div>
      {moves ? (
        <p data-testid={`${rowTestId}-moves`} className="mt-2 border-t border-border pt-1.5 text-xs">
          <span className="text-muted-foreground">Moves: </span>
          <span className="break-words tabular-nums">{moves}</span>
        </p>
      ) : null}
    </div>
  );
}

function DecisionCell({
  contribution,
  decision,
  onApprove,
  onReject,
  onUndo,
  onAmend,
}: {
  contribution: BoardContribution;
  decision: BoardDecision | null;
  onApprove: () => void;
  onReject: () => void;
  onUndo: () => void;
  onAmend: () => void;
}) {
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
        {/* MUTED, not one of the verdict colours: this is not a verdict the planner gave on
            this board, it is a decision that is already in the database. */}
        {/* WRAPS: a composition is as long as it is ("Reserve 20 BRW-BB · Borrow 10 · Buy
            13"), and a pill that overflows a fixed column silently loses its last term -
            which on this one is the quantity being bought. */}
        <span
          className={`${STATUS_PILL_BASE} max-w-full whitespace-normal break-words text-start normal-case ${statusPillClass(
            'closed',
          )}`}
          title={contribution.decision.amend_reason ?? ''}
        >
          {confirmedSummary(contribution.decision, contribution.fulfilment_location)}
        </span>
        <Button type="button" size="sm" variant="outline" onClick={onAmend}>
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
          className={`${STATUS_PILL_BASE} max-w-full whitespace-normal break-words text-start normal-case ${statusPillClass(
            VERDICT_PALETTE[decision.verdict],
          )}`}
          title={decision.reason ?? ''}
        >
          {/* An amendment can now reserve, borrow and buy at once, so the pill states the
              COMPOSITION: naming one of the three describes a decision nobody took. */}
          {decision.verdict === 'approved'
            ? 'Approved'
            : decision.verdict === 'amended'
              ? amendSummary(decision, contribution.fulfilment_location)
              : 'Rejected'}
        </span>
        {/* Amend stays offered on a decided row. Undo-then-Amend is two presses that throw
            away the composition the planner already made. */}
        <Button type="button" size="sm" variant="outline" onClick={onAmend}>
          <Pencil className="size-4" aria-hidden />
          Amend
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onUndo}>
          Undo
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button type="button" size="sm" onClick={onApprove}>
        <Check className="size-4" aria-hidden />
        Approve
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={onAmend}>
        <Pencil className="size-4" aria-hidden />
        Amend
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={onReject}>
        <X className="size-4" aria-hidden />
        Reject
      </Button>
    </div>
  );
}

/**
 * A figure the server actually stated, as opposed to one it left out.
 *
 * A NULL is "not stated", never 0. The two are opposite instructions - 0 means do not look
 * here, nothing stated means nobody has said where to look.
 */
function present(value: string | null | undefined): boolean {
  return value !== null && value !== undefined;
}

/**
 * Why this line's Reserve is the size it is: who was ahead of it at its OWN location, and what
 * was left when it was reached (PLAN 13.7, the fair-share amendment).
 *
 * The captain's card, live: pile Available -8013 at BRW-BB, and yet a Reserve of 80 stands -
 * because 6 lines ahead wanted 388 of the 1015 on hand and 627 remained for this line. The strip
 * above states the pile; this states the line. THEY ARE DIFFERENT NUMBERS AND NEITHER IS EVER
 * PRINTED UNDER THE OTHER'S LABEL: "Available" is the whole pile, "left for this line" is this
 * line's share at its own location.
 *
 * It says what remained and claims NOTHING about what may be reserved. `qty_proposed_reserve` can
 * exceed this figure, because the shared pool is a second source with its own queue - a live line
 * reading "0 left for this line" still reserved 9 from the pool, and the source strip beside it
 * already says "Reserve 9 at BRW".
 *
 * Absent is absent: a line the server sent no share for, and a line whose sales order states no
 * location (it has no pile to be queued at), get no sentence rather than a 0.
 */
function shareNote(contribution: BoardContribution): string | null {
  if (contribution.unplannable) return null;
  if (!present(contribution.available_to_this_line)) return null;
  const left = contribution.available_to_this_line;
  const at = contribution.fulfilment_location;
  const lines = contribution.lines_ahead ?? 0;
  if (lines === 0) {
    return `First in the queue${at ? ` at ${at}` : ''} · ${left} left for this line`;
  }
  const wanted = present(contribution.so_qty_ahead) ? contribution.so_qty_ahead : '0';
  return `${lines} line${lines === 1 ? '' : 's'} ahead wanting ${wanted} · ${left} left for this line${
    at ? ` at ${at}` : ''
  }`;
}

/**
 * What a covered row reads: which revision decided it, and what that revision froze.
 *
 * The composition comes from `amendSummary`, the same function an amended row uses, because a
 * frozen composition and an amended one are the same four kinds in the same order - and two
 * renderings of one composition is how they come to disagree.
 */
/**
 * PRIVATE since AC-D4. It was exported for the board's list view, whose single Proposal
 * column became Suggested and Decided - and the Decided column states the composition alone
 * (`describe`), because the revision is already on the Verdict column and on the row's tick.
 * The one remaining caller is the row strip below.
 */
function confirmedSummary(
  decision: NonNullable<BoardContribution['decision']>,
  ownLocation?: string | null,
): string {
  return `Confirmed rev ${decision.revision_no} · ${amendSummary(
    {
      verdict: 'amended',
      timely_spo_qty: decision.timely_spo_qty,
      reserve: decision.reserve,
      borrow: decision.borrow.map((row) => ({
        source: row.source,
        warehouse_id: row.warehouse_id ?? '',
        warehouse_code: row.location ?? null,
        donor_project_id: row.donor_project_id ?? null,
        qty: row.qty,
        reason: row.reason,
        // Carried, not dropped: it is what tells "Borrow (order)" from "Borrow (other)"
        // on a frozen composition, which arrives with no rung at all.
        donor_so_number: row.donor_so_number ?? null,
      })),
      buy_qty: decision.buy_qty,
    },
    ownLocation,
  )}`;
}

/**
 * Exported so the planning-changes batch page (`PLAN-so-book-diff-replanning.md`) can print a
 * replan/qty_up row's proposal in the same words the board's own breakdown does, rather than a
 * second sentence-builder that drifts from this one.
 *
 * SECTION 2'S WORDS, off `SHORT_LABELS`. This strip used to print ladder v2's rung names
 * (Pool / Group take / Group borrow / Cross-group borrow) inside a popover whose Suggestion
 * card, colour bar and legend all said Shared / Own / Borrow for the same quantities. One
 * composition may not be described twice: the plan's table is the only vocabulary.
 *
 * `ownLocation` is the line's own warehouse code, which is what tells the agent's own group
 * from the shared pool for a source that carries no rung.
 */
export function sourceLabel(
  source: BoardContribution['sources'][number],
  ownLocation?: string | null,
): string {
  // The WHOLE source, never a kind and a rung pulled out of it: the location is what tells
  // the agent's own group from the shared pool when the source carries no rung, and passing
  // the pieces by hand is how it came to be left out.
  const row = rowOf(source, ownLocation);
  return row ? SHORT_LABELS[row] : 'Cannot be sourced';
}

/**
 * Where the quantity comes from, in the preposition each kind takes.
 *
 * A Reserve is held AT a location; a Borrow comes FROM somebody else's. "Borrow 10 at MWH-IB"
 * reads as stock this line has there, which is the opposite of what a borrow is. A group
 * borrow names its donor SO line instead, when one was stated - "from SO371334 line 2" is
 * the identity that matters, the location is secondary.
 */
/** Exported for the same reason `sourceLabel` is - see its comment. */
export function sourceAt(source: BoardContribution['sources'][number]): string {
  if (source.kind === 'borrow' && source.rung === 'group_borrow' && source.donor_so_number) {
    const line =
      source.donor_line_no !== null && source.donor_line_no !== undefined
        ? ` line ${source.donor_line_no}`
        : '';
    return ` from ${source.donor_so_number}${line}`;
  }
  if (!source.location) return '';
  return source.kind === 'borrow' ? ` from ${source.location}` : ` at ${source.location}`;
}

/** The outstanding quantity: the server's own name for it when it sends one. */
function outstandingOf(contribution: BoardContribution): string {
  return contribution.qty_outstanding ?? contribution.qty;
}

function orderedOf(contribution: BoardContribution): string {
  return contribution.qty_ordered ?? '0';
}

function sumOf(
  contributions: BoardContribution[],
  pick: (contribution: BoardContribution) => string,
): string {
  return fromMinor(
    contributions.reduce((total, contribution) => total + toMinor(pick(contribution)), 0),
  );
}

// The evidence behind the score used to be a `title` sentence built here. It is a table now
// (`BoardRankPopover`): the captain asked to see the CALCULATION, and one row per factor with
// its fact, score, weight and product - plus the division that produces the number - is the
// shape a person can check. Two renderings of one arithmetic is how they drift.
