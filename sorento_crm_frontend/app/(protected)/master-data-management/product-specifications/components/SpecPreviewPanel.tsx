'use client';

import { useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { readableValue } from '@/lib/spec-readable';
import { useSpecPreview } from '../hooks/useSpecPreview';
import type {
  SpecDerivationRule,
  SpecPreviewSampleRow,
} from '../types/productSpec.types';


// The counts compare what the rules live today read with what the draft reads, in
// the owner's words (fix round 4, 27 Sep).
const COUNTS = [
  ['changed', 'changed'],
  ['now_set', 'now set'],
  ['no_longer_set', 'no longer set'],
  ['unchanged', 'unchanged'],
] as const;

/** Stored values that already differ from today's rules are not this draft's doing,
 *  so they are not in the counts; a save re-reads them too, which is why it can
 *  report more updates than the preview. */
function driftLine(count: number): string {
  return count === 1
    ? "1 product has a stored value that differs from today's rules; saving this rule refreshes it too."
    : `${count} products have a stored value that differs from today's rules; saving this rule refreshes them too.`;
}

/**
 * "Preview on catalogue" (AC-B.4): before saving, how many products would change and a
 * sample of before/after, so a rule reorder can be checked against the whole catalogue
 * rather than one product. Advice, not a gate - Save stays enabled the whole time.
 */
export default function SpecPreviewPanel({
  specKey,
  rules,
  unit,
  valueLabels,
}: {
  specKey: string;
  rules: SpecDerivationRule[];
  /** The spec's unit and value labels, so a before/after reads the way the
   *  rest of the screen does - "Rose gold", "Yes", "750 mm" - never a slug (B-7). */
  unit?: string | null;
  valueLabels?: Record<string, string>;
}) {
  const { status, result, error, run } = useSpecPreview(specKey);

  const readable = useMemo(
    () => (v: string | number | boolean | null) =>
      v === null || v === undefined ? '-' : readableValue(v, unit ?? undefined, valueLabels) || '-',
    [unit, valueLabels],
  );

  const columns = useMemo<ColumnDef<SpecPreviewSampleRow>[]>(
    () => [
      {
        accessorKey: 'code',
        header: 'Code',
        cell: ({ row }) => (
          <span className="truncate font-mono" title={row.original.code}>
            {row.original.code}
          </span>
        ),
        size: 130,
      },
      {
        accessorKey: 'name',
        header: 'Name',
        cell: ({ row }) => {
          const text = row.original.name || '-';
          return (
            <span className="truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 220,
      },
      {
        accessorKey: 'before',
        header: 'Before',
        cell: ({ row }) => {
          const text = readable(row.original.before);
          return (
            <span className="truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'after',
        header: 'After',
        cell: ({ row }) => {
          const text = readable(row.original.after);
          return (
            <span className="truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 120,
      },
    ],
    [readable],
  );

  const table = useReactTable({
    data: result?.sample ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-muted/10 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          See what would change
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={status === 'pending'}
          onClick={() => run(rules)}
        >
          {status === 'pending' ? (
            <>
              <Loader2 className="size-3.5 animate-spin" /> Checking...
            </>
          ) : (
            'See what would change'
          )}
        </Button>
      </div>

      {status === 'error' && error && (
        <Alert variant="destructive" size="sm">
          <AlertIcon />
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      {status === 'done' && result && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-4 text-sm">
            {COUNTS.map(([field, words]) => (
              <span key={field}>
                <span className="font-medium">{result[field] ?? 0}</span>{' '}
                <span className="text-muted-foreground">{words}</span>
              </span>
            ))}
          </div>
          {(result.drift ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground">{driftLine(result.drift ?? 0)}</p>
          )}

          {(result.sample?.length ?? 0) > 0 && (
            <DataGrid
              table={table}
              recordCount={result.sample?.length ?? 0}
              tableLayout={{ width: 'fixed', columnsResizable: true }}
            >
              <DataGridTable />
            </DataGrid>
          )}
        </div>
      )}
    </div>
  );
}
