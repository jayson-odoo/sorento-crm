'use client';

import * as React from 'react';
import { AlertTriangle, Check, Pencil, X } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { amendNeedsReason, factorLabel } from '../../_shared/lib/fulfilmentBoard';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import type {
  BoardCell,
  BoardCellLocation,
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * The breakdown behind one cell, and the decision on it (PLAN 13, journey step 4).
 *
 * A TABLE on the shared DataGrid, and the captain's reason for it is the whole design: "this
 * needs to be more table based instead of card based, so it is easier to see, and you need to
 * show me the SO order quantity, owed / outstanding quantity also in the table ... then need to
 * show summary row whenever relevant". Ten lines as ten cards is a scroll; ten lines as ten rows
 * is a comparison, which is what a planner is actually doing here.
 *
 * The earlier version of this file argued for cards on the grounds that a row carries a
 * two-line explanation and a balance line. That argument does not survive the ask: the balance
 * is now stated ONCE for the whole cell at the TOP (the captain: "7 owed = 7 reserve + 0
 * incoming + 0 buy, you should show at the top"), and the per-row reasoning lives in the
 * `title` of the cell that shows the composition, which is the same `truncate` + `title`
 * contract every other grid in this repo uses for long text.
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
  rankingIsFlat = false,
  onDecide,
  onClose,
}: {
  cell: BoardCell;
  bucketLabel: string;
  draft: BoardDraft;
  /**
   * The SERVER's verdict that the active policy separates none of these rows (13.5). When it
   * does, every score is 0.00, and a column of 0.00 reads as a considered ranking rather than
   * as no ranking, so the number is suppressed instead.
   */
  rankingIsFlat?: boolean;
  onDecide: (key: string, decision: BoardDecision | null) => void;
  onClose: () => void;
}) {
  const decided = cell.contributions.filter((entry) => draft[entry.key]).length;
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
   * line, and a single quantity applied to eleven different owed quantities is not a decision
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
        enableRow: (row) => !row.original.unplannable,
        disabledReason: () =>
          'This line cannot be decided here: its sales order states no fulfilment location.',
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
        // so the numbers below Ordered and Owed need no caption of their own.
        footer: () => <span className="text-muted-foreground">Total</span>,
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'Sales order' },
      },
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
            // Never derived from owed plus delivered on this side. A number the client
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
        accessorFn: (row) => owedOf(row),
        header: ({ column }) => <DataGridColumnHeader title="Owed" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm font-medium tabular-nums">
            {owedOf(row.original)}
          </span>
        ),
        footer: () => <span className="tabular-nums">{sumOf(cell.contributions, owedOf)}</span>,
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Owed' },
      },
      {
        id: 'required_date',
        accessorFn: (row) => row.required_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Required" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm tabular-nums">
            {row.original.required_date
              ? formatDateInMalaysia(row.original.required_date)
              : 'No date'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Required' },
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
            .map((source) =>
              `${sourceLabel(source.kind)} ${source.qty}${
                source.location ? ` at ${source.location}` : ''
              }`,
            )
            .join(' · ');
          // The engine's own sentences, reachable on the cell rather than wrapped into the
          // row: `spo_number` and `arrival_date` are always null because the SPO and its date
          // are INSIDE the sentence (deviation 2), so the sentence is the only place the fact
          // exists and it may never be dropped.
          const why = row.original.sources.map((source) => source.reason).join(' ');
          return (
            <div className="min-w-0" title={why}>
              <span className="block truncate text-sm tabular-nums">{strip}</span>
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
        // and wanted only when comparing two of them, so they are a tooltip; the policy's own
        // flatness is stated once at the top.
        cell: ({ row }) => (
          <span
            data-testid={`rank-factors-${row.original.key}`}
            className="block truncate text-sm font-medium tabular-nums text-end"
            title={factorsTitle(row.original)}
          >
            {rankingIsFlat ? 'Not ranked' : row.original.rank_score.toFixed(2)}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Rank', cellClassName: 'text-end' },
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
    [cell.contributions, draft, onDecide, rankingIsFlat],
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
          <DialogDescription className="min-w-0 break-words">
            {`${cell.total_qty} across ${cell.contributions.length} line${
              cell.contributions.length === 1 ? '' : 's'
            }, ${decided} decided`}
          </DialogDescription>

          {/* THE SUMMARY, AT THE TOP (the captain). One balance for the whole cell, stated
              before the detail rather than repeated under every row. */}
          <div
            data-testid="cell-balance"
            className="text-sm font-medium tabular-nums break-words"
          >
            {cellBalanceLine(cell)}
          </div>

          {/* Said ONCE, because it is a fact about the policy rather than about any row. It was
              repeated under every rank, eleven identical grey sentences saying nothing
              row-specific. */}
          {rankingIsFlat && (
            <p className="text-sm text-muted-foreground break-words">
              The active policy separates none of these rows.
            </p>
          )}

          {/* The source strip again, because the dialog has to stand on its own: a reader who
              opened it from a cell they can no longer see still needs to know one cell can
              draw on several locations. */}
          {/* What is actually AT each location, not only what is owed from it. The captain's
              "where will I need to source to fulfil", answered with facts. */}
          <div className="flex flex-wrap gap-1.5">
            {cell.locations.map((entry) => (
              <span
                key={entry.location ?? '__none__'}
                data-testid={`cell-location-${entry.location ?? 'none'}`}
                title={locationTitle(entry)}
                className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(
                  entry.location ? 'draft' : 'rejected',
                )}`}
              >
                {locationStrip(entry)}
              </span>
            ))}
          </div>
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
            enableRowSelection={(row) => !row.original.unplannable}
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
            emptyBody="Nothing in the selection owes this product by this date."
            pageSize={25}
          />

          {amending && (
            <AmendPanel
              contribution={amending}
              onCancel={() => setAmending(null)}
              onSave={(decision) => {
                onDecide(amending.key, decision);
                setAmending(null);
              }}
            />
          )}
        </DialogBody>
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
 */
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

  if (decision) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        <span
          className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(
            VERDICT_PALETTE[decision.verdict],
          )}`}
          title={decision.reason ?? ''}
        >
          {decision.verdict === 'approved'
            ? 'Approved'
            : decision.verdict === 'amended'
              ? `Amended to reserve ${decision.reserve_qty}`
              : 'Rejected'}
        </span>
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
 * Amending one row, under the table rather than inside a cell.
 *
 * A quantity input and a mandatory-reason box do not fit a fixed-width grid cell without
 * truncating the very thing they exist to capture, so the form gets the width it needs and the
 * table keeps its shape. Inside the scroll region, so it can never be covered by the footer.
 */
function AmendPanel({
  contribution,
  onSave,
  onCancel,
}: {
  contribution: BoardContribution;
  onSave: (decision: BoardDecision) => void;
  onCancel: () => void;
}) {
  const proposedReserve = contribution.sources
    .filter((source) => source.kind === 'reserve')
    .reduce((total, source) => total + toMinor(source.qty), 0);
  const [reserveQty, setReserveQty] = React.useState(fromMinor(proposedReserve));
  const [reason, setReason] = React.useState('');

  const needsReason = amendNeedsReason(contribution, reserveQty);
  const canSave = !needsReason || reason.trim().length > 0;

  return (
    <section className="space-y-2 rounded-lg border border-border p-3">
      <h4 className="text-sm font-medium">
        {`Amend ${contribution.so_number} line ${contribution.line_no}`}
      </h4>
      <div className="flex flex-wrap items-center gap-2">
        <label
          className="text-2xs uppercase tracking-wide text-muted-foreground"
          htmlFor={`amend-reserve-${contribution.key}`}
        >
          Reserve
        </label>
        <Input
          id={`amend-reserve-${contribution.key}`}
          type="number"
          min="0"
          step="any"
          value={reserveQty}
          aria-label={`Reserve for ${contribution.so_number} line ${contribution.line_no}`}
          onChange={(event) => setReserveQty(event.target.value)}
          className="h-8 w-28 tabular-nums"
        />
        <span className="text-sm text-muted-foreground">
          {contribution.fulfilment_location}
        </span>
      </div>
      {needsReason && (
        <div className="space-y-1">
          <label
            className="block text-2xs uppercase tracking-wide text-muted-foreground"
            htmlFor={`amend-reason-${contribution.key}`}
          >
            Reason <span className="text-destructive">*</span>
          </label>
          <Textarea
            id={`amend-reason-${contribution.key}`}
            rows={2}
            value={reason}
            placeholder="In your own words"
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!canSave}
          onClick={() =>
            onSave({
              verdict: 'amended',
              reserve_qty: reserveQty,
              reason: reason.trim() || undefined,
            })
          }
        >
          Save the amendment
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </section>
  );
}

/**
 * One location pill: what is owed here, then what is here.
 *
 * A NULL stock figure is "not stated", never 0. The two are opposite instructions - 0 free
 * means do not look here, nothing stated means nobody has said where to look - and a line whose
 * sales order names no location has every stock figure null by construction.
 */
function locationStrip(entry: BoardCellLocation): string {
  const parts = [`${entry.location ?? 'No location'} · ${entry.qty} owed`];
  if (entry.qty_on_hand === null || entry.qty_on_hand === undefined) {
    parts.push('Stock not stated');
  } else {
    parts.push(`${entry.qty_on_hand} on hand`);
    if (entry.qty_free !== null && entry.qty_free !== undefined) {
      parts.push(`${entry.qty_free} free`);
    }
    if (entry.qty_incoming !== null && entry.qty_incoming !== undefined) {
      parts.push(`${entry.qty_incoming} incoming`);
    }
  }
  return parts.join(' · ');
}

/** The documents behind the incoming stock: "80 incoming" from nowhere is a rumour. */
function locationTitle(entry: BoardCellLocation): string {
  const legs = (entry.incoming ?? []).map((leg) =>
    `${leg.spo_number}${leg.arrival_date ? ` arrives ${formatDateInMalaysia(leg.arrival_date)}` : ''}: ${leg.qty}`,
  );
  return legs.length > 0 ? legs.join('. ') : locationStrip(entry);
}

function sourceLabel(kind: BoardContribution['sources'][number]['kind']): string {
  if (kind === 'reserve') return 'Reserve';
  if (kind === 'timely_spo') return 'Incoming';
  if (kind === 'buy') return 'Buy';
  return 'Cannot be sourced';
}

/** The owed quantity: the server's own name for it when it sends one. */
function owedOf(contribution: BoardContribution): string {
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

/**
 * "100 owed = 40 reserve + 0 incoming + 60 buy", for the WHOLE cell, at the top.
 *
 * The captain asked for it there because it is the answer to the question the cell was opened
 * to ask. Under each row it was the same arithmetic said N times and summed by nobody.
 */
function cellBalanceLine(cell: BoardCell): string {
  const of = (kind: string) =>
    cell.contributions
      .flatMap((contribution) => contribution.sources)
      .filter((source) => source.kind === kind)
      .reduce((total, source) => total + toMinor(source.qty), 0);
  const owed = cell.contributions.reduce(
    (total, contribution) => total + toMinor(owedOf(contribution)),
    0,
  );
  return `${fromMinor(owed)} owed = ${fromMinor(of('reserve'))} reserve + ${fromMinor(
    of('timely_spo'),
  )} incoming + ${fromMinor(of('buy'))} buy`;
}

/** The evidence behind the score, for the reader who wants it. Words, never column names. */
function factorsTitle(contribution: BoardContribution): string {
  return contribution.rank_factors
    .map((factor) =>
      factor.present
        ? `${factorLabel(factor.key)}: ${factor.raw ?? factor.value?.toFixed(2)}, scored ${factor.value?.toFixed(2)}, weighted ${factor.weight}`
        : `${factorLabel(factor.key)}: not recorded, so it is left out of the score entirely rather than counted as zero`,
    )
    .join('. ');
}
