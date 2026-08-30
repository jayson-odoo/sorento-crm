'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import type { ProductAttachment } from '../types/productAttachment.types';
import { useProductAttachments } from '../hooks/useProductAttachments';

export default function ProductAttachmentsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = useProductAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<ProductAttachment>[]>(
    () => [
      buildSelectColumn<ProductAttachment>(),
      {
        accessorKey: 'product.product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.product?.product_code || '-',
        meta: { headerTitle: 'Product Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'product.product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.product?.product_name || '-',
        meta: { headerTitle: 'Product Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'attachment.original_filename',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Filename" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.attachment?.original_filename || '-',
        meta: { headerTitle: 'Attachment Filename', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'attachment.attachment_type.type_name',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Type" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.attachment?.attachment_type?.type_name || '-',
        meta: { headerTitle: 'Attachment Type', skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const handleRowClick = (row: ProductAttachment) => {
    if (row.product_id) {
      router.push(`/master-data-management/products/${row.product_id}`);
    }
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      standardToolbar={false}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search product attachments..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search"
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            exportConfig={{ filename: 'product_attachments_export.xlsx' }}
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
