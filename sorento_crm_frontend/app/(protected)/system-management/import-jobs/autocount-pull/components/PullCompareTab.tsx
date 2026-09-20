'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Download } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { FileDropzone } from '@/components/common/FileDropzone';
import { toast } from '@/lib/toast';
import { generateExcelFile, parseExcelFile, type ColumnOption } from '@/lib/excel-utils';
import { useComparePull } from '../hooks/useAutocountPull';
import { isCompareFullMatch } from '../types/compareMatch';
import type {
  AutocountCompareDifference,
  AutocountComparePullResult,
  AutocountPullEntity,
} from '../types/autocountPull.types';

export interface PullCompareTabProps {
  jobId: string;
  entity: AutocountPullEntity;
}

/** D4 (small-fix track): same reasoning as `PullExcelViewTab`'s own constant - a stable
 *  key per entity, never the pathname (which embeds the job id) the shared `DataGrid`
 *  falls back to without one. */
const COMPARE_LISTING_KEY: Record<AutocountPullEntity, string> = {
  products: 'master_data.products.autocount_pull::compare',
  stock_balances: 'inventory.stock.autocount_pull::compare',
};

function summaryHeadline(result: AutocountComparePullResult): { title: string; body: string; ok: boolean } {
  const { summary } = result;
  const ok = isCompareFullMatch(summary);
  if (ok) {
    return {
      title: '100% match.',
      body: `${summary.matched} of ${summary.total} items agree with ${summary.filename}.`,
      ok: true,
    };
  }
  const parts = [`${summary.different} differ`];
  if (summary.only_in_excel) parts.push(`${summary.only_in_excel} only in your Excel`);
  if (summary.only_in_pull) parts.push(`${summary.only_in_pull} only in AutoCount`);
  return {
    title: `${summary.matched} of ${summary.total} match.`,
    body: `${parts.join(', ')}.`,
    ok: false,
  };
}

/**
 * Drops the same file the checker would have uploaded by hand and lines it up against the
 * pull server-side. Advisory only (P11) - the result is shown, never used to gate Confirm.
 */
export function PullCompareTab({ jobId, entity }: PullCompareTabProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<AutocountComparePullResult | null>(null);
  const compareMutation = useComparePull(jobId);
  const accept = entity === 'stock_balances' ? '.xlsx,.xls,.xlsm' : '.xlsx,.xls';

  const handleFilesChange = async (next: File[]) => {
    setFiles(next);
    const file = next[0];
    if (!file) return;
    try {
      const rows = await parseExcelFile(file);
      if (rows.length === 0) {
        toast.error('That file has no rows.');
        return;
      }
      compareMutation.mutate(
        { filename: file.name, rows: rows as Record<string, unknown>[] },
        { onSuccess: (data) => setResult(data) },
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not read that file.');
    }
  };

  const columns = useMemo<ColumnDef<AutocountCompareDifference>[]>(() => {
    const base: ColumnDef<AutocountCompareDifference>[] = [
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item Code" column={column} />,
        cell: ({ row }) => <span className="truncate">{row.original.item_code}</span>,
        size: 140,
      },
    ];
    if (entity === 'stock_balances') {
      base.push({
        accessorKey: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => <span className="truncate">{row.original.location ?? '-'}</span>,
        size: 120,
      });
    }
    base.push(
      {
        accessorKey: 'field',
        header: ({ column }) => <DataGridColumnHeader title="Difference" column={column} />,
        cell: ({ row }) => <span className="truncate">{row.original.field}</span>,
        size: 180,
      },
      {
        accessorKey: 'excel',
        header: ({ column }) => <DataGridColumnHeader title="Your Excel" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.excel}>
            {row.original.excel}
          </span>
        ),
        size: 220,
      },
      {
        accessorKey: 'pull',
        header: ({ column }) => <DataGridColumnHeader title="AutoCount pull" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.pull}>
            {row.original.pull}
          </span>
        ),
        size: 220,
      },
    );
    return base;
  }, [entity]);

  const table = useReactTable({
    columns,
    data: result?.differences ?? [],
    getRowId: (row, index) => `${row.item_code}-${row.location ?? ''}-${row.field}-${index}`,
    getCoreRowModel: getCoreRowModel(),
  });

  const handleDownloadDifferences = async () => {
    if (!result || result.differences.length === 0) return;
    const cols: ColumnOption[] = [
      { key: 'item_code', label: 'Item Code', selected: true },
      ...(entity === 'stock_balances'
        ? [{ key: 'location', label: 'Location', selected: true } satisfies ColumnOption]
        : []),
      { key: 'field', label: 'Difference', selected: true },
      { key: 'excel', label: 'Your Excel', selected: true },
      { key: 'pull', label: 'AutoCount pull', selected: true },
    ];
    // No UUID in the filename the user sees (cursor rule) - the entity, not the job id.
    await generateExcelFile(result.differences, cols, `autocount-${entity}-differences.xlsx`);
  };

  const headline = result ? summaryHeadline(result) : null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FileDropzone
          id={`autocount-compare-${jobId}`}
          accept={accept}
          files={files}
          onFilesChange={handleFilesChange}
          onReject={() => toast.error(`Invalid file type. Please use: ${accept}`)}
          title="Drop the Excel file here, or click to browse"
          hint={`Accepted formats: ${accept}`}
          disabled={compareMutation.isPending}
          aria-label="Excel file to compare"
        />
        <div className="space-y-2">
          {compareMutation.isPending && (
            <p className="text-sm text-muted-foreground">Comparing…</p>
          )}
          {headline && (
            <Alert
              className={
                headline.ok
                  ? 'border-green-200 bg-green-50 text-green-900'
                  : 'border-amber-200 bg-amber-50 text-amber-900'
              }
            >
              <AlertTitle>{headline.title}</AlertTitle>
              <AlertDescription>{headline.body}</AlertDescription>
            </Alert>
          )}
        </div>
      </div>

      {result && result.differences.length > 0 && (
        <DataGrid
          table={table}
          recordCount={result.differences.length}
          isLoading={false}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
          listingKey={COMPARE_LISTING_KEY[entity]}
        >
          <Card>
            <div className="flex items-center justify-end p-3">
              <Button variant="outline" size="sm" onClick={handleDownloadDifferences}>
                <Download className="size-4" />
                Download differences
              </Button>
            </div>
            <CardTable>
              <DataGridTable />
            </CardTable>
          </Card>
        </DataGrid>
      )}
    </div>
  );
}

export default PullCompareTab;
