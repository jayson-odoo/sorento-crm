'use client';

import * as React from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { AutocountWriteLine, AutocountWriteResult } from '../types/projectAutocountWrite.types';

const VERB_TEXT: Record<string, string> = {
  REMOVE_LINE: 'Remove line',
  CANCEL_BALANCE: 'Cancel balance',
  REPOINT_SO: 'Move to another order',
  MODEL_CHANGE: 'Change item',
  ADD_LINE: 'Add line',
  QTY_CHANGE: 'Change quantity',
  ADVANCE: 'Bring forward',
  DELAY: 'Delay',
};

function verbText(verb: string | null | undefined): string {
  if (!verb) return 'Change';
  return VERB_TEXT[verb] ?? verb.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

/**
 * AutoCount's own answer after a write (mock v2). Every write is followed by a read-back, so the
 * lines listed are the ones AutoCount holds, not the ones we sent. A skipped rate-only line and an
 * exploded product set are named (ruling R6), and what waits for AutoCount is listed with its
 * reason. A refusal is one sentence and no lines.
 */
export function AutocountWriteDialog({
  open,
  onOpenChange,
  title,
  result,
  onRetry,
  retrying = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  result: AutocountWriteResult | null;
  /** Runs the same action again. Shown whenever the answer is not done (owner, 11 Nov). */
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const done = result?.outcome === 'done';
  const canRetry = Boolean(onRetry) && result !== null && !done && result.outcome !== 'waiting';
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {result ? (
            <>
              <p
                className={cn(
                  'text-sm font-medium break-words',
                  done ? 'text-success' : 'text-foreground',
                )}
                role="status"
              >
                {result.message}
              </p>

              {(result.warnings ?? []).map((warning, index) => {
                const text = typeof warning === 'string' ? warning : (warning.message ?? warning.code);
                return text ? (
                  <p
                    key={`${text}-${index}`}
                    className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm break-words"
                  >
                    {text}
                  </p>
                ) : null;
              })}

              {(result.lines ?? []).length > 0 && <ReadBackGrid lines={result.lines} />}

              {(result.skipped ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Not sent</p>
                  {result.skipped.map((line) => (
                    <p key={`${line.code}-${line.description}`} className="text-sm break-words">
                      {`${line.code ?? ''} ${line.description ?? ''}`.trim()}
                    </p>
                  ))}
                </div>
              )}

              {(result.exploded ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Sent as its parts</p>
                  {result.exploded.map((set) => (
                    <p key={set.code ?? 'set'} className="text-sm break-words">
                      {`${set.code ?? 'Set'}: ${set.components
                        .map((part) => `${part.code} x ${part.qty}`)
                        .join(', ')}`}
                    </p>
                  ))}
                </div>
              )}

              {(result.waiting ?? []).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Not changed yet</p>
                  {result.waiting.map((change, index) => (
                    <p key={`${change.verb}-${change.line_no}-${index}`} className="text-sm break-words">
                      {[
                        verbText(change.verb),
                        change.line_no != null ? `line ${change.line_no}` : null,
                        change.item_code,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      <span className="text-muted-foreground">{` - ${change.reason}`}</span>
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {canRetry && (
            <Button type="button" variant="primary" disabled={retrying} onClick={onRetry}>
              {retrying ? 'Trying again…' : 'Try again'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function text(value: string | null | undefined, className = 'block truncate') {
  return (
    <span className={className} title={value ?? ''}>
      {value || '-'}
    </span>
  );
}

/** The lines AutoCount holds after the write (its read-back, not what we sent). */
function ReadBackGrid({ lines }: { lines: AutocountWriteLine[] }) {
  const columns = React.useMemo<ColumnDef<AutocountWriteLine>[]>(
    () => [
      {
        id: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="Line" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_no}</span>,
        size: 60,
        meta: { headerTitle: 'Line' },
      },
      {
        id: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item" column={column} />,
        cell: ({ row }) => text(row.original.item_code, 'block truncate font-medium'),
        size: 150,
        meta: { headerTitle: 'Item' },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => text(row.original.description),
        size: 240,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => text(row.original.qty, 'block truncate text-end tabular-nums'),
        size: 80,
        meta: { headerTitle: 'Qty' },
      },
      {
        id: 'unit_price',
        header: ({ column }) => <DataGridColumnHeader title="Unit price" column={column} />,
        cell: ({ row }) => text(row.original.unit_price, 'block truncate text-end tabular-nums'),
        size: 110,
        meta: { headerTitle: 'Unit price' },
      },
      {
        id: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => text(row.original.location),
        size: 110,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery" column={column} />,
        cell: ({ row }) =>
          text(row.original.delivery_date ? formatDateInMalaysia(row.original.delivery_date) : null),
        size: 110,
        meta: { headerTitle: 'Delivery' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row, index) => `${row.line_no}:${row.item_code}:${index}`,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={lines.length}
      isLoading={false}
      listingKey={null}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <div className="overflow-x-auto rounded-lg border border-border">
        <DataGridTable />
      </div>
    </DataGrid>
  );
}
