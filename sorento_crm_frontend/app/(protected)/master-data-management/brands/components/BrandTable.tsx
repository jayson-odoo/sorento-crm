'use client';

import Link from 'next/link';
import { Copy, Trash2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import type { ColumnDef } from '@tanstack/react-table';
import type { Brand } from '../types/brand.types';

/**
 * Column definitions for the Brands DataGrid. The grid + canonical toolbar are
 * owned by BrandsList; this module exposes the columns so selection/export read
 * uniformly from react-table.
 */
export function buildBrandColumns(handlers: {
  onDuplicate?: (brand: Brand) => void;
  onDelete?: (brand: Brand) => void;
}): ColumnDef<Brand>[] {
  const { onDuplicate, onDelete } = handlers;
  return [
    buildSelectColumn<Brand>(),
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
      cell: ({ row }) => (
        <span className="text-muted-foreground truncate block">{row.original.brand_code}</span>
      ),
    },
    {
      id: 'description',
      accessorFn: (row) => row.description,
      header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
      size: 280,
      enableSorting: false,
      meta: { headerTitle: 'Description' },
      cell: ({ row }) => (
        <span
          className="text-muted-foreground truncate block"
          title={row.original.description ?? undefined}
        >
          {row.original.description ?? '-'}
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
              <Badge variant="secondary" size="sm" className="cursor-help shrink-0 w-fit">
                {row.original.product_count ?? 0}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>Number of products using this brand</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 px-1.5 shrink-0" asChild>
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
      size: 70,
      enableSorting: false,
      enableHiding: false,
      enableResizing: false,
      meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
      // The row opens the brand record, where Edit happens in place, so the
      // cell carries only what is left: Duplicate, then Delete in red (D15).
      cell: ({ row }) => (
        <RowActionsMenu
          ariaLabel={`brand ${row.original.brand_code}`}
          actions={[
            ...(onDuplicate
              ? [
                  {
                    key: 'brand.duplicate',
                    label: 'Duplicate brand',
                    icon: Copy,
                    run: () => onDuplicate(row.original),
                  },
                ]
              : []),
            ...(onDelete
              ? [
                  {
                    key: 'brand.delete',
                    label: 'Delete brand',
                    icon: Trash2,
                    kind: 'destructive' as const,
                    run: () => onDelete(row.original),
                  },
                ]
              : []),
          ]}
        />
      ),
    },
  ];
}
