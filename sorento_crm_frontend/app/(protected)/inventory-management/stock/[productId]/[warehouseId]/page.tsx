'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarActions, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { Card, CardContent, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { getStockDetail, getStockLedgerByStock, exportStockBalance } from '../../services/stockService';
import type { Stock } from '../../types/stock.types';
import type { StockLedgerEntry } from '../../../stock-ledger/types/stockLedger.types';

type StockDetailPageProps = {
  params: Promise<{ productId: string; warehouseId: string }>;
};

export default function StockDetailPage({ params }: StockDetailPageProps) {
  const { productId, warehouseId } = use(params);
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 20 });

  const stockQuery = useQuery({
    queryKey: ['stock-detail', productId, warehouseId],
    queryFn: () => getStockDetail(productId, warehouseId),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const ledgerQuery = useQuery({
    queryKey: ['stock-ledger-detail', productId, warehouseId, pagination.pageIndex, pagination.pageSize],
    queryFn: () => getStockLedgerByStock(productId, warehouseId, pagination),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  // Get navigation data for next/previous using export endpoint (no pagination limit)
  const navigationQuery = useQuery({
    queryKey: ['stock-navigation'],
    queryFn: () => exportStockBalance(),
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const navigationItems = navigationQuery.data ?? [];
  // Sort navigation items by product_code for consistent ordering
  const sortedNavigationItems = useMemo(() => {
    return [...navigationItems].sort((a, b) => {
      const codeA = a.product?.product_code || '';
      const codeB = b.product?.product_code || '';
      return codeA.localeCompare(codeB);
    });
  }, [navigationItems]);
  const stock = stockQuery.data as Stock | null;
  const navigationItemsForRecordNav = useMemo(
    () => sortedNavigationItems.map((s) => ({ id: `${s.product_id}/${s.warehouse_id}` })),
    [sortedNavigationItems],
  );
  const currentRecordId = `${productId}/${warehouseId}`;

  const columns = useMemo<ColumnDef<StockLedgerEntry>[]>(
    () => [
      {
        accessorKey: 'transaction_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.transaction_type}
          </Badge>
        ),
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'quantity_change',
        header: ({ column }) => <DataGridColumnHeader title="Change" column={column} />,
        cell: ({ row }) => {
          const value = row.original.quantity_change;
          const isPositive = value > 0;
          return (
            <span className={isPositive ? 'text-emerald-600 font-medium' : 'text-red-600 font-medium'}>
              {isPositive ? `+${value}` : value}
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'previous_quantity',
        header: ({ column }) => <DataGridColumnHeader title="Previous" column={column} />,
        size: 120,
      },
      {
        accessorKey: 'new_quantity',
        header: ({ column }) => <DataGridColumnHeader title="New" column={column} />,
        size: 120,
      },
      {
        accessorKey: 'created_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Created By" column={column} />,
        cell: ({ row }) => row.original.created_by_name || row.original.created_by || '-',
        size: 180,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 200,
      },
      {
        accessorKey: 'notes',
        header: ({ column }) => <DataGridColumnHeader title="Notes" column={column} />,
        cell: ({ row }) => row.original.notes || '-',
        size: 200,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: ledgerQuery.data?.data || [],
    pageCount: Math.ceil((ledgerQuery.data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  if (stockQuery.isLoading) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Stock</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/inventory-management/stock">Stock</BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/inventory-management/stock">
                  <MoveLeft /> Back to Stock
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!stock) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Stock</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/inventory-management/stock">Stock</BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/inventory-management/stock">
                  <MoveLeft /> Back to Stock
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Stock record not found</p>
            <Button variant="outline" onClick={() => router.push('/inventory-management/stock')} className="mt-4">
              Back to Stock
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Stock Balance</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Inventory Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/inventory-management/stock">Stock</BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <div className="flex items-center gap-2">
              <RecordNavigation
                basePath="/inventory-management/stock"
                currentId={currentRecordId}
                items={navigationItemsForRecordNav}
                totalCount={navigationItemsForRecordNav.length}
                ariaLabel="stock"
              />
              <Button asChild variant="outline">
                <Link href="/inventory-management/stock">
                  <MoveLeft /> Back to Stock
                </Link>
              </Button>
            </div>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold">{stock.product?.product_code || '-'}</h1>
                    {stock.product?.product_name && (
                      <Badge variant="secondary">
                        {stock.product.product_name}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {stock.warehouse?.warehouse_name || 'No warehouse'} • Available: {stock.quantity_available ?? 0}
                  </p>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 text-sm">
                <div>
                  <div className="text-muted-foreground">Product</div>
                  <div className="font-medium">{stock.product?.product_name || '-'}</div>
                  <div className="text-muted-foreground">{stock.product?.product_code || '-'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Warehouse</div>
                  <div className="font-medium">{stock.warehouse?.warehouse_name || '-'}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Quantities</div>
                  <div className="font-medium">
                    On Hand: {stock.quantity_on_hand ?? 0} | Available: {stock.quantity_available ?? 0}
                  </div>
                  <div className="text-muted-foreground">
                    Reserved: {stock.quantity_reserved ?? 0} | Damaged: {stock.quantity_damaged ?? 0}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <DataGrid table={table} recordCount={ledgerQuery.data?.pagination.total || 0} isLoading={ledgerQuery.isLoading}>
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div className="text-lg font-semibold">Stock Ledger</div>
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
        </div>
      </Container>
    </>
  );
}
