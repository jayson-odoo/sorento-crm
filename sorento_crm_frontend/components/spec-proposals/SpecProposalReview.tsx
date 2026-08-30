'use client';

import { useCallback, useMemo } from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from '@tanstack/react-table';

import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { readable, readableValue } from '@/lib/spec-readable';
import { DEFAULT_SELECTABLE_KINDS } from './types';
import type {
  SpecProposal,
  SpecProposalKind,
  SpecProposalReviewProps,
} from './types';

/**
 * What a piece of text says about a product, beside what the product already holds.
 *
 * **Shared and product-blind** (AC-B.8): it takes proposals, a selection and a
 * callback, and it owns no product identity and imports no service. Extraction from a
 * pasted flyer card renders it today; milestone 2's supplier acceptance renders the
 * same component over a supplier's staged submission, which is why the selection is
 * the caller's state rather than this component's - a multi-product review lifts one
 * selection across several of these.
 *
 * **`kind` is data, not a decision made here** (AC-B.3). The server decides whether a
 * proposal is new, a change or a conflict, because the supplier surface has to reach
 * byte-identical answers and a second copy of the rule in the browser would drift the
 * first time either moved.
 *
 * The shared `DataGrid` with the standard `buildSelectColumn`, like every other
 * table in the system (D10).
 */

/**
 * The three kinds on the shared pill vocabulary, locally.
 *
 * A local map rather than new entries in `lib/status-pill.ts`, exactly as
 * `SpecSourceBadge` does it: "conflict" here is a word from one domain and the shared
 * cross-domain vocabulary is not the place for it. The escalation is the point - a new
 * value states something the product never said, a change overwrites a machine
 * reading, and a conflict overwrites a value a person vouched for, which is why
 * conflicts arrive unticked.
 */
const KIND_PILL_KEY: Record<SpecProposalKind, string> = {
  new: 'submitted',
  change: 'pending',
  conflict: 'rejected',
  // The two that ask nothing of the reader take the two quietest colours in the
  // palette, so a batch of forty rows reads as "these six need a decision" at a
  // glance rather than as forty things to work through.
  unchanged: 'derived',
  suppressed: 'voided',
};

/** Exactly the copy the contract names. The value is the sentence, not a legend. */
export function proposalBadgeText(proposal: SpecProposal): string {
  const stored = readableValue(
    proposal.stored_value,
    proposal.stored_unit ?? undefined,
  );
  switch (proposal.kind) {
    case 'change':
      return `Changes ${stored} to ${readableValue(proposal.value, proposal.unit ?? undefined)}`;
    case 'conflict':
      // A tombstone conflicts with a REMOVAL, not with a value: the person said this
      // product does not carry this spec, so there is no stored value to name. Through
      // the sentence below it reads "Conflicts with your value " - a badge that stops
      // mid-phrase, which the reader has to interpret as either a bug or a blank value.
      return stored
        ? `Conflicts with your value ${stored}`
        : 'Conflicts with your removal of this spec';
    case 'unchanged':
      // Not "Unchanged", which reads as something that failed to change. The
      // product already says this, which is why the row cannot be ticked.
      return 'Already stored';
    case 'suppressed':
      return 'Removed from this product';
    default:
      return 'New';
  }
}

/** The two kinds no surface may tick. There is no value to write for either. */
const NEVER_SELECTABLE: readonly SpecProposalKind[] = [
  'unchanged',
  'suppressed',
];

export function SpecProposalReview({
  proposals,
  selectedKeys,
  onSelectionChange,
  disabled = false,
  selectableKinds = DEFAULT_SELECTABLE_KINDS,
  renderValue,
  rowActions,
}: SpecProposalReviewProps) {
  const canSelect = useCallback(
    (kind: SpecProposalKind) =>
      !disabled &&
      !NEVER_SELECTABLE.includes(kind) &&
      selectableKinds.includes(kind),
    [disabled, selectableKinds],
  );

  /** The caller's array as react-table wants it. Keys, so a refetch keeps the ticks. */
  const rowSelection = useMemo<RowSelectionState>(
    () => Object.fromEntries(selectedKeys.map((key) => [key, true])),
    [selectedKeys],
  );

  const handleSelectionChange = useCallback(
    (
      updater:
        | RowSelectionState
        | ((old: RowSelectionState) => RowSelectionState),
    ) => {
      const next =
        typeof updater === 'function' ? updater(rowSelection) : updater;
      // Reported in the order the rows are read, not in click order: the caller turns
      // this straight into the batch it writes, and a batch that reorders itself
      // between two identical reviews is a diff nobody can check.
      onSelectionChange(
        proposals.map((row) => row.spec_key).filter((key) => next[key]),
      );
    },
    [proposals, rowSelection, onSelectionChange],
  );

  const columns = useMemo<ColumnDef<SpecProposal>[]>(
    () => [
      buildSelectColumn<SpecProposal>({
        enableRow: (row) => canSelect(row.original.kind),
      }),
      {
        accessorKey: 'label',
        header: ({ column }) => (
          <DataGridColumnHeader title="Specification" column={column} />
        ),
        size: 180,
        minSize: 120,
        enableSorting: false,
        meta: { headerTitle: 'Specification' },
        cell: ({ row }) => {
          const label = row.original.label || readable(row.original.spec_key);
          return (
            <span className="truncate text-sm font-medium" title={label}>
              {label}
            </span>
          );
        },
      },
      {
        id: 'value',
        header: ({ column }) => (
          <DataGridColumnHeader title="Value" column={column} />
        ),
        size: 170,
        minSize: 110,
        enableSorting: false,
        meta: { headerTitle: 'Value' },
        cell: ({ row }) => {
          const value = readableValue(
            row.original.value,
            row.original.unit ?? undefined,
          );
          const read = (
            <span className="flex min-w-0 items-center gap-1.5">
              <span
                className="truncate text-sm"
                title={value}
                data-spec-proposal-value={row.original.spec_key}
              >
                {value}
              </span>
              {/* A corrected value is not the value the text stated, and the
                  reader has to be able to tell which rows they changed before
                  they apply forty of them. */}
              {row.original.edited && (
                <span
                  className="shrink-0 text-[11px] text-muted-foreground"
                  data-spec-proposal-edited={row.original.spec_key}
                >
                  edited
                </span>
              )}
            </span>
          );
          return renderValue ? renderValue(row.original, read) : read;
        },
      },
      {
        id: 'kind',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Against what is stored"
            column={column}
          />
        ),
        size: 260,
        minSize: 150,
        enableSorting: false,
        meta: { headerTitle: 'Against what is stored' },
        cell: ({ row }) => {
          const text = proposalBadgeText(row.original);
          return (
            <span
              // `cn` and not a template string: the shared pill base carries
              // `capitalize`, which would render "Changes Chrome To Matt Black", and
              // only tailwind-merge drops it for the `normal-case` here.
              className={cn(
                STATUS_PILL_BASE,
                'max-w-full truncate normal-case',
                statusPillClass(KIND_PILL_KEY[row.original.kind]),
              )}
              title={text}
              data-spec-proposal-kind={row.original.kind}
            >
              {text}
            </span>
          );
        },
      },
      {
        id: 'evidence',
        header: ({ column }) => (
          <DataGridColumnHeader title="Read from" column={column} />
        ),
        size: 300,
        minSize: 160,
        enableSorting: false,
        meta: { headerTitle: 'Read from' },
        cell: ({ row }) => (
          // Truncated with the whole sentence on hover: the words a value was read
          // from are the only way to judge it, and a wrapped paragraph per row makes
          // a list of eight taller than the screen it has to be read on.
          <span
            className="truncate font-mono text-xs text-muted-foreground"
            title={row.original.evidence}
          >
            {row.original.evidence}
          </span>
        ),
      },
      ...(rowActions
        ? [
            {
              id: 'actions',
              header: '',
              size: 96,
              minSize: 72,
              enableSorting: false,
              enableResizing: false,
              meta: { headerTitle: 'Actions' },
              cell: ({ row }) => (
                <div className="flex items-center justify-end gap-1">
                  {rowActions(row.original)}
                </div>
              ),
            } as ColumnDef<SpecProposal>,
          ]
        : []),
    ],
    [canSelect, renderValue, rowActions],
  );

  const table = useReactTable({
    columns,
    data: proposals,
    getRowId: (row) => row.spec_key,
    state: { rowSelection },
    onRowSelectionChange: handleSelectionChange,
    // A function, not the boolean it was: react-table reads per-row selectability
    // off the TABLE option (the one on the column definition is decoration), and
    // this is also what keeps the header tick from selecting a row nothing can be
    // written for.
    enableRowSelection: (row) => canSelect(row.original.kind),
    getCoreRowModel: getCoreRowModel(),
    // One text proposes a handful of keys at most. Paging that would be a control the
    // reader has to operate to see a list that already fits.
    manualPagination: true,
    pageCount: 1,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={proposals.length}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      // Column personalisation OFF: these rows exist for as long as one review does,
      // so a saved width per user would be a config row nothing ever reads again.
      listingKey=""
      emptyMessage={
        <div
          className="py-8 text-center text-sm text-muted-foreground"
          data-spec-proposals-empty
        >
          Nothing to review.
        </div>
      }
    >
      <Card>
        <CardTable>
          {/* Horizontal scroll INSIDE the table's own container: at 375px five
              columns cannot fit, and without this the page itself scrolls sideways
              and takes the rest of the record with it. */}
          <DataGridTable />
        </CardTable>
      </Card>
    </DataGrid>
  );
}
