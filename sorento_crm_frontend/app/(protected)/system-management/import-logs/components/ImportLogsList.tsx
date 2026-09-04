'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDateTime } from '@/lib/helpers';
import { useImportLogs } from '../hooks/useImportLogs';
import type { ImportLog } from '../types/importLog.types';

export default function ImportLogsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [entityType, setEntityType] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // Helper function to extract product codes from warnings/errors for description
  const getDescription = (log: ImportLog): string => {
    const productCodes: string[] = [];
    
    // Extract from warnings
    if (log.warnings && Array.isArray(log.warnings)) {
      log.warnings.forEach((warning: any) => {
        if (warning.product_code) {
          productCodes.push(String(warning.product_code));
        }
        if (warning._product_code) {
          productCodes.push(String(warning._product_code));
        }
      });
    }
    
    // Extract from errors
    if (log.errors && Array.isArray(log.errors)) {
      log.errors.forEach((error: any) => {
        if (error.product_code) {
          productCodes.push(String(error.product_code));
        }
        if (error.data?.product_code) {
          productCodes.push(String(error.data.product_code));
        }
        if (error.data?._product_code) {
          productCodes.push(String(error.data._product_code));
        }
      });
    }
    
    // Extract from summary (for stock imports)
    if (log.summary && typeof log.summary === 'object') {
      if (log.summary.product_codes && Array.isArray(log.summary.product_codes)) {
        productCodes.push(...log.summary.product_codes.map(String));
      }
      if (log.summary.kpi_warnings && Array.isArray(log.summary.kpi_warnings)) {
        log.summary.kpi_warnings.forEach((item: any) => {
          if (item.product_code) {
            productCodes.push(String(item.product_code));
          }
        });
      }
    }
    
    // Remove duplicates and limit display
    const uniqueCodes = Array.from(new Set(productCodes)).filter(Boolean);
    if (uniqueCodes.length === 0) return '-';
    if (uniqueCodes.length <= 5) {
      return uniqueCodes.join(', ');
    }
    return `${uniqueCodes.slice(0, 5).join(', ')}... (+${uniqueCodes.length - 5} more)`;
  };

  const { data, isLoading, isPlaceholderData, refetch, isFetching } = useImportLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    entity_type: entityType || undefined,
  });

  const columns = useMemo<ColumnDef<ImportLog>[]>(
    () => [
      buildSelectColumn<ImportLog>(),
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Entity" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary">
            {row.original.entity_type}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Entity', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        cell: ({ row }) => row.original.filename || '-',
        size: 220,
        meta: { headerTitle: 'Filename' },
      },
      {
        accessorKey: 'import_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 140,
        meta: { headerTitle: 'Type' },
      },
      {
        accessorKey: 'successful_rows',
        header: ({ column }) => <DataGridColumnHeader title="Success" column={column} />,
        cell: ({ row }) => row.original.successful_rows,
        size: 100,
        meta: { headerTitle: 'Success' },
      },
      {
        accessorKey: 'skipped_rows',
        header: ({ column }) => <DataGridColumnHeader title="Skipped" column={column} />,
        cell: ({ row }) => row.original.skipped_rows,
        size: 100,
        meta: { headerTitle: 'Skipped' },
      },
      {
        accessorKey: 'failed_rows',
        header: ({ column }) => <DataGridColumnHeader title="Failed" column={column} />,
        cell: ({ row }) => row.original.failed_rows,
        size: 100,
        meta: { headerTitle: 'Failed' },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const desc = getDescription(row.original);
          return (
            <span className="text-sm text-muted-foreground" title={desc}>
              {desc}
            </span>
          );
        },
        size: 300,
        meta: { headerTitle: 'Description' },
      },
      {
        accessorKey: 'imported_by',
        header: ({ column }) => <DataGridColumnHeader title="Imported By" column={column} />,
        cell: ({ row }) => row.original.imported_by || '-',
        size: 180,
        meta: { headerTitle: 'Imported By' },
      },
      {
        accessorKey: 'imported_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.imported_at)),
        size: 200,
        meta: { headerTitle: 'Created At' },
      },
      {
        accessorKey: 'duration_ms',
        header: ({ column }) => <DataGridColumnHeader title="Duration" column={column} />,
        cell: ({ row }) => (row.original.duration_ms ? `${row.original.duration_ms} ms` : '-'),
        size: 120,
        meta: { headerTitle: 'Duration' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  const handleRowClick = (logId: string) => {
    router.push(`/system-management/import-logs/${logId}`);
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      onRowClick={(row) => handleRowClick(row.id)}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            filters={{
              kind: 'custom',
              active: Boolean(entityType),
              activeCount: entityType ? 1 : 0,
              content: (
                <div className="space-y-3">
                  <Input
                    placeholder="Filter by entity type..."
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                  />
                  {entityType && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => setEntityType('')}
                    >
                      Clear filters
                    </Button>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'import_logs_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
