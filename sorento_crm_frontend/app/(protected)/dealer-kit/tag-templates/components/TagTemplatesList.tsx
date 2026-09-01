'use client';

/**
 * DataGrid listing of tag templates.
 *
 * Columns: name, family (badge), print size (WxH mm), created_at, actions.
 * "New Template" button opens TagTemplateDialog.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { familyLabel, type TagTemplate } from '@/lib/dealer-kit/tag-template-types';
import {
  deleteTemplate,
  listTemplates,
} from '../../services/tagTemplateService';
import { TagTemplateDialog } from './TagTemplateDialog';

export function TagTemplatesList() {
  const router = useRouter();

  const [templates, setTemplates] = useState<TagTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TagTemplate | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listTemplates();
      setTemplates(data);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const columns = useMemo<ColumnDef<TagTemplate>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Name" />
        ),
        size: 250,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: 'family',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Family" />
        ),
        size: 150,
        cell: ({ row }) => (
          <Badge variant="secondary" className="font-normal">
            {familyLabel(row.original.family)}
          </Badge>
        ),
      },
      {
        id: 'print_size',
        header: 'Print Size',
        size: 120,
        cell: ({ row }) => {
          const ps = row.original.print_size;
          return (
            <span className="text-muted-foreground">
              {ps.width_mm} x {ps.height_mm} mm
            </span>
          );
        },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader column={column} title="Created" />
        ),
        size: 160,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.created_at)}
          </span>
        ),
      },
      {
        id: 'published',
        header: 'Status',
        size: 100,
        cell: ({ row }) =>
          row.original.published_version_id ? (
            <Badge variant="success" className="font-normal">
              Live v{row.original.published_version_no}
            </Badge>
          ) : (
            <Badge variant="outline" className="font-normal">
              Draft
            </Badge>
          ),
      },
      {
        id: 'actions',
        header: '',
        size: 100,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/dealer-kit/tag-templates/${row.original.id}`);
              }}
              title="Edit template"
            >
              <Pencil className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row.original);
              }}
              title="Delete template"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ),
      },
    ],
    [router],
  );

  const table = useReactTable({
    data: templates,
    columns,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {templates.length} template{templates.length !== 1 ? 's' : ''}
          </span>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 size-3.5" />
            New Template
          </Button>
        </CardHeader>
        <CardTable>
          <DataGrid
            table={table}
            recordCount={templates.length}
            isLoading={isLoading}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            onRowClick={(row) =>
              router.push(`/dealer-kit/tag-templates/${row.id}`)
            }
          >
            <DataGridTable />
            <CardFooter className="justify-center">
              <DataGridPagination />
            </CardFooter>
          </DataGrid>
        </CardTable>
      </Card>

      <TagTemplateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={fetchData}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete tag template"
        description={
          deleteTarget
            ? `Are you sure you want to delete "${deleteTarget.name}"? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (deleteTarget) {
            await deleteTemplate(deleteTarget.id);
          }
        }}
        successMessage="Template deleted"
        onSuccess={fetchData}
      />
    </>
  );
}
