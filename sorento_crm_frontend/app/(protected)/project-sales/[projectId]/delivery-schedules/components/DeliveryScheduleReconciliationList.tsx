'use client';

import * as React from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleProductPicker } from './DeliveryScheduleProductPicker';

/**
 * The columns that need a decision, as a table, each row carrying the fix for its own problem.
 *
 * Two reports shaped this. The first: "ya I know I need to fix this, but how" - the section
 * used to be a wall of sentences with nothing to press, so every row now states the problem
 * AND offers the one action that ends it, in the place the problem is read. The second: the
 * sentences-with-controls layout that answered it grew into a wall of its own, so the same
 * facts are now a table - one row per column, the three numbers in their own columns where
 * they line up and can be compared down the page rather than read out of a sentence.
 *
 * The shared DataGrid, per ARCHITECTURE-RULES: fixed layout, resizable columns, an explicit
 * size on every column. The problem sentence is truncated with its full text on `title` -
 * that is the trade a table makes, and the column can be dragged wider when the whole
 * sentence is wanted.
 *
 * Client-side: the columns are already in the version response (thirty-odd of them at most),
 * so paging or sorting them at the server would be a round trip for data in the browser.
 */
export function DeliveryScheduleReconciliationList({
  columns,
  canEdit,
  poOptions,
  onJump,
  onFixQuantities,
  onResolveProduct,
  onDismissColumn,
}: {
  /** The columns that do not reconcile, plus any carrying a warning or a dismissal. */
  columns: ColumnState[];
  canEdit: boolean;
  /** The products the PO orders, which is what the pickers offer. */
  poOptions: SearchableSelectOption[];
  onJump: (columnKey: string) => void;
  /** Jump to the column AND put the cursor in the first quantity that can be typed into. */
  onFixQuantities: (columnKey: string) => void;
  onResolveProduct: (columnIndex: number, productId: string) => void;
  /** Overrule this column's check as a false signal, or put it back under it. */
  onDismissColumn?: (
    columnIndex: number,
    dismissed: boolean,
    reason?: string,
  ) => void;
}) {
  const tableColumns = React.useMemo<ColumnDef<ColumnState>[]>(
    () => [
      {
        id: 'code',
        accessorKey: 'key',
        header: 'Code',
        size: 190,
        cell: ({ row }) => {
          const column = row.original;
          const name = column.productCode ?? column.customerCode ?? 'Unidentified column';
          return (
            <div className="min-w-0">
              {/* The jump survives as the column's own name: the reviewer still wants to go
                  and look at it, and a name is a more honest target than a whole row. */}
              <button
                type="button"
                onClick={() => onJump(column.key)}
                aria-label={`Go to ${
                  column.productCode ?? column.customerCode ?? 'the unidentified column'
                } in the schedule`}
                title={name}
                className="block max-w-full truncate rounded-sm text-start text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              >
                {name}
              </button>
              {column.productCode && column.customerCode && (
                <span
                  className="mt-0.5 block truncate text-xs text-muted-foreground"
                  title={column.customerCode}
                >
                  {column.customerCode}
                </span>
              )}
            </div>
          );
        },
      },
      {
        id: 'status',
        accessorKey: 'reconciled',
        header: 'Status',
        size: 120,
        cell: ({ row }) => <StatusPill column={row.original} />,
      },
      {
        id: 'ourTotal',
        accessorKey: 'ourTotal',
        header: 'Schedule qty',
        size: 110,
        meta: { headerClassName: 'text-end', cellClassName: 'text-end tabular-nums' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.ourTotal}</span>,
      },
      {
        id: 'reportedTotal',
        accessorKey: 'reportedTotal',
        header: 'Reported total',
        size: 120,
        cell: ({ row }) => (
          <NumberOrNote value={row.original.reportedTotal} missing="Not printed" />
        ),
      },
      {
        id: 'poQty',
        accessorKey: 'poQty',
        header: 'PO qty',
        size: 110,
        cell: ({ row }) => (
          <NumberOrNote value={row.original.poQty} missing="Not on the PO" />
        ),
      },
      {
        id: 'problem',
        accessorKey: 'index',
        header: 'Problem',
        size: 320,
        cell: ({ row }) => <ProblemCell column={row.original} />,
      },
      {
        id: 'action',
        accessorKey: 'key',
        header: 'Action',
        size: 300,
        cell: ({ row }) => (
          <RowActions
            column={row.original}
            canEdit={canEdit}
            poOptions={poOptions}
            onFixQuantities={onFixQuantities}
            onResolveProduct={onResolveProduct}
            onDismissColumn={onDismissColumn}
          />
        ),
      },
    ],
    [canEdit, onDismissColumn, onFixQuantities, onJump, onResolveProduct, poOptions],
  );

  const table = useReactTable({
    columns: tableColumns,
    data: columns,
    getRowId: (row) => row.key,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={columns.length}
      // Column personalisation OFF, deliberately: unset, the grid keys saved widths on the
      // URL, which here carries a schedule VERSION id - a per-user config row per document,
      // never read again. It also leaves the grid in its skeleton state until something else
      // re-renders it.
      listingKey=""
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="Nothing to fix."
    >
      <Card data-testid="reconciliation-list">
        <CardTable>
          {/* Seven columns are wider than a phone, so the table scrolls inside its own
              container rather than dragging the page sideways. */}
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}

/**
 * What this column is, in one word and one colour.
 *
 * Four states, and they are not interchangeable: blocked holds up the confirm, a warning
 * never does, a dismissal is a person overruling a block, and reconciled is a row that is
 * only listed because it carries one of the other two.
 */
function StatusPill({ column }: { column: ColumnState }) {
  if (column.dismissed) {
    return (
      <Badge variant="secondary" size="sm">
        Dismissed
      </Badge>
    );
  }
  if (column.blockers.length > 0) {
    return (
      <Badge variant="destructive" appearance="light" size="sm">
        Blocked
      </Badge>
    );
  }
  if (column.warning) {
    return (
      <Badge variant="warning" appearance="light" size="sm">
        Warning
      </Badge>
    );
  }
  return (
    <Badge variant="success" appearance="light" size="sm">
      Reconciled
    </Badge>
  );
}

/** A quantity, or what its absence means. Never a bare dash: "0" and "not given" differ. */
function NumberOrNote({ value, missing }: { value: string | null; missing: string }) {
  if (value === null)
    return <span className="text-xs text-muted-foreground">{missing}</span>;
  return <span className="tabular-nums">{value}</span>;
}

/**
 * Every sentence the check wrote about this column, and the dismissal that overruled them.
 *
 * Truncated with the whole text on `title`, which is the price of a table. The numbers the
 * sentences quote are in their own columns beside this one, so what is cut is the wording
 * rather than the facts.
 */
function ProblemCell({ column }: { column: ColumnState }) {
  const sentences = column.blockers.map((blocker) => blocker.detail);
  const warning = column.warning;

  if (sentences.length === 0 && !warning) {
    return <span className="text-xs text-muted-foreground">Agrees with the PO</span>;
  }

  return (
    <div className="min-w-0 space-y-1">
      {sentences.map((sentence, index) => (
        <p
          key={column.blockers[index].code}
          data-testid="reconciliation-detail"
          className="truncate text-sm text-muted-foreground"
          title={sentence}
        >
          {sentence}
        </p>
      ))}
      {warning && (
        <p
          data-testid="reconciliation-warning"
          className="truncate text-sm text-[var(--color-warning-accent,var(--color-yellow-700))]"
          title={warning}
        >
          {warning}
        </p>
      )}
      {column.dismissed && (
        <p
          data-testid="reconciliation-dismissed"
          className="truncate text-xs text-muted-foreground"
          title={`Dismissed as a false signal${
            column.dismissedByName ? ` by ${column.dismissedByName}` : ''
          }${column.dismissedReason ? `: ${column.dismissedReason}` : ''}`}
        >
          <span className="font-medium">Dismissed as a false signal</span>
          {column.dismissedByName ? ` by ${column.dismissedByName}` : ''}
          {column.dismissedReason ? `: ${column.dismissedReason}` : ''}
        </p>
      )}
    </div>
  );
}

/**
 * One row, one next action, plus the way to overrule the row entirely.
 *
 * Nothing is offered that cannot be carried out: a column with no product has disabled cells,
 * so "Fix the quantities" would land the cursor nowhere, and picking the product is the step
 * that comes first anyway. A column whose blockers were dismissed is asked nothing at all -
 * only offered the way back.
 */
function RowActions({
  column,
  canEdit,
  poOptions,
  onFixQuantities,
  onResolveProduct,
  onDismissColumn,
}: {
  column: ColumnState;
  canEdit: boolean;
  poOptions: SearchableSelectOption[];
  onFixQuantities: (columnKey: string) => void;
  onResolveProduct: (columnIndex: number, productId: string) => void;
  onDismissColumn?: (columnIndex: number, dismissed: boolean, reason?: string) => void;
}) {
  const dismissal = onDismissColumn ? (
    <DismissControl
      column={column}
      canEdit={canEdit}
      onDismissColumn={onDismissColumn}
    />
  ) : null;

  if (!canEdit || column.dismissed) {
    return dismissal ? <div className="min-w-0">{dismissal}</div> : null;
  }

  const codes = new Set(column.blockers.map((blocker) => blocker.code));
  const picker = (action: string) => (
    <div className="w-full">
      <DeliveryScheduleProductPicker
        idPrefix="schedule-fix"
        columnIndex={column.index}
        customerCode={column.customerCode}
        action={action}
        poOptions={poOptions}
        onPick={(productId) => onResolveProduct(column.index, productId)}
      />
    </div>
  );

  /**
   * The one action that ends the WORST of this column's problems.
   *
   * A column with two blockers used to offer two controls, one per sentence, which read as
   * two jobs. Identity comes first (a column pointing at the wrong product makes every
   * number under it meaningless), then the quantities.
   */
  const primary = codes.has('needs_product')
    ? picker('Pick the product')
    : codes.has('not_on_po') && column.productId
      ? picker('Pick a different product')
      : column.productId && column.blockers.length > 0
        ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onFixQuantities(column.key)}
            >
              Fix the quantities
            </Button>
          )
        : null;

  if (!primary && !dismissal) return null;

  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5">
      {primary}
      {dismissal}
    </div>
  );
}

/**
 * Overruling one column's check, and saying so afterwards.
 *
 * A dismissal is not a correction, so it is not offered as one: it asks for a reason before
 * it will save, the reason stays on screen next to the sentences it overrules, and Undo puts
 * the column straight back under its verdict. On a confirmed schedule (`canEdit` false) the
 * reason is still shown in the Problem column, because it is part of what was decided, but
 * nothing here can be changed.
 *
 * Nothing to dismiss on a column that only carries a warning: a warning does not block, so
 * there is no verdict to overrule.
 */
function DismissControl({
  column,
  canEdit,
  onDismissColumn,
}: {
  column: ColumnState;
  canEdit: boolean;
  onDismissColumn: (columnIndex: number, dismissed: boolean, reason?: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState('');

  if (column.dismissed) {
    if (!canEdit) return null;
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => onDismissColumn(column.index, false)}
      >
        Undo
      </Button>
    );
  }

  if (!canEdit || column.blockers.length === 0) return null;

  if (!open) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setOpen(true)}
      >
        Dismiss as false signal
      </Button>
    );
  }

  const trimmed = reason.trim();
  const save = () => {
    if (!trimmed) return;
    onDismissColumn(column.index, true, trimmed);
    setOpen(false);
    setReason('');
  };

  return (
    <div className="flex w-full flex-col gap-1.5">
      <Input
        autoFocus
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            save();
          }
        }}
        aria-label={`Why the check is wrong about ${
          column.productCode ?? column.customerCode ?? 'this column'
        }`}
        placeholder="Why is this a false signal?"
        className="w-full"
      />
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" disabled={!trimmed} onClick={save}>
          Dismiss
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setOpen(false);
            setReason('');
          }}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
