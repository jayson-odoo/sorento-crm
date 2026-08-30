'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import {
  Plus,
  Search,
  X,
  Trash2,
  Upload,
  Download,
  SlidersHorizontal,
  MessageSquare,
} from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { ProductTypeBadge } from './ProductTypeBadge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useProductFilters } from '../hooks/useProductFilters';
import { useProductCategorySelectQuery } from '../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../shared/hooks/use-brand-select-query';
import { CHAT_SEARCH_LABEL, chatSearchState, type ProductListItem } from '../types/product.types';
import { bulkImportProducts, validateProductsImport } from '../services/productService';
import ProductBulkDeleteDialog from './ProductBulkDeleteDialog';
import ProductBulkChatSearchDialog from './ProductBulkChatSearchDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { useImportJobDrawer } from '@/components/upload-activity';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import {
  buildDetailSearch,
  decodeAdvancedFilter,
  encodeAdvancedFilter,
} from '@/lib/listNavQuery';
import { ProductRowActions } from '../actions';
import {
  fetchProductsPage,
  productsListQueryKey,
  type ProductsListParams,
} from '../lib/listQuery';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { generateExcelFile } from '@/lib/excel-utils';
import type { ColumnOption } from '@/lib/excel-utils';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';

const PRODUCT_IMPORT_COLUMNS: ColumnOption[] = [
  { key: 'Item Code', label: 'Item Code', selected: true },
  { key: 'Description', label: 'Description', selected: true },
  { key: 'Desc 2', label: 'Desc 2', selected: true },
  { key: 'Item Group', label: 'Item Group', selected: true },
  { key: 'Item Brand', label: 'Item Brand', selected: true },
  { key: 'Price', label: 'Price', selected: true },
  { key: 'Is Active', label: 'Is Active', selected: true },
];

const ProductsList = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  // Hard refresh = clean slate: don't restore persisted search/filters from the URL
  // (those params only exist to restore state when navigating BACK from a detail page).
  const isReloadRef = useRef<boolean | null>(null);
  if (isReloadRef.current === null) {
    const nav =
      typeof performance !== 'undefined'
        ? (performance.getEntriesByType('navigation')[0] as
            | PerformanceNavigationTiming
            | undefined)
        : undefined;
    isReloadRef.current = nav?.type === 'reload';
  }
  const queryClient = useQueryClient();
  const { notifyImportQueued } = useImportJobDrawer();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string | null>('all');
  const [selectedVariantFilter, setSelectedVariantFilter] = useState<
    'base' | 'variant' | 'all'
  >('all');

  const {
    setCategoryId,
    setBrandId,
    setStatus,
    setSearch,
    clearFilters,
    hasActiveFilters,
  } = useProductFilters();

  // A hard refresh is a clean slate: the persisted params only exist to restore
  // state when coming BACK from a detail page, so they are stripped rather than
  // read. A "products discontinued" deep link survives it - that is an explicit
  // navigation intent, and dropping its brand slice would widen the list to
  // products the recipient was never notified about.
  useEffect(() => {
    if (!isReloadRef.current) return;
    isReloadRef.current = false;
    if (!searchParams.toString()) return;
    const batch = searchParams.get('discontinued_batch_id');
    const batchBrands = searchParams.get('brand_id');
    if (batch) {
      const kept = new URLSearchParams({ discontinued_batch_id: batch });
      if (batchBrands) kept.set('brand_id', batchBrands);
      router.replace(`${pathname}?${kept.toString()}`);
    } else {
      router.replace(pathname);
    }
  }, [searchParams, router, pathname]);


  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkChatSearchDialogOpen, setBulkChatSearchDialogOpen] = useState(false);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [advancedFilterDialogOpen, setAdvancedFilterDialogOpen] = useState(false);

  // Back hands the list its own query string back, and the pager keeps rewriting
  // it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl(
    (state) => {
      setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
      setSorting(state.sorting);
      setSearchQuery(state.searchQuery);
      setSearchInput(state.searchQuery);
      setSearch(state.searchQuery || undefined);
      const category = state.filters.category_id ?? null;
      setSelectedCategory(category);
      setCategoryId(category ?? undefined);
      // A multi-brand deep link (brand_id=a,b) has no single-select equivalent, so
      // the dropdown stays on "All brands" while the param still filters the grid.
      const brand = state.filters.brand_id ?? null;
      if (!brand || !brand.includes(',')) {
        setSelectedBrand(brand);
        setBrandId(brand ?? undefined);
      }
      const status = state.filters.status ?? 'all';
      setSelectedStatus(status);
      setStatus(status === 'active' ? true : status === 'inactive' ? false : undefined);
      const variant = state.filters.variant_filter;
      setSelectedVariantFilter(variant === 'base' || variant === 'variant' ? variant : 'all');
      setAdvancedFilter(
        decodeAdvancedFilter<ListQueryFilterGroup>(state.filters.advFilter),
      );
    },
    { enabled: !isReloadRef.current },
  );

  const { data: categories } = useProductCategorySelectQuery();
  const { data: brands } = useBrandSelectQuery();

  // Deep link from a "products discontinued" notification - restrict the list to
  // exactly the products reported in that batch.
  const discontinuedBatchId = searchParams.get('discontinued_batch_id') || undefined;
  // ...and, for a recipient scoped to specific brands, to their slice of it. The
  // param is passed through verbatim (comma-separated ids filter with IN).
  const discontinuedBrandIds = discontinuedBatchId
    ? searchParams.get('brand_id') || undefined
    : undefined;
  const effectiveBrandId =
    selectedBrand && selectedBrand !== 'all' ? selectedBrand : discontinuedBrandIds;

  // The list query, built through the shared key + fetch so the detail page's
  // pager reads THIS cache entry instead of asking the server again.
  const listParams = useMemo<ProductsListParams>(
    () => ({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      category_id:
        selectedCategory && selectedCategory !== 'all' ? selectedCategory : undefined,
      brand_id: effectiveBrandId,
      status: selectedStatus ?? 'all',
      variant_filter: selectedVariantFilter,
      discontinued_batch_id: discontinuedBatchId,
      discontinued_brand_ids: discontinuedBrandIds,
      advancedFilter: advancedFilter ?? undefined,
    }),
    [
      pagination,
      sorting,
      searchQuery,
      selectedCategory,
      effectiveBrandId,
      selectedStatus,
      selectedVariantFilter,
      discontinuedBatchId,
      discontinuedBrandIds,
      advancedFilter,
    ],
  );

  const { data, isLoading, isError, error } = useQuery({
    queryKey: productsListQueryKey(listParams),
    queryFn: () => fetchProductsPage(listParams),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  const handleCategorySelection = (categoryId: string) => {
    setSelectedCategory(categoryId);
    setCategoryId(categoryId !== 'all' ? categoryId : undefined);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleBrandSelection = (brandId: string) => {
    setSelectedBrand(brandId);
    setBrandId(brandId !== 'all' ? brandId : undefined);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleStatusSelection = (status: string) => {
    setSelectedStatus(status);
    setStatus(status === 'active' ? true : status === 'inactive' ? false : undefined);
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleVariantFilterSelection = (value: string) => {
    setSelectedVariantFilter(value as 'base' | 'variant' | 'all');
    setPagination({ ...pagination, pageIndex: 0 });
  };

  const handleClearFilters = () => {
    clearFilters();
    setSelectedCategory(null);
    setSelectedBrand(null);
    setSelectedStatus('all');
    setSelectedVariantFilter('all');
    setAdvancedFilter(null);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [advancedFilter]);

  // Carry the active list query (search/sort + category/brand/status/discontinued
  // batch filters) into the detail URL so the detail page's prev/next pager walks
  // the same filtered+sorted set. Uses the SAME param names as the list GET
  // (via buildDataGridParams) so the neighbours hook forwards them verbatim.
  const buildProductDetailUrl = (productId: string) => {
    const qs = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      {
        category_id: listParams.category_id,
        brand_id: listParams.brand_id,
        status:
          listParams.status && listParams.status !== 'all' ? listParams.status : undefined,
        variant_filter:
          selectedVariantFilter !== 'all' ? selectedVariantFilter : undefined,
        discontinued_batch_id: discontinuedBatchId,
        advFilter: encodeAdvancedFilter(advancedFilter),
      },
    );
    return `/master-data-management/products/${productId}${qs ? `?${qs}` : ''}`;
  };

  // The whole row opens the record; the filters the grid does not know about
  // ride in this query string, and the pager rebuilds the list's key from both.
  const rowHref = (row: ProductListItem) => buildProductDetailUrl(row.id);

  const columns = useMemo<ColumnDef<ProductListItem>[]>(
    () => [
      buildSelectColumn<ProductListItem>(),
      {
        accessorKey: 'product_code',
        id: 'product_code',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Product Code"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          return (
            <div className="font-medium text-sm">{row.original.product_code}</div>
          );
        },
        size: 150,
        meta: {
          headerTitle: 'Product Code',
          skeleton: <Skeleton className="h-4 w-24" />,
        },
        enableSorting: true,
        enableHiding: false,
      },
      {
        accessorKey: 'product_name',
        id: 'product_name',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Product Name"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          return (
            <div className="font-medium text-sm">
              {row.original.product_name}
            </div>
          );
        },
        size: 300,
        meta: {
          headerTitle: 'Product Name',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
        enableSorting: true,
        enableHiding: false,
      },
      {
        accessorKey: 'is_variant',
        id: 'variant_type',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Type"
            visibility={true}
            column={column}
          />
        ),
        size: 100,
        cell: ({ row }) => (
          <ProductTypeBadge isVariant={row.original.is_variant} />
        ),
        meta: {
          headerTitle: 'Type',
          skeleton: <Skeleton className="w-14 h-7" />,
        },
        enableSorting: false,
        enableHiding: true,
      },
      {
        accessorKey: 'variant_of',
        id: 'variant_of',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Variant of"
            visibility={true}
            column={column}
          />
        ),
        size: 160,
        cell: ({ row }) => {
          const parent = row.original.variant_of;
          if (!parent) {
            return <span className="text-muted-foreground"> - </span>;
          }
          return (
            <div
              className="truncate text-sm"
              title={`${parent.product_code} - ${parent.product_name}`}
            >
              {parent.product_code}
            </div>
          );
        },
        meta: {
          headerTitle: 'Variant of',
          skeleton: <Skeleton className="h-4 w-24" />,
        },
        enableSorting: false,
        enableHiding: true,
      },
      {
        accessorKey: 'variant_child_count',
        id: 'variant_child_count',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Variants"
            visibility={true}
            column={column}
          />
        ),
        size: 90,
        cell: ({ row }) => (
          <div className="text-sm">{row.original.variant_child_count ?? 0}</div>
        ),
        meta: {
          headerTitle: 'Variants',
          skeleton: <Skeleton className="h-4 w-8" />,
        },
        enableSorting: false,
        enableHiding: true,
      },
      {
        accessorKey: 'category_name',
        id: 'category_name',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Category"
            visibility={true}
            column={column}
          />
        ),
        size: 150,
        cell: ({ row }) => {
          const categoryName = row.original.category_name || row.original.category?.category_name;
          return categoryName ? (
            <Badge variant="secondary">{categoryName}</Badge>
          ) : (
            '-'
          );
        },
        meta: {
          headerTitle: 'Category',
          skeleton: <Skeleton className="w-28 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'brand_name',
        id: 'brand_name',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Brand"
            visibility={true}
            column={column}
          />
        ),
        size: 150,
        cell: ({ row }) => {
          const brandName = row.original.brand_name || row.original.brand?.brand_name;
          return brandName ? (
            <Badge variant="outline">{brandName}</Badge>
          ) : (
            '-'
          );
        },
        meta: {
          headerTitle: 'Brand',
          skeleton: <Skeleton className="w-28 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'list_price',
        id: 'list_price',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="List Price"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const price = row.original.list_price;
          return (
            <div className="text-sm">
              {new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'MYR',
              }).format(price)}
            </div>
          );
        },
        size: 120,
        meta: {
          headerTitle: 'List Price',
          skeleton: <Skeleton className="h-4 w-20" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'is_active',
        id: 'is_active',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Status"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const isActive = row.original.is_active;
          return (
            <Badge
              variant={isActive ? 'success' : 'secondary'}
              appearance="light"
            >
              <BadgeDot />
              {isActive ? 'Active' : 'Inactive'}
            </Badge>
          );
        },
        size: 100,
        meta: {
          headerTitle: 'Status',
          skeleton: <Skeleton className="w-14 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'is_discontinued',
        id: 'is_discontinued',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Discontinued"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const isDiscontinued = row.original.is_discontinued;
          return (
            <Badge
              variant={isDiscontinued ? 'destructive' : 'secondary'}
              appearance="light"
            >
              <BadgeDot />
              {isDiscontinued ? 'Discontinued' : 'Available'}
            </Badge>
          );
        },
        size: 130,
        meta: {
          headerTitle: 'Discontinued',
          skeleton: <Skeleton className="w-20 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'is_searchable',
        id: 'is_searchable',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Chat Search"
            visibility={true}
            column={column}
          />
        ),
        cell: ({ row }) => {
          const state = chatSearchState(row.original);
          return (
            <Badge
              variant={state === 'shown' ? 'success' : 'destructive'}
              appearance="light"
            >
              <BadgeDot />
              {CHAT_SEARCH_LABEL[state]}
            </Badge>
          );
        },
        size: 140,
        meta: {
          headerTitle: 'Chat Search',
          skeleton: <Skeleton className="w-16 h-7" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'created_at',
        id: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Created"
            visibility={true}
            column={column}
          />
        ),
        cell: (info) => {
          const v = info.getValue() as string | null | undefined;
          return v ? formatDateTimeInMalaysia(v) : '-';
        },
        size: 180,
        meta: {
          headerTitle: 'Created',
          skeleton: <Skeleton className="h-4 w-32" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'updated_at',
        id: 'updated_at',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="Updated"
            visibility={true}
            column={column}
          />
        ),
        cell: (info) => {
          const val = info.getValue() as string | null | undefined;
          return val ? formatDateTimeInMalaysia(val) : '-';
        },
        size: 180,
        meta: {
          headerTitle: 'Updated',
          skeleton: <Skeleton className="h-4 w-32" />,
        },
        enableSorting: true,
        enableHiding: true,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => <ProductRowActions product={row.original} />,
        meta: {
          skeleton: <Skeleton className="size-4" />,
        },
        size: 60,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  const [columnOrder, setColumnOrder] = useState<string[]>(
    columns.map((column) => column.id as string),
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row: ProductListItem) => row.id,
    state: {
      pagination,
      sorting,
      columnOrder,
      rowSelection,
    },
    columnResizeMode: 'onChange',
    onColumnOrderChange: setColumnOrder,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    enableRowSelection: true,
  });

  const handleSearch = () => {
    setSearchQuery(searchInput);
    setSearch(searchInput || undefined);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  const simpleFiltersActiveCount =
    (selectedCategory && selectedCategory !== 'all' ? 1 : 0) +
    (selectedBrand && selectedBrand !== 'all' ? 1 : 0) +
    (selectedStatus && selectedStatus !== 'all' ? 1 : 0) +
    (selectedVariantFilter && selectedVariantFilter !== 'all' ? 1 : 0);

  const getExportPayload = () => ({
    filter: advancedFilter ?? undefined,
    quick_search: searchQuery || undefined,
    category_id: selectedCategory && selectedCategory !== 'all' ? selectedCategory : undefined,
    brand_id: selectedBrand && selectedBrand !== 'all' ? selectedBrand : undefined,
    product_status: selectedStatus && selectedStatus !== 'all' ? selectedStatus : undefined,
  });

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button
      disabled={isLoading}
      onClick={() => router.push('/master-data-management/products/new')}
    >
      <Plus className="size-4" />
      Create Product
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      rowHref={rowHref}
      tableLayout={{
        columnsResizable: true,
        columnsPinnable: true,
        columnsMovable: true,
        columnsVisibility: true,
      }}
      tableClassNames={{
        edgeCell: 'px-5',
      }}
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          {discontinuedBatchId && (
            <div className="mb-3 flex items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
              <span>Showing only the products from a recent “products discontinued” notification.</span>
              <Button variant="ghost" size="sm" onClick={() => router.replace(pathname)}>
                Clear filter
              </Button>
            </div>
          )}
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search products..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  disabled={isLoading}
                  className="ps-9 w-64"
                />
                {searchInput.length > 0 && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => {
                      setSearchQuery('');
                      setSearchInput('');
                      setSearch(undefined);
                    }}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
            filters={{
              kind: 'custom',
              active: simpleFiltersActiveCount > 0,
              activeCount: simpleFiltersActiveCount,
              content: (
                <div className="space-y-3">
                  <SearchableSelect
                    value={selectedCategory || 'all'}
                    onChange={handleCategorySelection}
                    disabled={isLoading}
                    placeholder="Category"
                    options={[
                      { value: 'all', label: 'All categories' },
                      ...(categories ?? []).map((cat) => ({
                        value: cat.id,
                        label: cat.category_name,
                      })),
                    ]}
                  />
                  <SearchableSelect
                    value={selectedBrand || 'all'}
                    onChange={handleBrandSelection}
                    disabled={isLoading}
                    placeholder="Brand"
                    options={[
                      { value: 'all', label: 'All brands' },
                      ...(brands ?? []).map((brand) => ({
                        value: brand.id,
                        label: brand.brand_name,
                      })),
                    ]}
                  />
                  <SearchableSelect
                    value={selectedStatus || 'all'}
                    onChange={handleStatusSelection}
                    disabled={isLoading}
                    placeholder="Status"
                    options={[
                      { value: 'all', label: 'All status' },
                      { value: 'active', label: 'Active' },
                      { value: 'inactive', label: 'Inactive' },
                    ]}
                  />
                  <SearchableSelect
                    value={selectedVariantFilter}
                    onChange={handleVariantFilterSelection}
                    disabled={isLoading}
                    placeholder="Variant"
                    options={[
                      { value: 'all', label: 'All products' },
                      { value: 'base', label: 'Base only' },
                      { value: 'variant', label: 'Variants only' },
                    ]}
                  />
                  {(hasActiveFilters || simpleFiltersActiveCount > 0) && (
                    <Button variant="outline" size="sm" onClick={handleClearFilters} className="w-full">
                      Clear Filters
                    </Button>
                  )}
                </div>
              ),
            }}
            exportConfig={{
              kind: 'listQuery',
              resourceKey: 'products',
              filename: 'products_export.xlsx',
              getPayload: getExportPayload,
            }}
            primaryAction={listPrimaryAction}
            secondaryActions={[
              {
                key: 'advanced-filter',
                label: 'Advanced filters',
                icon: SlidersHorizontal,
                onClick: () => setAdvancedFilterDialogOpen(true),
              },
              {
                key: 'template',
                label: 'Download template',
                icon: Download,
                onClick: () =>
                  generateExcelFile([{}], PRODUCT_IMPORT_COLUMNS, 'products_import_template.xlsx'),
              },
              {
                key: 'import',
                label: 'Import',
                icon: Upload,
                onClick: () => setUploadDialogOpen(true),
                dataGuideTarget: 'master-data.products.upload-button',
              },
            ]}
            bulkActions={[
              {
                key: 'chat-search',
                label: 'Chat search',
                icon: MessageSquare,
                onClick: () => setBulkChatSearchDialogOpen(true),
              },
              {
                key: 'delete',
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                onClick: () => setBulkDeleteDialogOpen(true),
              },
            ]}
          />
        </CardHeader>
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load products'}
          </div>
        ) : null}
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
      <TemplateUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onTest={async (data: Record<string, unknown>[]) => validateProductsImport(data)}
        onUpload={async (data: Record<string, unknown>[]) => {
          await bulkImportProducts(data);
          notifyImportQueued();
          toast.success(
            'Import job queued successfully. Processing in background. Refresh or check Import Jobs for status.',
            {
              duration: 5000,
              action: {
                label: 'View Status',
                onClick: () => router.push('/system-management/import-jobs'),
              },
            },
          );
          queryClient.invalidateQueries({ queryKey: ['products'] });
          queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
        }}
        accept=".xlsx,.xls"
      />
      <ListQueryFilterDialog
        resourceKey="products"
        open={advancedFilterDialogOpen}
        onOpenChange={setAdvancedFilterDialogOpen}
        initialFilter={advancedFilter}
        onApply={setAdvancedFilter}
      />
      <ProductBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        productIds={selectedRowIds(table)}
        onSuccess={() => {
          setRowSelection({});
          queryClient.invalidateQueries({ queryKey: ['products'] });
        }}
      />
      <ProductBulkChatSearchDialog
        open={bulkChatSearchDialogOpen}
        onOpenChange={setBulkChatSearchDialogOpen}
        productIds={selectedRowIds(table)}
        onSuccess={() => setRowSelection({})}
      />
    </DataGrid>
  );
};

export default ProductsList;
