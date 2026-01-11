'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  PaginationState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronRight, Plus, Search, X, Edit, Trash2, Copy } from 'lucide-react';
import { formatDate } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  DataGrid,
  DataGridApiFetchParams,
  DataGridApiResponse,
} from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
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
import { useProducts } from '../hooks/useProducts';
import { useProductFilters } from '../hooks/useProductFilters';
import type { ProductListItem } from '../types/product.types';
import { getProducts, type GetProductsParams } from '../services/productService';

const ProductsList = () => {
  const router = useRouter();
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
    };

    return getProducts(params);
  };

  // Products query
  const { data, isLoading } = useQuery({
    queryKey: [
      'products',
      pagination,
      sorting,
      searchQuery,
      selectedCategory,
      selectedBrand,
      selectedStatus,
    ],
    queryFn: () =>
      fetchProducts({
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
        selectedCategory,
        selectedBrand,
        selectedStatus,
      }),
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

  const handleRowClick = (row: ProductListItem) => {
    const productId = row.id;
    router.push(`/master-data-management/products/${productId}`);
  };

  const handleEdit = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    router.push(`/master-data-management/products/${row.id}/edit`);
  };

  const handleDelete = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    // TODO: Implement delete with confirmation dialog
    console.log('Delete product:', row.id);
  };

  const handleDuplicate = (e: React.MouseEvent, row: ProductListItem) => {
    e.stopPropagation();
    // TODO: Implement duplicate with modal for new product code
    console.log('Duplicate product:', row.id);
  };

  const columns = useMemo<ColumnDef<ProductListItem>[]>(
    () => [
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
                currency: 'USD',
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
            title="Created Date"
            visibility={true}
            column={column}
          />
        ),
        cell: (info) => formatDate(new Date(info.getValue() as string)),
        size: 150,
        meta: {
          headerTitle: 'Created Date',
          skeleton: <Skeleton className="h-4 w-20" />,
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
    },
    columnResizeMode: 'onChange',
    onColumnOrderChange: setColumnOrder,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const DataGridToolbar = () => {
    const [inputValue, setInputValue] = useState(searchQuery);

    const handleSearch = () => {
      setSearchQuery(inputValue);
      setSearch(inputValue || undefined);
      setPagination({ ...pagination, pageIndex: 0 });
    };

    return (
      <CardHeader className="flex-col flex-wrap sm:flex-row items-stretch sm:items-center py-5">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search products..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              disabled={isLoading}
              className="ps-9 w-full sm:w-40 md:w-64"
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
          <Select
            onValueChange={handleCategorySelection}
            value={selectedCategory || 'all'}
            defaultValue="all"
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Filter by category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {/* TODO: Populate from category select query */}
            </SelectContent>
          </Select>
          <Select
            onValueChange={handleBrandSelection}
            value={selectedBrand || 'all'}
            defaultValue="all"
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Filter by brand" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All brands</SelectItem>
              {/* TODO: Populate from brand select query */}
            </SelectContent>
          </Select>
          <Select
            onValueChange={handleStatusSelection}
            value={selectedStatus || 'all'}
            defaultValue="all"
            disabled={isLoading}
          >
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
          {hasActiveFilters && (
            <Button
              variant="outline"
              size="sm"
              onClick={clearFilters}
            >
              Clear Filters
            </Button>
          )}
        </div>
        <div className="flex items-center justify-end">
          <Button
            disabled={isLoading}
            onClick={() => {
              router.push('/master-data-management/products/new');
            }}
          >
            <Plus />
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
  );
};

export default ProductsList;
