'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Download, Filter, Pencil, Plus, Search, SlidersHorizontal, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { useTenantModules } from '@/hooks/useTenantModules';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import {
  useCreateWorkflowDefinition,
  useDeleteWorkflowDefinition,
  useWorkflowDefinitionsGridQuery,
} from '../hooks/useWorkflowForms';
import type { WorkflowFormDefinition } from '../types/workflowForms.types';

export default function WorkflowDefinitionsList() {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const listQueryToolsEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('workflow_forms');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 20 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [quickStatus, setQuickStatus] = useState<'all' | 'active' | 'inactive'>('all');

  const { data, isLoading, isError, error } = useWorkflowDefinitionsGridQuery({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    advancedFilter,
    quickStatus,
  });

  const createMut = useCreateWorkflowDefinition();
  const delMut = useDeleteWorkflowDefinition();
  const canAdd = useHasPermission('workflow_forms.definitions.add');
  const canEdit = useHasPermission('workflow_forms.definitions.edit');
  const canDelete = useHasPermission('workflow_forms.definitions.delete');
  const canExport = useHasPermission('workflow_forms.definitions.export');

  const [open, setOpen] = useState(false);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [advancedFilter, searchQuery, quickStatus]);

  const submitCreate = () => {
    createMut.mutate(
      { code: code.trim().toLowerCase(), name: name.trim(), description: desc || undefined },
      {
        onSuccess: () => {
          setOpen(false);
          setCode('');
          setName('');
          setDesc('');
        },
      },
    );
  };

  const quickFilterActive = quickStatus !== 'all';

  const columns = useMemo<ColumnDef<WorkflowFormDefinition>[]>(
    () => [
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => <span className="font-mono text-sm">{row.original.code}</span>,
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 220,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'published',
        header: 'Published',
        cell: ({ row }) =>
          row.original.published_version_number != null ? (
            <Badge variant="primary">v{row.original.published_version_number}</Badge>
          ) : (
            <span className="text-muted-foreground text-sm">—</span>
          ),
        size: 110,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="h-5 w-10" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="success">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
        size: 110,
        meta: { skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            {canEdit ? (
              <Button size="icon" variant="ghost" asChild>
                <Link href={`/workflow-forms-management/definitions/${row.original.id}`} aria-label="Edit">
                  <Pencil className="size-4" />
                </Link>
              </Button>
            ) : null}
            {canDelete ? (
              <Button
                size="icon"
                variant="ghost"
                aria-label="Delete"
                onClick={() => {
                  if (confirm(`Delete workflow form "${row.original.name}"?`)) delMut.mutate(row.original.id);
                }}
              >
                <Trash2 className="size-4 text-destructive" />
              </Button>
            ) : null}
          </div>
        ),
        size: 100,
        enableSorting: false,
      },
    ],
    [canEdit, canDelete, delMut],
  );

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil((data?.pagination.total ?? 0) / pagination.pageSize),
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
      recordCount={data?.pagination.total ?? 0}
      isLoading={isLoading}
      onRowClick={(row) => router.push(`/workflow-forms-management/definitions/${row.id}`)}
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search code or name…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="ps-9 w-64 max-w-full"
              />
              {searchQuery ? (
                <Button
                  mode="icon"
                  variant="dim"
                  className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => setSearchQuery('')}
                >
                  <X />
                </Button>
              ) : null}
            </div>
            {listQueryToolsEnabled ? (
              <>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="relative shrink-0"
                      title="Quick filters — status"
                      aria-label="Quick filters"
                    >
                      <SlidersHorizontal className="size-4" />
                      {quickFilterActive ? (
                        <span className="absolute end-1 top-1 size-2 rounded-full bg-primary" aria-hidden />
                      ) : null}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-72" align="start">
                    <div className="space-y-3">
                      <h4 className="text-sm font-semibold">Quick filters</h4>
                      <div className="space-y-2">
                        <Label htmlFor="wf-def-status" className="text-xs">
                          Status
                        </Label>
                        <select
                          id="wf-def-status"
                          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                          value={quickStatus}
                          onChange={(e) =>
                            setQuickStatus(e.target.value as 'all' | 'active' | 'inactive')
                          }
                        >
                          <option value="all">All</option>
                          <option value="active">Active only</option>
                          <option value="inactive">Inactive only</option>
                        </select>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
                <Button variant="outline" size="sm" className="gap-1" onClick={() => setFilterDialogOpen(true)}>
                  <Filter className="size-4" />
                  Filters
                  {advancedFilter ? (
                    <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                      On
                    </Badge>
                  ) : null}
                </Button>
                {canExport ? (
                  <Button variant="outline" size="sm" className="gap-1" onClick={() => setExportDialogOpen(true)}>
                    <Download className="size-4" />
                    Export
                  </Button>
                ) : null}
              </>
            ) : null}
          </div>
          {canAdd ? (
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="size-4 mr-1" />
                  New workflow form
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create workflow form</DialogTitle>
                </DialogHeader>
                <div className="grid gap-3 py-2">
                  <div className="space-y-1">
                    <Label>Code (unique, lowercase)</Label>
                    <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. leave_request" />
                  </div>
                  <div className="space-y-1">
                    <Label>Name</Label>
                    <Input value={name} onChange={(e) => setName(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <Label>Description</Label>
                    <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={submitCreate} disabled={!code.trim() || !name.trim() || createMut.isPending}>
                    Create
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          ) : null}
        </CardHeader>
        {!listQueryToolsEnabled ? (
          <div className="px-5 pb-2 text-sm text-muted-foreground">
            Install the Workflow Forms module to enable advanced filters and export.
          </div>
        ) : null}
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load workflow forms'}
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
      {listQueryToolsEnabled ? (
        <>
          <ListQueryFilterDialog
            resourceKey="workflow_form_definitions"
            open={filterDialogOpen}
            onOpenChange={setFilterDialogOpen}
            initialFilter={advancedFilter}
            onApply={setAdvancedFilter}
          />
          <ListQueryExportDialog
            resourceKey="workflow_form_definitions"
            open={exportDialogOpen}
            onOpenChange={setExportDialogOpen}
            filename="workflow_form_definitions.xlsx"
            getPayload={() => ({
              filter: advancedFilter ?? undefined,
              quick_search: searchQuery || undefined,
              workflow_definition_is_active:
                quickStatus === 'all' ? undefined : quickStatus === 'active',
            })}
          />
        </>
      ) : null}
    </DataGrid>
  );
}
