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
import { Plus, Search, X, ChevronRight, FileDown, Cog, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useStockInquiries } from '../hooks/useStockInquiries';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { StockInquiry } from '../types/stockInquiry.types';
import { exportStockInquiriesToExcel } from '../utils/exportStockInquiryToExcel';
import StockInquiryBulkDeleteDialog from './StockInquiryBulkDeleteDialog';

export default function StockInquiriesList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [exporting, setExporting] = useState(false);
  const [selectedInquiryIds, setSelectedInquiryIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const { data, isLoading } = useStockInquiries({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const handleRowClick = (row: StockInquiry) => {
    const inquiryId = row.id;
    router.push(`/procurement-management/stock-inquiries/${inquiryId}`);
  };

  const handleExportExcel = async () => {
    const items = data?.data ?? [];
    if (items.length === 0) return;
    setExporting(true);
    try {
      await exportStockInquiriesToExcel(items, 'Stock_Inquiries.xlsx');
    } finally {
      setExporting(false);
    }
  };

  const toggleInquirySelection = (inquiryId: string) => {
    setSelectedInquiryIds((prev) => {
      const next = new Set(prev);
      if (next.has(inquiryId)) next.delete(inquiryId);
      else next.add(inquiryId);
      return next;
    });
  };

  const selectAllInquiries = () => {
    const pageInquiries = data?.data ?? [];
    if (selectedInquiryIds.size === pageInquiries.length) {
      setSelectedInquiryIds(new Set());
    } else {
      setSelectedInquiryIds(new Set(pageInquiries.map((i) => i.id)));
    }
  };

  const pageInquiries = data?.data ?? [];
  const isAllSelected = pageInquiries.length > 0 && selectedInquiryIds.size === pageInquiries.length;

  const columns = useMemo<ColumnDef<StockInquiry>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllInquiries}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedInquiryIds.has(row.original.id)}
            onCheckedChange={() => toggleInquirySelection(row.original.id)}
            aria-label={`Select ${row.original.product_code ?? row.original.id}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'product_code',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product Code" column={column} />
        ),
        size: 150,
        cell: ({ row }) => row.original.product_code || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'item_description',
        header: ({ column }) => (
          <DataGridColumnHeader title="Item Description" column={column} />
        ),
        size: 200,
        cell: ({ row }) => row.original.item_description || '-',
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'project_customer',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project Customer" column={column} />
        ),
        size: 150,
        cell: ({ row }) => row.original.project_customer || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'project_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project Name" column={column} />
        ),
        size: 150,
        cell: ({ row }) => row.original.project_name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'quantity',
        header: ({ column }) => (
          <DataGridColumnHeader title="Quantity" column={column} />
        ),
        size: 100,
        cell: ({ row }) => row.original.quantity || '-',
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Delivery Date" column={column} />
        ),
        cell: ({ row }) => row.original.delivery_date ?? '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'remark',
        header: ({ column }) => (
          <DataGridColumnHeader title="Remark" column={column} />
        ),
        cell: ({ row }) => {
          const remark = row.original.remark;
          return remark ? (
            <span className="line-clamp-2" title={remark}>{remark}</span>
          ) : (
            '-'
          );
        },
        size: 180,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created" column={column} />
        ),
        size: 150,
        cell: ({ row }) => {
          const raw = row.original.created_at;
          if (raw == null) return '-';
          const formatted = formatDateTimeInMalaysia(raw);
          return formatted || '-';
        },
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'salesperson',
        header: ({ column }) => (
          <DataGridColumnHeader title="Salesperson" column={column} />
        ),
        size: 150,
        cell: ({ row }) => row.original.salesperson || '-',
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        size: 110,
        cell: ({ row }) => {
          const status = row.original.status;
          if (!status) return '-';
          return (
            <Badge variant={getStatusBadgeVariant(status)} appearance="ghost">
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          );
        },
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => (
          <ChevronRight className="text-muted-foreground/70 size-3.5" />
        ),
        size: 40,
      },
    ],
    [selectedInquiryIds, isAllSelected],
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
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search stock inquiries..."
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
          <div className="flex gap-2">
            {selectedInquiryIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedInquiryIds.size})
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" aria-label="Options">
                  <Cog className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={handleExportExcel}
                  disabled={exporting || !data?.data?.length}
                >
                  <FileDown className="size-4" />
                  {exporting ? 'Exporting…' : 'Export to Excel'}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              onClick={() =>
                router.push('/procurement-management/stock-inquiries/new')
              }
            >
              <Plus />
              Create Stock Inquiry
            </Button>
          </div>
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
      <StockInquiryBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedInquiryIds(new Set());
        }}
        inquiryIds={Array.from(selectedInquiryIds)}
        onSuccess={() => setSelectedInquiryIds(new Set())}
      />
    </DataGrid>
  );
}
