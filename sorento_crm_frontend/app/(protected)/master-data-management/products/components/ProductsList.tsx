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
  ChevronRight,
  Plus,
  Search,
  X,
  Edit,
  Trash2,
  Copy,
  Upload,
  Download,
  Filter,
  Settings,
  SlidersHorizontal,
  Columns3,
} from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  DataGrid,
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import {
  DataGridTable,
  DataGridTableRowSelect,
  DataGridTableRowSelectAll,
} from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useProducts } from '../hooks/useProducts';
import { useProductFilters } from '../hooks/useProductFilters';
import { useProductCategorySelectQuery } from '../../shared/hooks/use-product-category-select-query';
import { useBrandSelectQuery } from '../../shared/hooks/use-brand-select-query';
import type { ProductListItem } from '../types/product.types';
import { getProducts, bulkImportProducts, validateProductsImport, type GetProductsParams } from '../services/productService';
import ProductDeleteDialog from './product-delete-dialog';
import ProductBulkDeleteDialog from './ProductBulkDeleteDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { useImportJobDrawer } from '@/components/upload-activity';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { generateExcelFile } from '@/lib/excel-utils';
import type { ColumnOption } from '@/lib/excel-utils';

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
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string | null>('all');

  const {
    filters,
    setCategoryId,
    setBrandId,
    setStatus,
    setSearch,
    clearFilters,
    hasActiveFilters,
  } = useProductFilters();

  // Initialize filters and pagination from URL (e.g. when navigating back from detail)
  useEffect(() => {
    // On a hard refresh, strip the persisted params so the list opens clean.
    if (isReloadRef.current) {
      isReloadRef.current = false;
      if (searchParams.toString()) {
        // Preserve a "products discontinued" deep link through the reload-clean —
        // it is an explicit navigation intent, not persisted list state.
        const batch = searchParams.get('discontinued_batch_id');
        router.replace(batch ? `${pathname}?discontinued_batch_id=${batch}` : pathname);
      }
      return;
    }
    const search = searchParams.get('search') ?? '';
    const category = searchParams.get('category') ?? null;
    const brand = searchParams.get('brand') ?? null;
    const status = searchParams.get('status') ?? 'all';
    const sortField = searchParams.get('sort');
    const sortDir = searchParams.get('sortDir');
    const pageParam = searchParams.get('page');
    const pageSizeParam = searchParams.get('pageSize');
    if (search) {
      setSearchQuery(search);
      setSearch(search);
    }
    if (category) {
      setSelectedCategory(category);
      setCategoryId(category);
    }
    if (brand) {
      setSelectedBrand(brand);
      setBrandId(brand);
    }
    if (status) {
      setSelectedStatus(status);
      setStatus(status === 'active' ? true : status === 'inactive' ? false : undefined);
    }
    if (sortField) {
      setSorting([{ id: sortField, desc: sortDir === 'desc' }]);
    }
    if (pageParam != null || pageSizeParam != null) {
      const page = parseInt(pageParam ?? '0', 10);
      const pageSize = parseInt(pageSizeParam ?? '50', 10);
      setPagination({
        pageIndex: Number.isNaN(page) ? 0 : Math.max(0, page),
        pageSize: Number.isNaN(pageSize) || pageSize < 1 ? 50 : Math.min(pageSize, 500),
      });
    }
  }, [searchParams, setSearch, setCategoryId, setBrandId, setStatus, router, pathname]);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState<ProductListItem | null>(null);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [advancedFilterDialogOpen, setAdvancedFilterDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);

  const selectedRowIds = useMemo(() => Object.keys(rowSelection), [rowSelection]);

  const { data: categories } = useProductCategorySelectQuery();
  const { data: brands } = useBrandSelectQuery();

  // Deep link from a "products discontinued" notification — restrict the list to
  // exactly the products reported in that batch.
  const discontinuedBatchId = searchParams.get('discontinued_batch_id') || undefined;

  // Fetch products from the server API
  const fetchProducts = async ({
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    selectedCategory,
    selectedBrand,
    selectedStatus,
  }: DataGridApiFetchParams & {
    selectedCategory: string | null;
    selectedBrand: string | null;
    selectedStatus: string | null;
  }): Promise<DataGridApiResponse<ProductListItem>> => {
    const sortField = sorting?.[0]?.id || '';
    const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';

    const params: GetProductsParams = {
      pageIndex,
      pageSize,
      sorting,
      searchQuery,
      ...(selectedCategory && selectedCategory !== 'all'
        ? { category_id: selectedCategory }
        : {}),
      ...(selectedBrand && selectedBrand !== 'all'
        ? { brand_id: selectedBrand }
        : {}),
      ...(selectedStatus && selectedStatus !== 'all'
        ? { status: selectedStatus as 'active' | 'inactive' }
        : { status: 'all' }),
      ...(discontinuedBatchId ? { discontinued_batch_id: discontinuedBatchId } : {}),
    };

    return getProducts(params);
  };

  // Products query
  const { data, isLoading, isError, error } = useQuery({
    queryKey: [
      'products',
      pagination,
      sorting,
      searchQuery,
      selectedCategory,
      selectedBrand,
      selectedStatus,
      advancedFilter,
      discontinuedBatchId,
    ],
    queryFn: async () => {
      if (advancedFilter) {
        const sortField = sorting?.[0]?.id || '';
        const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
        return postListQuerySearch<ProductListItem>({
          resource: 'products',
          filter: advancedFilter,
          page: pagination.pageIndex + 1,
          limit: pagination.pageSize,
          sort: sortField || 'created_at',
          dir: sortDirection,
          quick_search: searchQuery || undefined,
          category_id:
            selectedCategory && selectedCategory !== 'all' ? selectedCategory : undefined,
          brand_id: selectedBrand && selectedBrand !== 'all' ? selectedBrand : undefined,
          product_status:
            selectedStatus && selectedStatus !== 'all' ? selectedStatus : undefined,
        });
      }
      return fetchProducts({
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
        selectedCategory,
        selectedBrand,
        selectedStatus,
      });
    },
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

  const handleClearFilters = () => {
    clearFilters();
    setSelectedCategory(null);
    setSelectedBrand(null);
    setSelectedStatus('all');
    setAdvancedFilter(null);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  };

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [advancedFilter]);

  const buildProductDetailUrl = (productId: string) => {
    const params = new URLSearchParams();
    if (searchQuery) params.set('search', searchQuery);
    if (selectedCategory && selectedCategory !== 'all') params.set('category', selectedCategory);
    if (selectedBrand && selectedBrand !== 'all') params.set('brand', selectedBrand);
    if (selectedStatus && selectedStatus !== 'all') params.set('status', selectedStatus);
    const sortField = sorting?.[0]?.id;
    const sortDir = sorting?.[0]?.desc ? 'desc' : 'asc';
    if (sortField) {
      params.set('sort', sortField);
      params.set('sortDir', sortDir);
    }
    params.set('page', String(pagination.pageIndex));
    params.set('pageSize', String(pagination.pageSize));
    const qs = params.toString();
    return `/master-data-management/products/${productId}${qs ? `?${qs}` : ''}`;
  };

  const handleRowClick = (row: ProductListItem) => {
    router.push(buildProductDetailUrl(row.id));
  };

  const handleEdit = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    const [path, qs] = buildProductDetailUrl(row.id).split('?');
    router.push(`${path}/edit${qs ? `?${qs}` : ''}`);
  };

  const handleDelete = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    setProductToDelete(row);
    setDeleteDialogOpen(true);
  };

  const handleDuplicate = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    // TODO: Implement duplicate with modal for new product code
    console.log('Duplicate product:', row.id);
  };

  const columns = useMemo<ColumnDef<ProductListItem>[]>(
    () => [
      {
        id: 'select',
        header: () => <DataGridTableRowSelectAll />,
        cell: ({ row }) => <DataGridTableRowSelect row={row} />,
        size: 40,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="size-5" /> },
        enableResizing: false,
      },
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
              appearance="ghost"
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
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => handleEdit(e, row.original)}
              title="Edit"
            >
              <Edit className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => handleDuplicate(e, row.original)}
              title="Duplicate"
            >
              <Copy className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => handleDelete(e, row.original)}
              title="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </div>
        ),
        meta: {
          skeleton: <Skeleton className="size-4" />,
        },
        size: 120,
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

  const DataGridToolbar = () => {
    const [inputValue, setInputValue] = useState(searchQuery);
    useEffect(() => {
      setInputValue(searchQuery);
    }, [searchQuery]);

    const handleSearch = () => {
      setSearchQuery(inputValue);
      setSearch(inputValue || undefined);
      setPagination({ ...pagination, pageIndex: 0 });
    };

    return (
      <CardHeader className="flex flex-row flex-wrap items-center gap-2 py-5">
        {discontinuedBatchId && (
          <div className="basis-full flex items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
            <span>Showing only the products from a recent “products discontinued” notification.</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.replace(pathname)}
            >
              Clear filter
            </Button>
          </div>
        )}
        <div className="relative flex-1 min-w-[140px] max-w-[280px]">
          <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
          <Input
            placeholder="Search products..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            disabled={isLoading}
            className="ps-9 w-full"
          />
          {searchQuery.length > 0 && (
            <Button
              mode="icon"
              variant="dim"
              className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
              onClick={() => {
                setSearchQuery('');
                setInputValue('');
                setSearch(undefined);
              }}
            >
              <X />
            </Button>
          )}
        </div>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="icon" disabled={isLoading} title="Filters" className="relative">
              <Filter className="size-4" />
              {hasActiveFilters && (
                <span className="absolute -top-1 -end-1 size-2.5 rounded-full bg-primary" />
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72" align="start">
            <div className="space-y-3">
              <h4 className="font-medium text-sm">Filters</h4>
              <Select
                onValueChange={handleCategorySelection}
                value={selectedCategory || 'all'}
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All categories</SelectItem>
                  {(categories ?? []).map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.category_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                onValueChange={handleBrandSelection}
                value={selectedBrand || 'all'}
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Brand" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All brands</SelectItem>
                  {(brands ?? []).map((brand) => (
                    <SelectItem key={brand.id} value={brand.id}>
                      {brand.brand_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                onValueChange={handleStatusSelection}
                value={selectedStatus || 'all'}
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
              {hasActiveFilters && (
                <Button variant="outline" size="sm" onClick={handleClearFilters} className="w-full">
                  Clear Filters
                </Button>
              )}
            </div>
          </PopoverContent>
        </Popover>
        <div className="flex items-center gap-2 ml-auto">
          {selectedRowIds.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setBulkDeleteDialogOpen(true)}
              className="text-destructive border-destructive/50 hover:bg-destructive/10"
            >
              <Trash2 className="size-4 mr-2" />
              Delete selected ({selectedRowIds.length})
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" disabled={isLoading} title="Import options">
                <Settings className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={isLoading}
                onClick={() =>
                  generateExcelFile(
                    [{}],
                    PRODUCT_IMPORT_COLUMNS,
                    'products_import_template.xlsx',
                  )
                }
              >
                <Download className="size-4" />
                Download template
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={isLoading}
                onClick={() => setUploadDialogOpen(true)}
                data-guide-target="master-data.products.upload-button"
              >
                <Upload className="size-4" />
                Upload
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="icon"
            disabled={isLoading}
            title="Advanced filters"
            className="relative"
            onClick={() => setAdvancedFilterDialogOpen(true)}
          >
            <SlidersHorizontal className="size-4" />
            {advancedFilter ? (
              <span className="absolute -top-1 -end-1 size-2.5 rounded-full bg-primary" />
            ) : null}
          </Button>
          <Button
            variant="outline"
            size="icon"
            disabled={isLoading}
            title="Export"
            onClick={() => setExportDialogOpen(true)}
          >
            <Download className="size-4" />
          </Button>
          <DataGridColumnVisibility
            table={table}
            trigger={
              <Button variant="outline" size="sm" className="gap-1">
                <Columns3 className="size-4" />
                Columns
              </Button>
            }
          />
          <Button
            disabled={isLoading}
            onClick={() => router.push('/master-data-management/products/new')}
          >
            <Plus className="size-4" />
            Create Product
          </Button>
        </div>
        </CardHeader>
    );
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      tableLayout={{
        columnsResizable: true,
        columnsPinnable: true,
        columnsMovable: true,
        columnsVisibility: true,
      }}
      tableClassNames={{
        edgeCell: 'px-5',
      }}
    >
      <Card>
        <DataGridToolbar />
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load products'}
          </div>
        ) : null}
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
      {productToDelete && (
        <ProductDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => {
            setDeleteDialogOpen(false);
            setProductToDelete(null);
          }}
          product={productToDelete}
        />
      )}
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
      <ListQueryExportDialog
        resourceKey="products"
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        filename="products_export.xlsx"
        selectedRecordIds={selectedRowIds.length > 0 ? selectedRowIds : undefined}
        getPayload={() => ({
          filter: advancedFilter ?? undefined,
          quick_search: searchQuery || undefined,
          category_id: selectedCategory && selectedCategory !== 'all' ? selectedCategory : undefined,
          brand_id: selectedBrand && selectedBrand !== 'all' ? selectedBrand : undefined,
          product_status: selectedStatus && selectedStatus !== 'all' ? selectedStatus : undefined,
        })}
      />
      <ProductBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        productIds={selectedRowIds}
        onSuccess={() => {
          setRowSelection({});
          queryClient.invalidateQueries({ queryKey: ['products'] });
        }}
      />
    </DataGrid>
  );
};

export default ProductsList;
