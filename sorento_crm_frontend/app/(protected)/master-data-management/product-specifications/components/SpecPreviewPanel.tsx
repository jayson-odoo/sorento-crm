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
import { useSpecPreview } from '../hooks/useSpecPreview';
import type {
  SpecDerivationRule,
  SpecPreviewSampleRow,
} from '../types/productSpec.types';

const readable = (v: string | number | boolean | null) => {
  if (v === null || v === undefined) return '-';
  return typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v);
};

/**
 * "Preview on catalogue" (AC-B.4): before saving, how many products would change and a
 * sample of before/after, so a rule reorder can be checked against the whole catalogue
 * rather than one product. Advice, not a gate - Save stays enabled the whole time.
 */
export default function SpecPreviewPanel({
  specKey,
  rules,
}: {
  specKey: string;
  rules: SpecDerivationRule[];
}) {
  const { status, result, error, run } = useSpecPreview(specKey);

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
        size: 160,
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
        size: 140,
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
        size: 140,
      },
    ],
    [],
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
          Preview on catalogue
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={status === 'pending'}
          onClick={() => run(rules)}
        >
          {status === 'pending' ? (
            <>
              <Loader2 className="size-3.5 animate-spin" /> Running...
            </>
          ) : (
            'Preview on catalogue'
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
            <span>
              <span className="font-medium">{result.changed ?? 0}</span>{' '}
              <span className="text-muted-foreground">changed</span>
            </span>
            <span>
              <span className="font-medium">{result.added ?? 0}</span>{' '}
              <span className="text-muted-foreground">added</span>
            </span>
            <span>
              <span className="font-medium">{result.removed ?? 0}</span>{' '}
              <span className="text-muted-foreground">removed</span>
            </span>
            <span>
              <span className="font-medium">{result.unchanged ?? 0}</span>{' '}
              <span className="text-muted-foreground">unchanged</span>
            </span>
          </div>

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

      {status === 'idle' && (
        <p className="text-xs text-muted-foreground">
          Check how many products this ordering would change before saving it.
        </p>
      )}
    </div>
  );
}
