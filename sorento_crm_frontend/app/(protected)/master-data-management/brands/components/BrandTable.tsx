'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { Edit, Copy, Trash2, ChevronRight, ExternalLink, Columns3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';
import type { Brand } from '../types/brand.types';

interface BrandTableProps {
  brands: Brand[];
  searchQuery?: string;
  onEdit?: (brand: Brand) => void;
  onDuplicate?: (brand: Brand) => void;
  onDelete?: (brand: Brand) => void;
}

export default function BrandTable({
  brands,
  searchQuery = '',
  onEdit,
  onDuplicate,
  onDelete,
}: BrandTableProps) {
  const filteredBrands = useMemo(
    () =>
      brands.filter(
        (b) =>
          b.brand_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          b.brand_code?.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [brands, searchQuery],
  );

  const columns = useMemo<ColumnDef<Brand>[]>(
    () => [
      {
        id: 'brand_name',
        accessorFn: (row) => row.brand_name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 280,
        enableSorting: true,
        meta: { headerTitle: 'Name' },
        cell: ({ row }) => (
          <span className="font-medium truncate block">{row.original.brand_name}</span>
        ),
      },
      {
        id: 'brand_code',
        accessorFn: (row) => row.brand_code,
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 180,
        enableSorting: true,
        meta: { headerTitle: 'Code' },
        cell: ({ row }) => <span className="text-muted-foreground truncate block">{row.original.brand_code}</span>,
      },
      {
        id: 'description',
        accessorFn: (row) => row.description,
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 280,
        enableSorting: false,
        meta: { headerTitle: 'Description' },
        cell: ({ row }) => (
          <span className="text-muted-foreground truncate block" title={row.original.description ?? undefined}>
            {row.original.description ?? '—'}
          </span>
        ),
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Active' },
        cell: ({ row }) => (
          <Badge
            variant={row.original.is_active ? 'success' : 'secondary'}
            size="sm"
            appearance="ghost"
            className="shrink-0"
          >
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
      },
      {
        id: 'product_count',
        accessorFn: (row) => row.product_count ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Products' },
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="secondary"
                  size="sm"
                  className="cursor-help shrink-0 w-fit"
                >
                  {row.original.product_count ?? 0}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>Number of products using this brand</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 shrink-0"
                  asChild
                >
                  <Link
                    href={`/master-data-management/products?brand=${row.original.id}`}
                    className="text-muted-foreground hover:text-foreground"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink className="size-3.5" />
                    <span className="sr-only">View products (opens in new tab)</span>
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>View products with this brand</TooltipContent>
            </Tooltip>
          </div>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 180,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onEdit?.(row.original);
              }}
              title="Edit"
            >
              <Edit className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onDuplicate?.(row.original);
              }}
              title="Duplicate"
            >
              <Copy className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onDelete?.(row.original);
              }}
              title="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
            <ChevronRight className="text-muted-foreground/70 size-3.5 shrink-0" />
          </div>
        ),
      },
    ],
    [onDelete, onDuplicate, onEdit],
  );

  const table = useReactTable({
    columns,
    data: filteredBrands,
    getRowId: (row) => row.id,
    state: {
      pagination: { pageIndex: 0, pageSize: 10 },
    },
    getCoreRowModel: getCoreRowModel(),
  });

  if (filteredBrands.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4">No brands found</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <DataGrid table={table} recordCount={filteredBrands.length} isLoading={false} tableLayout={{ width: 'fixed' }}>
        <div className="mb-3 flex items-center justify-end">
          <DataGridColumnVisibility
            table={table}
            trigger={
              <Button variant="outline" size="sm" className="gap-1">
                <Columns3 className="size-4" />
                Columns
              </Button>
            }
          />
        </div>
        <DataGridTable />
      </DataGrid>
    </div>
  );
}
