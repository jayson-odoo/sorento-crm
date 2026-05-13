'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { ChevronRight, Columns3, Download, Eye, Filter, Plus, Search, SlidersHorizontal, Trash2, Users, X } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
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
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { useTenantModules } from '@/hooks/useTenantModules';
import AttachmentDetailModal from '@/app/(protected)/resource-management/attachments/components/AttachmentDetailModal';
import { getPromotions } from '../services/promotionService';
import type { Promotion } from '../types/promotion.types';
import { formatPromotionBoundaryInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { postListQuerySearch, type ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import PromotionBulkDeleteDialog from './PromotionBulkDeleteDialog';
import PromotionBulkAccessLevelsDialog from './PromotionBulkAccessLevelsDialog';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';

export default function PromotionsList() {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const listQueryToolsEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('marketing');

  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const accessLevelNameMap = useMemo(() => {
    const m = new Map<string, string>();
    accessTypeOptions.forEach((o) => m.set(o.code, o.name || o.code));
    return m;
  }, [accessTypeOptions]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPromotionIds, setSelectedPromotionIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkAccessLevelsDialogOpen, setBulkAccessLevelsDialogOpen] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterAccessLevel, setFilterAccessLevel] = useState<string>('all');
  const [filterPromoType, setFilterPromoType] = useState<string>('all');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [viewerAttachmentId, setViewerAttachmentId] = useState<string | null>(null);

  const hasActiveFilters = filterStatus !== 'all' || filterAccessLevel !== 'all' || filterPromoType !== 'all';

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: [
      'promotions',
      pagination.pageIndex,
      pagination.pageSize,
      sorting,
      searchQuery,
      filterStatus,
      filterAccessLevel,
      filterPromoType,
      advancedFilter,
    ],
    queryFn: async () => {
      if (advancedFilter) {
        const sortField = sorting?.[0]?.id || '';
        const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
        return postListQuerySearch<Promotion>({
          resource: 'promotions',
          filter: advancedFilter,
          page: pagination.pageIndex + 1,
          limit: pagination.pageSize,
          sort: sortField || 'created_at',
          dir: sortDirection,
          quick_search: searchQuery || undefined,
          promotion_status: filterStatus === 'all' ? undefined : filterStatus,
          promotion_promo_type: filterPromoType === 'all' ? undefined : filterPromoType,
          promotion_access_level: filterAccessLevel === 'all' ? undefined : filterAccessLevel,
        });
      }
      return getPromotions({
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
        status: filterStatus === 'all' ? undefined : filterStatus,
        user_type: filterAccessLevel === 'all' ? undefined : filterAccessLevel,
        promo_type: filterPromoType === 'all' ? undefined : filterPromoType,
      });
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [advancedFilter, filterStatus, filterAccessLevel, filterPromoType]);

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
        accessorKey: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const desc = row.original.description;
          if (!desc) return <span className="text-muted-foreground">-</span>;
          return (
            <div className="min-w-0 max-w-full truncate" title={desc}>
              {desc}
            </div>
          );
        },
        size: 260,
        minSize: 160,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'attachments',
        header: ({ column }) => <DataGridColumnHeader title="Attachments" column={column} />,
        cell: ({ row }) => {
          const items = (row.original.attachments ?? [])
            .map((pa) => pa.attachment)
            .filter((a): a is NonNullable<typeof a> => !!a && !!a.original_filename);
          if (!items.length) return <span className="text-muted-foreground">-</span>;
          const handleOpenDetail = (
            e: React.MouseEvent<HTMLButtonElement>,
            attachmentId: string,
          ) => {
            e.stopPropagation();
            setViewerAttachmentId(attachmentId);
          };
          return (
            <div
              className="min-w-0 max-w-full truncate"
              title={items.map((a) => a.original_filename).join('\n')}
            >
              {items.map((a, idx) => (
                <span key={a.id} className="inline-flex items-center gap-1 align-middle">
                  <span>{a.original_filename}</span>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-primary focus:outline-none"
                    onClick={(e) => handleOpenDetail(e, a.id)}
                    title="View attachment details"
                    aria-label={`View details of ${a.original_filename}`}
                  >
                    <Eye className="size-3.5" />
                  </button>
                  {idx < items.length - 1 ? <span>, </span> : null}
                </span>
              ))}
            </div>
          );
        },
        size: 260,
        minSize: 180,
        enableSorting: false,
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
                  {accessLevelNameMap.get(level) ?? level}
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
        cell: ({ row }) => formatPromotionBoundaryInMalaysia(row.original.start_date),
        size: 120,
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End Date" column={column} />,
        cell: ({ row }) => formatPromotionBoundaryInMalaysia(row.original.end_date),
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
        cell: ({ row }) => (
          <span className="tabular-nums">{row.original.products_count ?? 0}</span>
        ),
        size: 100,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => {
          const created = row.original.created_at;
          if (!created) return <span className="text-muted-foreground">-</span>;
          return (
            <span className="whitespace-nowrap tabular-nums">
              {formatDateTimeInMalaysia(created as unknown as string)}
            </span>
          );
        },
        size: 160,
        minSize: 140,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
      },
    ],
    [selectedPromotionIds, isAllSelected, pagePromotions.length, accessLevelNameMap],
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
    <DataGrid
      table={table}
      tableLayout={{ columnsVisibility: true }}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
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
                <Button
                  variant="outline"
                  size="icon"
                  className={hasActiveFilters ? 'border-primary' : ''}
                  title="Quick filters"
                >
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
                        {accessTypeOptions.map((opt) => (
                          <SelectItem key={opt.code} value={opt.code}>
                            {opt.name || opt.code}
                          </SelectItem>
                        ))}
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
                      Clear quick filters
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
            {listQueryToolsEnabled ? (
              <>
                <Button
                  variant="outline"
                  size="icon"
                  title="Advanced filters"
                  className="relative"
                  onClick={() => setFilterDialogOpen(true)}
                >
                  <SlidersHorizontal className="size-4" />
                  {advancedFilter ? (
                    <span className="absolute -top-1 -end-1 size-2.5 rounded-full bg-primary" />
                  ) : null}
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  title="Export"
                  onClick={() => setExportDialogOpen(true)}
                >
                  <Download className="size-4" />
                </Button>
              </>
            ) : null}
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
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
      <AttachmentDetailModal
        open={viewerAttachmentId !== null}
        onOpenChange={(open) => {
          if (!open) setViewerAttachmentId(null);
        }}
        attachmentId={viewerAttachmentId}
      />
      {listQueryToolsEnabled ? (
        <>
          <ListQueryFilterDialog
            resourceKey="promotions"
            open={filterDialogOpen}
            onOpenChange={setFilterDialogOpen}
            initialFilter={advancedFilter}
            onApply={setAdvancedFilter}
          />
          <ListQueryExportDialog
            resourceKey="promotions"
            filename="promotions-export"
            open={exportDialogOpen}
            onOpenChange={setExportDialogOpen}
            getPayload={() => ({
              filter: advancedFilter ?? undefined,
              quick_search: searchQuery || undefined,
              promotion_status: filterStatus === 'all' ? undefined : filterStatus,
              promotion_promo_type: filterPromoType === 'all' ? undefined : filterPromoType,
              promotion_access_level: filterAccessLevel === 'all' ? undefined : filterAccessLevel,
            })}
            selectedRecordIds={
              selectedPromotionIds.size > 0 ? Array.from(selectedPromotionIds) : undefined
            }
          />
        </>
      ) : null}
    </DataGrid>
  );
}
