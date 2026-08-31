'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, Link as LinkIcon, Plus, Trash2, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { GroupBySelect } from '@/components/ui/group-by-select';
import { useSPOAllocations, useSPOAllocationsGroupedBySPONumber } from '../hooks/useSPOAllocations';
import SPOBulkDeleteDialog from './SPOBulkDeleteDialog';
import { SPOImportDialog } from './SPOImportDialog';
import { importSPOAllocations, validateSPOAllocations } from '../services/spoAllocationService';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useQueryClient } from '@tanstack/react-query';
import type {
  SPOAllocation,
  SPOAllocationWithShipped,
  SPOWithAllocationsGroup,
} from '../types/spoAllocation.types';
import Link from 'next/link';
import React from 'react';
import { allocationLocation } from '../lib/allocationLocation';

type ViewMode = 'none' | 'spo_number';

const GROUP_BY_OPTIONS = [{ value: 'spo_number' as const, label: 'Group by SPO number' }];

export default function SPOAllocationsList() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>('spo_number');
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'spo_number', desc: false },
  ]);
  // A link from the reorder plan's SPO column lands here narrowed to its product.
  const searchParams = useSearchParams();
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch(searchParams.get('query') ?? '');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [selectedAllocationIds, setSelectedAllocationIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const queryClient = useQueryClient();
  const { notifyImportQueued } = useImportJobDrawer();

  const groupedQuery = useSPOAllocationsGroupedBySPONumber({
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    query: searchQuery.trim() || undefined,
    sort: sorting[0]?.id ?? 'spo_number',
    dir: sorting[0]?.desc ? 'desc' : 'asc',
  });

  const flatQuery = useSPOAllocations({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: searchQuery.trim() || undefined,
  });

  const isGrouped = viewMode === 'spo_number';
  const { data: groupedDataRaw, isLoading: isLoadingGrouped, isFetching: isFetchingGrouped } = groupedQuery;
  const { data: flatDataRaw, isLoading: isLoadingFlat, isFetching: isFetchingFlat } = flatQuery;

  // A search brings the reader back to page 0 to see the matches.
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery]);

  const groupedData = groupedDataRaw?.data ?? [];
  const flatData = flatDataRaw?.data ?? [];
  const totalSPOs = isGrouped
    ? (groupedDataRaw?.pagination?.total ?? 0)
    : (flatDataRaw?.pagination?.total ?? 0);
  const pageCount = Math.ceil(totalSPOs / pagination.pageSize);
  const isLoading = isGrouped ? isLoadingGrouped : isLoadingFlat;
  const isFetching = isGrouped ? isFetchingGrouped : isFetchingFlat;

  const toggleGroup = (spoNumber: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(spoNumber)) {
        next.delete(spoNumber);
      } else {
        next.add(spoNumber);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedGroups(new Set(groupedData.map((g) => g.spo_number)));
  };

  const collapseAll = () => {
    setExpandedGroups(new Set());
  };

  const toggleAllocationSelection = (allocationId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setSelectedAllocationIds((prev) => {
      const next = new Set(prev);
      if (next.has(allocationId)) {
        next.delete(allocationId);
      } else {
        next.add(allocationId);
      }
      return next;
    });
  };

  const handleBulkDelete = () => {
    if (selectedAllocationIds.size > 0) {
      setBulkDeleteDialogOpen(true);
    }
  };

  const handleBulkDeleteSuccess = () => {
    setSelectedAllocationIds(new Set());
  };

  const toggleSelectAllInGroup = (group: SPOWithAllocationsGroup) => {
    const ids = group.spo_allocations.map((a) => a.id);
    const allSelected = ids.every((id) => selectedAllocationIds.has(id));
    setSelectedAllocationIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectAllFlat = () => {
    const ids = flatData.map((a) => a.id);
    const allSelected = ids.length > 0 && ids.every((id) => selectedAllocationIds.has(id));
    setSelectedAllocationIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const handleAllocationClick = (allocation: SPOAllocationWithShipped | SPOAllocation) => {
    router.push(`/procurement-management/spo-allocations/${allocation.id}`);
  };

  const groupColumns = useMemo<ColumnDef<SPOWithAllocationsGroup>[]>(
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
              toggleGroup(row.original.spo_number);
            }}
          >
            {expandedGroups.has(row.original.spo_number) ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </Button>
        ),
        size: 50,
      },
      {
        accessorKey: 'spo_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="SPO Number" column={column} />
        ),
        cell: ({ row }) => {
          const spoNumber = row.original.spo_number;
          const count = row.original.spo_allocations.length;
          return (
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm">{spoNumber}</span>
              <Badge variant="secondary" size="sm" className="text-xs">
                {count} allocation{count !== 1 ? 's' : ''}
              </Badge>
            </div>
          );
        },
        size: 220,
        meta: { headerTitle: 'SPO Number', skeleton: <Skeleton className="h-4 w-32" /> },
      },
    ],
    [expandedGroups],
  );

  const flatColumns = useMemo<ColumnDef<SPOAllocation>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={
              flatData.length > 0 &&
              flatData.every((a) => selectedAllocationIds.has(a.id))
            }
            onCheckedChange={toggleSelectAllFlat}
            aria-label="Select all on page"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedAllocationIds.has(row.original.id)}
            onCheckedChange={() => toggleAllocationSelection(row.original.id)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Select ${row.original.spo_number ?? row.original.id}`}
          />
        ),
        size: 44,
      },
      {
        accessorKey: 'spo_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="SPO Number" column={column} />
        ),
        cell: ({ row }) => (
          <span className="font-medium text-sm">{row.original.spo_number ?? '-'}</span>
        ),
        size: 140,
        meta: { headerTitle: 'SPO Number' },
      },
      {
        id: 'product',
        header: 'Product',
        cell: ({ row }) => {
          const p = row.original.product;
          if (!p) return '-';
          return (
            <span className="text-sm">
              {p.product_code}
              {p.product_name && p.product_name !== p.product_code ? ` - ${p.product_name}` : ''}
            </span>
          );
        },
        size: 180,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'location',
        header: 'Location',
        cell: ({ row }) => allocationLocation(row.original),
        size: 100,
        meta: { headerTitle: 'Location' },
      },
      {
        id: 'shipped',
        header: 'Shipped',
        cell: () => '-',
        size: 70,
        meta: { headerTitle: 'Shipped' },
      },
      {
        accessorKey: 'allocated_quantity',
        header: ({ column }) => (
          <DataGridColumnHeader title="Allocated" column={column} />
        ),
        cell: ({ row }) => row.original.allocated_quantity,
        size: 70,
        meta: { headerTitle: 'Allocated' },
      },
      {
        accessorKey: 'quantity_received',
        header: ({ column }) => (
          <DataGridColumnHeader title="Received" column={column} />
        ),
        cell: ({ row }) => row.original.quantity_received,
        size: 70,
        meta: { headerTitle: 'Received' },
      },
      {
        id: 'packing_list',
        header: 'Packing List',
        cell: ({ row }) => {
          const ship = row.original.inbound_shipment;
          if (!ship) return '-';
          return (
            <Link
              href={`/procurement-management/packing-lists/${ship.id}`}
              className="text-primary hover:underline flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <LinkIcon className="size-3" />
              {ship.shipment_number}
              {ship.shipping_container_number && (
                <span className="text-muted-foreground">({ship.shipping_container_number})</span>
              )}
            </Link>
          );
        },
        size: 160,
        meta: { headerTitle: 'Packing List' },
      },
      {
        accessorKey: 'receipt_status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        cell: ({ row }) => (
          <Badge status={row.original.receipt_status} size="sm">
            {row.original.receipt_status
              ?.split('_')
              .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
              .join(' ') ?? '-'}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Status' },
      },
    ],
    [flatData, selectedAllocationIds],
  );

  type TableRow = SPOWithAllocationsGroup | SPOAllocation;
  const columns: ColumnDef<TableRow>[] = isGrouped ? (groupColumns as ColumnDef<TableRow>[]) : (flatColumns as ColumnDef<TableRow>[]);
  const tableData: TableRow[] = isGrouped ? groupedData : flatData;

  const table = useReactTable({
    columns,
    data: tableData,
    pageCount,
    getRowId: (row) => ('spo_allocations' in row ? (row as SPOWithAllocationsGroup).spo_number : (row as SPOAllocation).id),
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button
      onClick={() => router.push('/procurement-management/spo-allocations/new')}
    >
      <Plus className="size-4" />
      Create SPO Allocation
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={totalSPOs}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{ columnsVisibility: true }}
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="flex items-center gap-2 min-w-0 shrink">
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                  placeholder="Search..."
                  className="shrink-0 w-40 sm:w-44"
                />
                <GroupBySelect<ViewMode>
                  value={viewMode}
                  options={GROUP_BY_OPTIONS}
                  onValueChange={(v) => setViewMode(v)}
                  allLabel="All allocations"
                  placeholder="View"
                  className="w-[140px] shrink-0"
                />
                {isGrouped && (
                  <div className="flex items-center shrink-0">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={expandAll}
                      disabled={groupedData.length === 0}
                      title="Expand all"
                      aria-label="Expand all groups"
                    >
                      <ChevronsUpDown className="size-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={collapseAll}
                      disabled={expandedGroups.size === 0}
                      title="Collapse all"
                      aria-label="Collapse all groups"
                    >
                      <ChevronsDownUp className="size-4" />
                    </Button>
                  </div>
                )}
                {/* Selection here is a cross-view (grouped + flat) manual id Set,
                    not react-table rowSelection, so the bulk-delete control stays
                    inline rather than in the toolbar's selection-driven bulk strip. */}
                {selectedAllocationIds.size > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleBulkDelete}
                    className="h-8 shrink-0"
                  >
                    <Trash2 className="size-4" />
                    Delete {selectedAllocationIds.size} selected
                  </Button>
                )}
              </div>
            }
            exportConfig={{ filename: 'spo_allocations_export.xlsx' }}
            secondaryActions={[
              {
                key: 'import',
                label: 'Import SPO',
                icon: Upload,
                onClick: () => setImportDialogOpen(true),
                dataGuideTarget: 'procurement.spo-allocations.import-options-button',
              },
            ]}
            primaryAction={listPrimaryAction}
          />
        </CardHeader>
        <SPOImportDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          onTest={validateSPOAllocations}
          onUpload={async (files) => {
            const result = await importSPOAllocations(files);
            notifyImportQueued();
            queryClient.invalidateQueries({ queryKey: ['spo-allocations'] });
            queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
            return result;
          }}
        />
        <CardTable>
          <ScrollArea>
            <table className="w-full border-collapse table-fixed text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  {table.getHeaderGroups()[0]?.headers.map((header) => (
                    <th
                      key={header.id}
                      className="relative text-left p-3 font-medium text-xs text-muted-foreground truncate"
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
                    <td colSpan={columns.length} className="p-3">
                      <div className="text-center text-muted-foreground text-sm">
                        Loading...
                      </div>
                    </td>
                  </tr>
                ) : !isGrouped && flatData.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="p-3">
                      <div className="text-center text-muted-foreground text-sm">
                        No SPO allocations found.
                      </div>
                    </td>
                  </tr>
                ) : isGrouped && groupedData.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="p-3">
                      <div className="text-center text-muted-foreground text-sm">
                        No SPO allocations found.
                      </div>
                    </td>
                  </tr>
                ) : !isGrouped ? (
                  table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className="border-b hover:bg-accent/50 cursor-pointer"
                      onClick={() => handleAllocationClick(row.original as SPOAllocation)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          className="p-3 truncate text-sm"
                          style={{
                            width: cell.column.getSize(),
                            minWidth: cell.column.getSize(),
                          }}
                        >
                          {typeof cell.column.columnDef.cell === 'function'
                            ? cell.column.columnDef.cell(cell.getContext())
                            : null}
                        </td>
                      ))}
                    </tr>
                  ))
                ) : (
                  groupedData.map((group) => (
                    <React.Fragment key={group.spo_number}>
                      <tr className="border-b hover:bg-accent/50">
                        {table.getHeaderGroups()[0]?.headers.map((header) => {
                          const cell = table
                            .getRow(group.spo_number)
                            ?.getVisibleCells()
                            .find((c) => c.column.id === header.id);
                          return (
                            <td
                              key={header.id}
                              className="p-3 truncate text-sm"
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
                      {expandedGroups.has(group.spo_number) && (
                        <tr>
                          <td
                            colSpan={columns.length}
                            className="p-0 bg-muted/30 align-top"
                          >
                            <div className="p-3">
                              <div className="mb-2 text-xs font-medium text-muted-foreground">
                                Allocations for SPO {group.spo_number}
                              </div>
                              <ScrollArea>
                                <table className="w-auto min-w-full border-collapse text-xs">
                                  <thead>
                                    <tr className="border-b">
                                      <th className="text-left p-1.5 font-medium text-muted-foreground w-8">
                                        <Checkbox
                                          checked={
                                            group.spo_allocations.length === 0
                                              ? false
                                              : group.spo_allocations.every((a) =>
                                                  selectedAllocationIds.has(a.id),
                                                )
                                              ? true
                                              : group.spo_allocations.some((a) =>
                                                  selectedAllocationIds.has(a.id),
                                                )
                                                ? 'indeterminate'
                                                : false
                                          }
                                          onCheckedChange={() =>
                                            toggleSelectAllInGroup(group)
                                          }
                                          aria-label="Select all in this SPO"
                                        />
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground min-w-[120px]">
                                        Product
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground w-[80px]">
                                        Location
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground w-[70px]">
                                        Allocated
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground w-[70px]">
                                        Received
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground min-w-[140px]">
                                        Packing List
                                      </th>
                                      <th className="text-left p-1.5 font-medium text-muted-foreground w-[90px]">
                                        Status
                                      </th>
                                      <th className="w-6" />
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(() => {
                                      // Group allocations by product so shipped qty is shown once per product
                                      const byProduct = new Map<string, SPOAllocationWithShipped[]>();
                                      for (const a of group.spo_allocations) {
                                        const key = a.product_id ?? a.product?.id ?? a.id;
                                        if (!byProduct.has(key)) byProduct.set(key, []);
                                        byProduct.get(key)!.push(a);
                                      }
                                      return Array.from(byProduct.entries()).flatMap(([, allocations]) => {
                                        const first = allocations[0];
                                        const qtyShipped = first.quantity_shipped ?? null;
                                        const productLabel = first.product?.product_code ?? '-';
                                        const productName = first.product?.product_name;
                                        const fullLabel = productName && productName !== productLabel
                                          ? `${productLabel} - ${productName}`
                                          : productLabel;
                                        return allocations.map((allocation, idx) => (
                                          <tr
                                            key={allocation.id}
                                            className="border-b hover:bg-background cursor-pointer"
                                            onClick={() => handleAllocationClick(allocation)}
                                          >
                                            <td className="p-1.5" onClick={(e) => e.stopPropagation()}>
                                              <Checkbox
                                                checked={selectedAllocationIds.has(allocation.id)}
                                                onCheckedChange={() => toggleAllocationSelection(allocation.id)}
                                              />
                                            </td>
                                            <td className="p-1.5">
                                              {idx === 0 ? (
                                                <span className="font-medium">
                                                  {fullLabel}
                                                  {qtyShipped != null && (
                                                    <span className="text-muted-foreground font-normal ms-1">
                                                      ({qtyShipped} shipped)
                                                    </span>
                                                  )}
                                                </span>
                                              ) : (
                                                <span className="text-muted-foreground/70">↳</span>
                                              )}
                                            </td>
                                            <td className="p-1.5">
                                              {allocationLocation(allocation)}
                                            </td>
                                            <td className="p-1.5">
                                              {allocation.allocated_quantity}
                                            </td>
                                        <td className="p-1.5">
                                          {allocation.quantity_received}
                                        </td>
                                        <td className="p-1.5">
                                          {allocation.inbound_shipment ? (
                                            <Link
                                              href={`/procurement-management/packing-lists/${allocation.inbound_shipment.id}`}
                                              className="text-primary hover:underline"
                                              onClick={(e) => e.stopPropagation()}
                                            >
                                              <span className="flex items-center gap-1">
                                                <LinkIcon className="size-3" />
                                                {allocation.inbound_shipment.shipment_number}
                                                {allocation.inbound_shipment.shipping_container_number && (
                                                  <span className="text-muted-foreground">
                                                    ({allocation.inbound_shipment.shipping_container_number})
                                                  </span>
                                                )}
                                              </span>
                                            </Link>
                                          ) : (
                                            '-'
                                          )}
                                        </td>
                                        <td className="p-1.5">
                                          <Badge
                                            status={allocation.receipt_status}
                                            size="sm"
                                          >
                                            {allocation.receipt_status
                                              ?.split('_')
                                              .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                                              .join(' ') ?? '-'}
                                          </Badge>
                                        </td>
                                        <td className="p-1.5">
                                          <ChevronRight className="text-muted-foreground/70 size-3" />
                                        </td>
                                      </tr>
                                        ));
                                      });
                                    })()}
                                  </tbody>
                                </table>
                                <ScrollBar orientation="horizontal" />
                              </ScrollArea>
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
      <SPOBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        allocationIds={Array.from(selectedAllocationIds)}
        onSuccess={handleBulkDeleteSuccess}
      />
    </DataGrid>
  );
}
