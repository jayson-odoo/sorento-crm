'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import type { PromotionAttachment } from '../types/promotionAttachment.types';
import { usePromotionAttachments } from '../hooks/usePromotionAttachments';

export default function PromotionAttachmentsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = usePromotionAttachments({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<PromotionAttachment>[]>(
    () => [
      {
        accessorKey: 'promotion.promo_code',
        header: ({ column }) => <DataGridColumnHeader title="Promotion Code" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.promotion?.promo_code || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'promotion.name',
        header: ({ column }) => <DataGridColumnHeader title="Promotion Name" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.promotion?.name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'attachment.original_filename',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Filename" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.attachment?.original_filename || '-',
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'attachment.attachment_type.type_name',
        header: ({ column }) => <DataGridColumnHeader title="Attachment Type" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.attachment?.attachment_type?.type_name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'is_primary',
        header: ({ column }) => <DataGridColumnHeader title="Is Primary" column={column} />,
        size: 100,
        cell: ({ row }) => (
          row.original.is_primary ? (
            <Badge variant="default">Primary</Badge>
          ) : (
            <Badge variant="outline">Secondary</Badge>
          )
        ),
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'sort_order',
        header: ({ column }) => <DataGridColumnHeader title="Sort Order" column={column} />,
        size: 100,
        cell: ({ row }) => row.original.sort_order ?? '-',
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  return (
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search promotion attachments..."
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
              >
                <X />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable
              onRowClick={(row) => {
                if (row.original.promotion_id) {
                  router.push(`/marketing-management/promotions/${row.original.promotion_id}`);
                }
              }}
            />
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
