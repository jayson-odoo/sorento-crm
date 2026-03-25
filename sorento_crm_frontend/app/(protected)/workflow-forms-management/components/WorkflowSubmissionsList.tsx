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
import { Download, Filter, Plus, Search, SlidersHorizontal, X, Columns3 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { useTenantModules } from '@/hooks/useTenantModules';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import {
  usePublishedWorkflowDefinitionsForSubmissionQuery,
  useWorkflowSubmissionsGridQuery,
} from '../hooks/useWorkflowForms';
import type { WorkflowSubmission } from '../types/workflowForms.types';

export default function WorkflowSubmissionsList({
  fixedDefinitionId,
}: {
  /** When set, list is scoped to this workflow form (menu entry). */
  fixedDefinitionId?: string;
}) {
  const router = useRouter();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const listQueryToolsEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('workflow_forms');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [scopeDefinitionId, setScopeDefinitionId] = useState<string>(fixedDefinitionId ?? '__all');
  const [quickStateCode, setQuickStateCode] = useState('');

  const { data: pubDefs } = usePublishedWorkflowDefinitionsForSubmissionQuery();
  const { data, isLoading, isError, error } = useWorkflowSubmissionsGridQuery({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    advancedFilter,
    fixedDefinitionId,
    scopeDefinitionId,
    quickStateCode,
  });

  const canAdd = useHasPermission('workflow_forms.submissions.add');
  const canExport = useHasPermission('workflow_forms.submissions.export');

  useEffect(() => {
    if (fixedDefinitionId) setScopeDefinitionId(fixedDefinitionId);
  }, [fixedDefinitionId]);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [advancedFilter, searchQuery, quickStateCode, scopeDefinitionId, fixedDefinitionId]);

  const defOptions = useMemo(() => pubDefs?.data ?? [], [pubDefs?.data]);
  const formTitle = fixedDefinitionId
    ? defOptions.find((d) => d.id === fixedDefinitionId)?.name
    : null;

  const quickFilterActive = Boolean(quickStateCode.trim());

  const columns = useMemo<ColumnDef<WorkflowSubmission>[]>(
    () => [
      {
        id: 'form',
        header: 'Form',
        cell: ({ row }) => {
          const dn =
            row.original.definition_name ||
            row.original.definition_code ||
            defOptions.find((d) => d.id === row.original.definition_id)?.name ||
            'Submission';
          return <span className="font-medium">{dn}</span>;
        },
        size: 220,
        enableSorting: false,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'current_state_code',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => <Badge variant="secondary">{row.original.current_state_code}</Badge>,
        size: 130,
        meta: { skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) =>
          row.original.updated_at ? new Date(row.original.updated_at).toLocaleString() : '—',
        size: 180,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
            <Button size="sm" variant="outline" asChild>
              <Link href={`/workflow-forms-management/submissions/${row.original.id}`}>Open</Link>
            </Button>
          </div>
        ),
        size: 100,
        enableSorting: false,
      },
    ],
    [defOptions],
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

  const wfDefForPayload =
    fixedDefinitionId ||
    (scopeDefinitionId && scopeDefinitionId !== '__all' ? scopeDefinitionId : undefined);

  /** Required for list-query form-field metadata (published schema). */
  const definitionIdForFilters = wfDefForPayload;

  useEffect(() => {
    if (!fixedDefinitionId && scopeDefinitionId === '__all') {
      setAdvancedFilter(null);
    }
  }, [fixedDefinitionId, scopeDefinitionId]);

  return (
    <div className="space-y-3">
      {formTitle ? (
        <p className="text-sm text-muted-foreground">
          Form: <span className="font-medium text-foreground">{formTitle}</span>
        </p>
      ) : null}
      <DataGrid
        table={table}
        recordCount={data?.pagination.total ?? 0}
        isLoading={isLoading}
        onRowClick={(row) => router.push(`/workflow-forms-management/submissions/${row.id}`)}
        tableLayout={{ columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              {fixedDefinitionId ? null : (
                <Select
                  value={scopeDefinitionId || '__all'}
                  onValueChange={(v) => setScopeDefinitionId(v === '__all' ? '__all' : v)}
                >
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="All forms" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">All forms</SelectItem>
                    {defOptions.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search form, code, state…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-56 max-w-full"
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
                        title="Quick filter — state code"
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
                          <Label htmlFor="wf-sub-state" className="text-xs">
                            State code (exact)
                          </Label>
                          <Input
                            id="wf-sub-state"
                            placeholder="e.g. submitted"
                            value={quickStateCode}
                            onChange={(e) => setQuickStateCode(e.target.value)}
                          />
                        </div>
                      </div>
                    </PopoverContent>
                  </Popover>
                </>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {listQueryToolsEnabled ? (
                <>
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
              <DataGridColumnVisibility
                table={table}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1">
                    <Columns3 className="size-4" />
                    Columns
                  </Button>
                }
              />
              {canAdd ? (
                <Button size="sm" asChild>
                  <Link
                    href={
                      fixedDefinitionId
                        ? `/workflow-forms-management/forms/${fixedDefinitionId}/new`
                        : '/workflow-forms-management/submissions/new'
                    }
                  >
                    <Plus className="size-4 mr-1" />
                    New submission
                  </Link>
                </Button>
              ) : null}
            </div>
        </CardHeader>
          {!listQueryToolsEnabled ? (
            <div className="px-5 pb-2 text-sm text-muted-foreground">
              Install the Workflow Forms module to enable advanced filters and export.
            </div>
          ) : null}
          {isError ? (
            <div className="px-5 pb-2 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load submissions'}
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
              resourceKey="workflow_form_submissions"
              open={filterDialogOpen}
              onOpenChange={setFilterDialogOpen}
              initialFilter={advancedFilter}
              onApply={setAdvancedFilter}
              workflowDefinitionId={definitionIdForFilters}
            />
            <ListQueryExportDialog
              resourceKey="workflow_form_submissions"
              open={exportDialogOpen}
              onOpenChange={setExportDialogOpen}
              filename="workflow_form_submissions.xlsx"
              workflowDefinitionId={definitionIdForFilters}
              getPayload={() => ({
                filter: advancedFilter ?? undefined,
                quick_search: searchQuery || undefined,
                workflow_form_definition_id: wfDefForPayload,
                workflow_submission_state_code: quickStateCode.trim() || undefined,
              })}
            />
          </>
        ) : null}
      </DataGrid>
    </div>
  );
}
