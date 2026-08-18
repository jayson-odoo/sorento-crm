'use client';

import * as React from 'react';
import { AlertTriangle, Check, Pencil, X } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { amendNeedsReason, factorLabel } from '../../_shared/lib/fulfilmentBoard';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
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
  onDecide,
  onClose,
}: {
  cell: BoardCell;
  bucketLabel: string;
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => void;
  onClose: () => void;
}) {
  const decided = cell.contributions.filter((entry) => draft[entry.key]).length;
  /** The row being amended, if any. One at a time: two open forms is two half-decisions. */
  const [amending, setAmending] = React.useState<BoardContribution | null>(null);

  const columns = React.useMemo<ColumnDef<BoardContribution>[]>(
    () => [
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
        cell: ({ row }) => (
          <div className="min-w-0" data-testid={`rank-factors-${row.original.key}`}>
            <span className="block text-sm font-medium tabular-nums">
              {row.original.rank_score.toFixed(2)}
            </span>
            {/* Named in words a planner uses. These printed `po_document_sequence absent`
                until the captain asked what "w/c" meant and the same fault was found here:
                a database column name is not a label. */}
            <span className="block truncate text-[11px] text-muted-foreground" title={factorsTitle(row.original)}>
              {row.original.rank_factors
                .map((factor) =>
                  factor.present
                    ? factorLabel(factor.key)
                    : `${factorLabel(factor.key)} not recorded`,
                )
                .join(', ')}
            </span>
          </div>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Rank' },
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
    [cell.contributions, draft, onDecide],
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

          {/* The source strip again, because the dialog has to stand on its own: a reader who
              opened it from a cell they can no longer see still needs to know one cell can
              draw on several locations. */}
          <div className="flex flex-wrap gap-1.5">
            {cell.locations.map((entry) => (
              <span
                key={entry.location ?? '__none__'}
                className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(
                  entry.location ? 'draft' : 'rejected',
                )}`}
              >
                {`${entry.location ?? 'No location'} · ${entry.qty}`}
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

        <DialogFooter
          data-testid="cell-dialog-footer"
          className="shrink-0 gap-2 border-t p-4 sm:p-6"
        >
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
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
        ? `${factorLabel(factor.key)}: ${factor.value?.toFixed(2)} at weight ${factor.weight}`
        : `${factorLabel(factor.key)}: not recorded, so it is left out of the score entirely rather than counted as zero`,
    )
    .join('. ');
}
