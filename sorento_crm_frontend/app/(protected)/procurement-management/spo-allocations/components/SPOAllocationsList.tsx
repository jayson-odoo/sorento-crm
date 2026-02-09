'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { Plus, Search, X, ChevronDown, ChevronRight, Link as LinkIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useSPOAllocationsGroupedByShipment } from '../hooks/useSPOAllocations';
import type {
  SPOAllocation,
  ShipmentWithAllocationsGroup,
} from '../types/spoAllocation.types';
import Link from 'next/link';
import React from 'react';

/**
 * Build rows for the expanded section:
 * - One block per product that appears on the packing list (shipment_lines), with qty shipped and its allocations.
 * - A final "Other (not on packing list)" block for allocations whose product is not on the packing list.
 */
function groupByProduct(
  group: ShipmentWithAllocationsGroup,
): Array<{
  productId: string;
  productName: string;
  productCode?: string;
  quantityShipped: number;
  allocations: SPOAllocation[];
  isNotOnPackingList?: boolean;
}> {
  const lines = group.shipment_lines ?? [];
  const productIdsOnPackingList = new Set(lines.map((l) => l.product_id));
  const byProduct = new Map<
    string,
    { productName: string; productCode?: string; quantityShipped: number; allocations: SPOAllocation[] }
  >();
  for (const line of lines) {
    const name = line.product?.product_name ?? line.product?.product_code ?? '-';
    const code = line.product?.product_code;
    const existing = byProduct.get(line.product_id);
    if (existing) {
      existing.quantityShipped += line.quantity_shipped;
    } else {
      byProduct.set(line.product_id, {
        productName: name,
        productCode: code,
        quantityShipped: line.quantity_shipped,
        allocations: [],
      });
    }
  }
  const otherAllocations: SPOAllocation[] = [];
  for (const alloc of group.spo_allocations) {
    const name = alloc.product?.product_name ?? alloc.product?.product_code ?? '-';
    const code = alloc.product?.product_code;
    if (productIdsOnPackingList.has(alloc.product_id)) {
      const existing = byProduct.get(alloc.product_id);
      if (existing) {
        existing.allocations.push(alloc);
      } else {
        byProduct.set(alloc.product_id, {
          productName: name,
          productCode: code,
          quantityShipped: 0,
          allocations: [alloc],
        });
      }
    } else {
      otherAllocations.push(alloc);
    }
  }
  const result = Array.from(byProduct.entries()).map(([productId, data]) => ({
    productId,
    productName: data.productName,
    productCode: data.productCode,
    quantityShipped: data.quantityShipped,
    allocations: data.allocations,
    isNotOnPackingList: false,
  }));
  if (otherAllocations.length > 0) {
    result.push({
      productId: '__other__',
      productName: 'Other (not on packing list)',
      productCode: undefined,
      quantityShipped: 0,
      allocations: otherAllocations,
      isNotOnPackingList: true,
    });
  }
  return result;
}

export default function SPOAllocationsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'shipment_number', desc: false },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [productCodeFilter, setProductCodeFilter] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const { data, isLoading } = useSPOAllocationsGroupedByShipment({
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    query: searchQuery || undefined,
    product_code: productCodeFilter.trim() || undefined,
    sort: sorting[0]?.id ?? 'shipment_number',
    dir: sorting[0]?.desc ? 'desc' : 'asc',
  });

  const groupedData = data?.data ?? [];
  const totalShipments = data?.pagination?.total ?? 0;
  const pageCount = Math.ceil(totalShipments / pagination.pageSize);

  const toggleGroup = (shipmentId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(shipmentId)) {
        next.delete(shipmentId);
      } else {
        next.add(shipmentId);
      }
      return next;
    });
  };

  const handleAllocationClick = (allocation: SPOAllocation) => {
    router.push(`/procurement-management/spo-allocations/${allocation.id}`);
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'pending':
        return 'secondary';
      case 'partial_received':
        return 'primary';
      case 'fully_received':
        return 'primary';
      case 'rejected':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  const columns = useMemo<ColumnDef<ShipmentWithAllocationsGroup>[]>(
    () => [
      {
        id: 'expand',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={(e) => {
              e.stopPropagation();
              toggleGroup(row.original.inbound_shipment.id);
            }}
          >
            {expandedGroups.has(row.original.inbound_shipment.id) ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </Button>
        ),
        size: 50,
      },
      {
        accessorKey: 'inbound_shipment.shipment_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Packing List (Inbound Shipment)" column={column} />
        ),
        cell: ({ row }) => {
          const ship = row.original.inbound_shipment;
          const count = row.original.spo_allocations.length;
          return (
            <div className="flex items-center gap-2">
              <Link
                href={`/procurement-management/packing-lists/${ship.id}`}
                className="text-primary hover:underline font-medium flex items-center gap-1"
                onClick={(e) => e.stopPropagation()}
              >
                <LinkIcon className="size-3" />
                {ship.shipment_number}
              </Link>
              <Badge variant="secondary" size="sm">
                {count} allocation{count !== 1 ? 's' : ''}
              </Badge>
            </div>
          );
        },
        size: 280,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
    ],
    [expandedGroups],
  );

  const table = useReactTable({
    columns,
    data: groupedData,
    pageCount,
    getRowId: (row) => row.inbound_shipment.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={totalShipments}
      isLoading={isLoading}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search by shipment, SPO number, product..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="ps-9 w-56"
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
            <Input
              placeholder="Product code"
              value={productCodeFilter}
              onChange={(e) => setProductCodeFilter(e.target.value)}
              className="w-40"
            />
            {productCodeFilter && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setProductCodeFilter('')}
                className="text-muted-foreground"
              >
                <X className="size-4" />
              </Button>
            )}
          </div>
          <Button
            onClick={() =>
              router.push('/procurement-management/spo-allocations/new')
            }
          >
            <Plus />
            Create SPO Allocation
          </Button>
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <table className="w-full border-collapse table-fixed">
              <thead>
                <tr className="border-b bg-muted/40">
                  {table.getHeaderGroups()[0]?.headers.map((header) => (
                    <th
                      key={header.id}
                      className="relative text-left p-4 font-medium text-sm text-muted-foreground truncate"
                      style={{
                        width: header.getSize(),
                        minWidth: header.getSize(),
                      }}
                    >
                      {header.isPlaceholder
                        ? null
                        : typeof header.column.columnDef.header === 'function'
                          ? header.column.columnDef.header(header.getContext())
                          : header.column.columnDef.header}
                      {header.column.getCanResize() && (
                        <div
                          role="separator"
                          aria-orientation="vertical"
                          onDoubleClick={() => header.column.resetSize()}
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                          className="absolute top-0 right-0 h-full w-4 cursor-col-resize select-none touch-none flex justify-center items-center -mr-2 z-10 after:absolute after:inset-y-0 after:w-px after:bg-border after:-translate-x-1/2"
                        />
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={columns.length} className="p-4">
                      <div className="text-center text-muted-foreground">
                        Loading...
                      </div>
                    </td>
                  </tr>
                ) : groupedData.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="p-4">
                      <div className="text-center text-muted-foreground">
                        No inbound shipments with SPO allocations found.
                      </div>
                    </td>
                  </tr>
                ) : (
                  groupedData.map((group) => (
                    <React.Fragment key={group.inbound_shipment.id}>
                      <tr className="border-b hover:bg-accent/50">
                        {table.getHeaderGroups()[0]?.headers.map((header) => {
                          const cell = table
                            .getRow(group.inbound_shipment.id)
                            ?.getVisibleCells()
                            .find((c) => c.column.id === header.id);
                          return (
                            <td
                              key={header.id}
                              className="p-4 truncate"
                              style={{
                                width: header.getSize(),
                                minWidth: header.getSize(),
                              }}
                            >
                              {cell &&
                                (typeof cell.column.columnDef.cell === 'function'
                                  ? cell.column.columnDef.cell(cell.getContext())
                                  : cell.column.columnDef.cell)}
                            </td>
                          );
                        })}
                      </tr>
                      {expandedGroups.has(group.inbound_shipment.id) && (
                        <tr>
                          <td
                            colSpan={columns.length}
                            className="p-0 bg-muted/30 align-top"
                          >
                            <div className="p-4">
                              <div className="mb-3 font-medium text-sm text-muted-foreground">
                                SPO allocations for {group.inbound_shipment.shipment_number}
                              </div>
                              <table className="w-full border-collapse">
                                <thead>
                                  <tr className="border-b">
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground min-w-[160px]">
                                      Product
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[100px]">
                                      Qty shipped (PL)
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[140px]">
                                      SPO Number
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[120px]">
                                      Warehouse
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[100px]">
                                      Allocated Qty
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[100px]">
                                      Received Qty
                                    </th>
                                    <th className="text-left p-2 text-xs font-medium text-muted-foreground w-[120px]">
                                      Status
                                    </th>
                                    <th className="w-8" />
                                  </tr>
                                </thead>
                                <tbody>
                                  {groupByProduct(group).map(
                                    ({
                                      productId,
                                      productName,
                                      productCode,
                                      quantityShipped,
                                      allocations,
                                      isNotOnPackingList,
                                    }) => (
                                      <React.Fragment key={productId}>
                                        <tr className="border-b bg-muted/40">
                                          <td className="p-2 text-sm font-medium">
                                            {productCode ? `${productCode}${productName !== productCode ? ` — ${productName}` : ''}` : productName}
                                          </td>
                                          <td className="p-2 text-sm text-muted-foreground">
                                            {isNotOnPackingList ? '—' : quantityShipped}
                                          </td>
                                          <td className="p-2" colSpan={6} />
                                        </tr>
                                        {allocations.map((allocation) => (
                                          <tr
                                            key={allocation.id}
                                            className="border-b hover:bg-background cursor-pointer"
                                            onClick={() => handleAllocationClick(allocation)}
                                          >
                                            <td className="p-2 text-sm text-muted-foreground" />
                                            <td className="p-2 text-sm text-muted-foreground" />
                                            <td className="p-2 text-sm">
                                              {allocation.spo_number ?? '-'}
                                            </td>
                                            <td className="p-2 text-sm">
                                              {allocation.warehouse?.warehouse_code ?? '-'}
                                            </td>
                                            <td className="p-2 text-sm">
                                              {allocation.allocated_quantity}
                                            </td>
                                            <td className="p-2 text-sm">
                                              {allocation.quantity_received}
                                            </td>
                                            <td className="p-2">
                                              <Badge
                                                variant={getStatusBadgeVariant(
                                                  allocation.receipt_status,
                                                )}
                                                size="sm"
                                              >
                                                {allocation.receipt_status
                                                  ?.split('_')
                                                  .map((w) =>
                                                    w.charAt(0).toUpperCase() + w.slice(1),
                                                  )
                                                  .join(' ') ?? '-'}
                                              </Badge>
                                            </td>
                                            <td className="p-2">
                                              <ChevronRight className="text-muted-foreground/70 size-3.5" />
                                            </td>
                                          </tr>
                                        ))}
                                      </React.Fragment>
                                    ),
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))
                )}
              </tbody>
            </table>
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
