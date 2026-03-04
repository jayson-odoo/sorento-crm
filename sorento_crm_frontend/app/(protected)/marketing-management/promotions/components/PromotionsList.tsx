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
import { Plus, Search, X, ChevronRight, Trash2, Users, Filter } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { usePromotions } from '../hooks/usePromotions';
import type { Promotion } from '../types/promotion.types';
import { formatDate } from '@/lib/helpers';
import PromotionBulkDeleteDialog from './PromotionBulkDeleteDialog';
import PromotionBulkAccessLevelsDialog from './PromotionBulkAccessLevelsDialog';

export default function PromotionsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPromotionIds, setSelectedPromotionIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkAccessLevelsDialogOpen, setBulkAccessLevelsDialogOpen] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterAccessLevel, setFilterAccessLevel] = useState<string>('all');
  const [filterPromoType, setFilterPromoType] = useState<string>('all');

  const hasActiveFilters = filterStatus !== 'all' || filterAccessLevel !== 'all' || filterPromoType !== 'all';

  const { data, isLoading } = usePromotions({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: filterStatus === 'all' ? undefined : filterStatus,
    user_type: filterAccessLevel === 'all' ? undefined : filterAccessLevel,
    promo_type: filterPromoType === 'all' ? undefined : filterPromoType,
  });

  const pagePromotions = data?.data ?? [];
  const togglePromotionSelection = (promotionId: string) => {
    setSelectedPromotionIds((prev) => {
      const next = new Set(prev);
      if (next.has(promotionId)) next.delete(promotionId);
      else next.add(promotionId);
      return next;
    });
  };
  const selectAllPromotions = () => {
    if (selectedPromotionIds.size === pagePromotions.length) {
      setSelectedPromotionIds(new Set());
    } else {
      setSelectedPromotionIds(new Set(pagePromotions.map((p) => p.id)));
    }
  };
  const isAllSelected = pagePromotions.length > 0 && selectedPromotionIds.size === pagePromotions.length;

  const columns = useMemo<ColumnDef<Promotion>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllPromotions}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedPromotionIds.has(row.original.id)}
            onCheckedChange={() => togglePromotionSelection(row.original.id)}
            aria-label={`Select ${row.original.promo_code}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'promo_code',
        header: ({ column }) => <DataGridColumnHeader title="Promo Code" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 max-w-full truncate" title={row.original.promo_code || ''}>
            {row.original.promo_code || '-'}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 max-w-full truncate" title={row.original.name || ''}>
            {row.original.name || '-'}
          </div>
        ),
        size: 220,
        minSize: 150,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'promo_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => {
          const type = row.original.promo_type;
          const typeLabels: Record<string, string> = {
            price_override: 'Price Override',
            discount_percent: 'Discount %',
            discount_amount: 'Discount Amount',
            bundle: 'Bundle',
            other: 'Other',
          };
          return <Badge variant="secondary">{typeLabels[type as string] || type}</Badge>;
        },
        size: 150,
      },
      {
        accessorKey: 'access_levels',
        header: ({ column }) => <DataGridColumnHeader title="Access" column={column} />,
        cell: ({ row }) => {
          const levels = row.original.access_levels || [];
          if (!levels.length) return '-';
          return (
            <div className="flex flex-wrap gap-2">
              {levels.map((level) => (
                <Badge key={level} variant="secondary">
                  {level === 'dealer' ? 'Dealer' : 'End User'}
                </Badge>
              ))}
            </div>
          );
        },
        size: 160,
        minSize: 120,
      },
      {
        accessorKey: 'start_date',
        header: ({ column }) => <DataGridColumnHeader title="Start Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.start_date)),
        size: 120,
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.end_date)),
        size: 120,
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 100,
      },
      {
        accessorKey: 'products_count',
        header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
        size: 100,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
      },
    ],
    [selectedPromotionIds, isAllSelected, pagePromotions.length],
  );

  const handleRowClick = (row: Promotion) => {
    const promotionId = row.id;
    router.push(`/marketing-management/promotions/${promotionId}`);
  };

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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading} onRowClick={handleRowClick}>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search promotions..."
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
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className={hasActiveFilters ? 'border-primary' : ''} title="Filters">
                  <Filter className="size-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72" align="start">
                <div className="space-y-4">
                  <h4 className="font-medium">Filters</h4>
                  <div className="space-y-2">
                    <Label>Status</Label>
                    <Select value={filterStatus} onValueChange={setFilterStatus}>
                      <SelectTrigger>
                        <SelectValue placeholder="All" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="active">Active</SelectItem>
                        <SelectItem value="inactive">Inactive</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Access level</Label>
                    <Select value={filterAccessLevel} onValueChange={setFilterAccessLevel}>
                      <SelectTrigger>
                        <SelectValue placeholder="All" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="dealer">Dealer</SelectItem>
                        <SelectItem value="end_user">End User</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Type</Label>
                    <Select value={filterPromoType} onValueChange={setFilterPromoType}>
                      <SelectTrigger>
                        <SelectValue placeholder="All" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="price_override">Price Override</SelectItem>
                        <SelectItem value="discount_percent">Discount %</SelectItem>
                        <SelectItem value="discount_amount">Discount Amount</SelectItem>
                        <SelectItem value="bundle">Bundle</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {hasActiveFilters && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => {
                        setFilterStatus('all');
                        setFilterAccessLevel('all');
                        setFilterPromoType('all');
                      }}
                    >
                      Clear filters
                    </Button>
                  )}
                </div>
              </PopoverContent>
            </Popover>
          </div>
          <div className="flex items-center gap-2">
            {selectedPromotionIds.size > 0 && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setBulkAccessLevelsDialogOpen(true)}
                >
                  <Users className="size-4" />
                  Set Access Levels ({selectedPromotionIds.size})
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setBulkDeleteDialogOpen(true)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="size-4" />
                  Bulk Delete ({selectedPromotionIds.size})
                </Button>
              </>
            )}
            <Button onClick={() => router.push('/marketing-management/promotions/new')}>
              <Plus />
              Create Promotion
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
      <PromotionBulkAccessLevelsDialog
        open={bulkAccessLevelsDialogOpen}
        onOpenChange={(open) => {
          setBulkAccessLevelsDialogOpen(open);
          if (!open) setSelectedPromotionIds(new Set());
        }}
        promotionIds={Array.from(selectedPromotionIds)}
        onSuccess={() => setSelectedPromotionIds(new Set())}
      />
      <PromotionBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedPromotionIds(new Set());
        }}
        promotionIds={Array.from(selectedPromotionIds)}
        onSuccess={() => setSelectedPromotionIds(new Set())}
      />
    </DataGrid>
  );
}
