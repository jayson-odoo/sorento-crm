'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDateTime } from '@/lib/helpers';
import { useImportLogs } from '../hooks/useImportLogs';
import type { ImportLog } from '../types/importLog.types';
import { Columns3 } from 'lucide-react';

export default function ImportLogsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [entityType, setEntityType] = useState('');

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

  const { data, isLoading, refetch, isFetching } = useImportLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    entity_type: entityType || undefined,
  });

  const columns = useMemo<ColumnDef<ImportLog>[]>(
    () => [
      {
        accessorKey: 'entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Entity" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.entity_type}
          </Badge>
        ),
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        cell: ({ row }) => row.original.filename || '-',
        size: 220,
      },
      {
        accessorKey: 'import_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 140,
      },
      {
        accessorKey: 'successful_rows',
        header: ({ column }) => <DataGridColumnHeader title="Success" column={column} />,
        cell: ({ row }) => row.original.successful_rows,
        size: 100,
      },
      {
        accessorKey: 'skipped_rows',
        header: ({ column }) => <DataGridColumnHeader title="Skipped" column={column} />,
        cell: ({ row }) => row.original.skipped_rows,
        size: 100,
      },
      {
        accessorKey: 'failed_rows',
        header: ({ column }) => <DataGridColumnHeader title="Failed" column={column} />,
        cell: ({ row }) => row.original.failed_rows,
        size: 100,
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
      },
      {
        accessorKey: 'imported_by',
        header: ({ column }) => <DataGridColumnHeader title="Imported By" column={column} />,
        cell: ({ row }) => row.original.imported_by || '-',
        size: 180,
      },
      {
        accessorKey: 'imported_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.imported_at)),
        size: 200,
      },
      {
        accessorKey: 'duration_ms',
        header: ({ column }) => <DataGridColumnHeader title="Duration" column={column} />,
        cell: ({ row }) => (row.original.duration_ms ? `${row.original.duration_ms} ms` : '-'),
        size: 120,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
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
      onRowClick={(row) => handleRowClick(row.id)}
      tableLayout={{ columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative">
            <Input
              placeholder="Filter by entity type..."
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              className="w-64"
            />
          </div>
                    <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
