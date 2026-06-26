'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, Pencil, Trash2, ChevronRight } from 'lucide-react';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  useDeleteEmailTemplate,
  useEmailTemplates,
} from '../hooks/useEmailTemplates';
import type { EmailTemplate } from '../types/emailTemplate.types';
import EmailTemplateForm from './EmailTemplateForm';

export default function EmailTemplatesList() {
  const router = useRouter();
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 50 });
  const [query, setQuery] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<EmailTemplate | null>(null);
  const [deleting, setDeleting] = useState<EmailTemplate | null>(null);

  const params = useMemo(
    () => ({
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      query: query.trim() || undefined,
    }),
    [pagination, query],
  );

  const { data, isLoading, isFetching, refetch } = useEmailTemplates(params);
  const rows = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;
  const deleteMut = useDeleteEmailTemplate();

  const columns = useMemo<ColumnDef<EmailTemplate>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.code}
          </Badge>
        ),
        size: 200,
        meta: { skeleton: <Skeleton className="h-6 w-32" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium" title={row.original.name}>
              {row.original.name}
            </span>
            {row.original.description && (
              <span className="text-xs text-muted-foreground truncate max-w-[260px]" title={row.original.description}>
                {row.original.description}
              </span>
            )}
          </div>
        ),
        size: 280,
      },
      {
        accessorKey: 'subject',
        header: ({ column }) => <DataGridColumnHeader title="Subject" column={column} />,
        cell: ({ row }) => (
          <span className="truncate max-w-[320px] block" title={row.original.subject}>
            {row.original.subject}
          </span>
        ),
        size: 320,
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'}>
            {row.original.is_active ? 'Yes' : 'No'}
          </Badge>
        ),
        size: 90,
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.updated_at),
        size: 160,
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={(e) => {
                e.stopPropagation();
                setEditing(row.original);
                setShowForm(true);
              }}
              aria-label="Edit"
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleting(row.original);
              }}
              aria-label="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/system-management/email-templates/${row.original.id}`);
              }}
              aria-label="View"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        ),
        size: 140,
      },
    ],
    [router],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { pagination },
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater(pagination) : updater;
      setPagination(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      onRowClick={(t) => t?.id && router.push(`/system-management/email-templates/${t.id}`)}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Input
            placeholder="Search by code, name, subject"
            value={query}
            onChange={(e) => {
              setPagination((p) => ({ ...p, pageIndex: 0 }));
              setQuery(e.target.value);
            }}
            className="max-w-sm"
          />
          <Button
            onClick={() => {
              setEditing(null);
              setShowForm(true);
            }}
          >
            <Plus className="mr-1 size-4" /> Add template
          </Button>
        </CardHeader>
        <CardTable>
          <ScrollArea className="w-full">
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter className="flex justify-between border-t px-4 py-3">
          <DataGridPagination />
        </CardFooter>
      </Card>

      <EmailTemplateForm
        open={showForm}
        onOpenChange={(o) => {
          setShowForm(o);
          if (!o) setEditing(null);
        }}
        template={editing}
      />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Confirm delete"
        description={
          <>
            Delete email template <strong>{deleting?.name}</strong>? This action cannot be undone.
          </>
        }
        successMessage="Email template deleted"
        queryKeysToInvalidate={[['email-templates']]}
        onDelete={async () => {
          if (deleting) await deleteMut.mutateAsync(deleting.id);
        }}
      />
    </DataGrid>
  );
}
