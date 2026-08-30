'use client';

import { Edit, Trash2, Users, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import type { ColumnDef } from '@tanstack/react-table';
import type { Company } from '../types/company.types';

/**
 * Column definitions for the Companies DataGrid. The grid + canonical toolbar
 * are owned by CompaniesList; this module exposes the columns so selection /
 * export read uniformly from react-table.
 */
export function buildCompanyColumns(handlers: {
  onEdit?: (company: Company) => void;
  onManageAccess?: (company: Company) => void;
  onDelete?: (company: Company) => void;
}): ColumnDef<Company>[] {
  const { onEdit, onManageAccess, onDelete } = handlers;
  return [
    buildSelectColumn<Company>(),
    {
      id: 'name',
      accessorFn: (row) => row.name,
      header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
      size: 260,
      enableSorting: true,
      meta: { headerTitle: 'Name' },
      cell: ({ row }) => (
        <span className="font-medium truncate block" title={row.original.name}>
          {row.original.name}
        </span>
      ),
    },
    {
      id: 'code',
      accessorFn: (row) => row.code,
      header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
      size: 140,
      enableSorting: true,
      meta: { headerTitle: 'Code' },
      cell: ({ row }) => (
        <Badge variant="secondary" size="sm" className="shrink-0 font-mono">
          {row.original.code}
        </Badge>
      ),
    },
    {
      id: 'autocount_ref',
      accessorFn: (row) => row.autocount_ref,
      header: ({ column }) => <DataGridColumnHeader title="AutoCount Ref" column={column} />,
      size: 200,
      enableSorting: false,
      meta: { headerTitle: 'AutoCount Ref' },
      cell: ({ row }) => (
        <span
          className="text-muted-foreground truncate block"
          title={row.original.autocount_ref ?? undefined}
        >
          {row.original.autocount_ref ?? '-'}
        </span>
      ),
    },
    {
      id: 'user_count',
      accessorFn: (row) => row.user_count ?? 0,
      header: ({ column }) => <DataGridColumnHeader title="Users" column={column} />,
      size: 120,
      enableSorting: false,
      meta: { headerTitle: 'Users' },
      cell: ({ row }) => (
        <Badge variant="secondary" size="sm" className="shrink-0 w-fit">
          {row.original.user_count ?? 0}
        </Badge>
      ),
    },
    {
      id: 'contact_count',
      accessorFn: (row) => row.contact_count ?? 0,
      header: ({ column }) => <DataGridColumnHeader title="Contacts" column={column} />,
      size: 120,
      enableSorting: false,
      meta: { headerTitle: 'Contacts' },
      cell: ({ row }) => (
        <Badge variant="secondary" size="sm" className="shrink-0 w-fit">
          {row.original.contact_count ?? 0}
        </Badge>
      ),
    },
    {
      id: 'is_active',
      accessorFn: (row) => row.is_active,
      header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
      size: 130,
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
              onManageAccess?.(row.original);
            }}
            title="Manage access"
          >
            <Users className="size-4" />
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
  ];
}
