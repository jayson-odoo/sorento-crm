'use client';

import * as React from 'react';
import { Plus } from 'lucide-react';
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useQuotationTemplateMutations,
  useQuotationTemplates,
} from '../../_shared/hooks/useQuotationTemplates';
import type {
  QuotationTemplate,
  QuotationTemplateKind,
} from '../../_shared/services/quotationTemplateService';
import { QuotationCoverDesigner } from './QuotationCoverDesigner';
import { QuotationTemplateDialog } from './QuotationTemplateDialog';

type TemplatesTab = Extract<QuotationTemplateKind, 'terms' | 'cover_page'>;

/**
 * The standard terms and conditions, and the cover page designs. The active template is copied
 * into each NEW quotation at creation; quotations that already exist keep the wording they were
 * created with.
 */
export function QuotationTemplatesClient() {
  const [kind, setKind] = React.useState<TemplatesTab>('terms');
  return (
    <div className="space-y-4">
      <Tabs value={kind} onValueChange={(next) => setKind(next as TemplatesTab)}>
        <TabsList variant="line" className="w-full justify-start">
          <TabsTrigger value="terms">Terms</TabsTrigger>
          <TabsTrigger value="cover_page">Cover page</TabsTrigger>
        </TabsList>
      </Tabs>
      <QuotationTemplatesList key={kind} kind={kind} />
    </div>
  );
}

function QuotationTemplatesList({ kind }: { kind: TemplatesTab }) {
  const isDesign = kind === 'cover_page';
  const templates = useQuotationTemplates(kind);
  const { activate, deactivate } = useQuotationTemplateMutations(kind);
  const activateTemplate = activate.mutate;
  const activating = activate.isPending;
  const deactivateTemplate = deactivate?.mutate;
  const deactivating = deactivate?.isPending ?? false;
  const canEdit = useHasPermission('projects.types.edit');
  const [editing, setEditing] = React.useState<QuotationTemplate | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 15,
  });
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'name', desc: false }]);

  const rows = templates.data ?? [];

  const columns = React.useMemo<ColumnDef<QuotationTemplate>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 320,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 130,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="outline">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        size: 130,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => {
          if (!canEdit) return null;
          if (!row.original.is_active) {
            return (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={activating}
                onClick={(event) => {
                  event.stopPropagation();
                  activateTemplate(row.original.id);
                }}
              >
                Activate
              </Button>
            );
          }
          // Only a cover page design can be switched off; the default cover then applies.
          return isDesign && deactivateTemplate ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={deactivating}
              onClick={(event) => {
                event.stopPropagation();
                deactivateTemplate(row.original.id);
              }}
            >
              Deactivate
            </Button>
          ) : null;
        },
      },
    ],
    [activateTemplate, activating, deactivateTemplate, deactivating, isDesign, canEdit],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <>
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={templates.isLoading}
        error={templates.error}
        onRetry={() => void templates.refetch()}
        onRowClick={canEdit ? (row: QuotationTemplate) => setEditing(row) : undefined}
        emptyMessage={
          <span className="flex flex-col items-center gap-1">
            <span className="font-medium text-foreground">
              {isDesign ? 'No cover page designs yet' : 'No terms templates yet'}
            </span>
            <span className="text-xs">
              {isDesign
                ? 'The first design you add becomes the cover page.'
                : 'The first template you add becomes the standard terms.'}
            </span>
          </span>
        }
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        tableClassNames={{ edgeCell: 'px-5' }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              onRefresh={() => void templates.refetch()}
              isRefreshing={templates.isFetching}
              primaryAction={
                canEdit ? (
                  <Button onClick={() => setCreating(true)}>
                    <Plus />
                    {isDesign ? 'Add design' : 'Add template'}
                  </Button>
                ) : undefined
              }
            />
          </CardHeader>
          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      {(creating || editing) && isDesign && (
        <QuotationCoverDesigner
          template={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
      {(creating || editing) && !isDesign && (
        <QuotationTemplateDialog
          template={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
    </>
  );
}
