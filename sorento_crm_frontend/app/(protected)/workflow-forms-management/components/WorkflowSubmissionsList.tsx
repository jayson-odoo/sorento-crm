'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, Search, SlidersHorizontal, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { useTenantModules } from '@/hooks/useTenantModules';
import { fetchListQueryFields } from '@/lib/list-query/listQueryService';
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
  const pathname = usePathname();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const listQueryToolsEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('workflow_forms');

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [scopeDefinitionId, setScopeDefinitionId] = useState<string>(fixedDefinitionId ?? '__all');
  const [quickStateCode, setQuickStateCode] = useState('');

  const { data: pubDefs } = usePublishedWorkflowDefinitionsForSubmissionQuery();
  const { data, isLoading, isError, error, refetch, isFetching } = useWorkflowSubmissionsGridQuery({
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

  const wfDefForPayload =
    fixedDefinitionId ||
    (scopeDefinitionId && scopeDefinitionId !== '__all' ? scopeDefinitionId : undefined);

  /** Required for list-query form-field metadata (published schema). */
  const definitionIdForFilters = wfDefForPayload;

  const { data: submissionFieldMetas } = useQuery({
    queryKey: ['workflow-submissions-list-fields', definitionIdForFilters],
    queryFn: () =>
      fetchListQueryFields('workflow_form_submissions', {
        definitionId: definitionIdForFilters,
      }),
    enabled: Boolean(definitionIdForFilters),
    staleTime: 60_000,
  });

  const dynamicHeaderFields = useMemo(
    () =>
      (submissionFieldMetas ?? []).filter(
        (f) => f.field_key.startsWith('hdr:') && f.filterable,
      ),
    [submissionFieldMetas],
  );

  const formatHeaderValue = (value: unknown): string => {
    if (value === null || value === undefined || value === '') return '-';
    if (Array.isArray(value)) return value.map((v) => String(v)).join(', ');
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };

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
        meta: { headerTitle: 'Form', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'current_state_code',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => <Badge variant="secondary">{row.original.current_state_code}</Badge>,
        size: 130,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) =>
          row.original.updated_at ? new Date(row.original.updated_at).toLocaleString() : '-',
        size: 180,
        meta: { headerTitle: 'Updated', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      ...dynamicHeaderFields.map<ColumnDef<WorkflowSubmission>>((fieldMeta) => {
        const fieldId = fieldMeta.field_key.slice(4);
        const friendlyHeader = fieldMeta.label.replace(/^Header:\s*/i, '');
        return {
          id: fieldMeta.field_key,
          header: friendlyHeader,
          accessorFn: (row) => row.header_data?.[fieldId],
          cell: ({ getValue }) => (
            <span className="truncate block max-w-[24rem]">
              {formatHeaderValue(getValue())}
            </span>
          ),
          size: 220,
          enableSorting: false,
          meta: {
            headerTitle: friendlyHeader,
            skeleton: <Skeleton className="h-4 w-24" />,
          },
        };
      }),
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
        enableHiding: false,
      },
    ],
    [defOptions, dynamicHeaderFields],
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

  useEffect(() => {
    if (!fixedDefinitionId && scopeDefinitionId === '__all') {
      setAdvancedFilter(null);
    }
  }, [fixedDefinitionId, scopeDefinitionId]);

  const exportPayload = () => ({
    filter: advancedFilter ?? undefined,
    quick_search: searchQuery || undefined,
    workflow_form_definition_id: wfDefForPayload,
    workflow_submission_state_code: quickStateCode.trim() || undefined,
  });

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
        listingKey={wfDefForPayload ? `${pathname}::${wfDefForPayload}` : pathname}
        onRowClick={(row) => router.push(`/workflow-forms-management/submissions/${row.id}`)}
        tableLayout={{ columnsVisibility: true }}
        standardToolbar={false}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="flex flex-wrap items-center gap-2">
                  {fixedDefinitionId ? null : (
                    <SearchableSelect
                      value={scopeDefinitionId || '__all'}
                      onChange={(v) => setScopeDefinitionId(v === '__all' ? '__all' : v)}
                      options={[
                        { value: '__all', label: 'All forms' },
                        ...defOptions.map((d) => ({ value: d.id, label: d.name })),
                      ]}
                      placeholder="All forms"
                      triggerClassName="w-[220px]"
                    />
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
                        aria-label="Clear search"
                      >
                        <X />
                      </Button>
                    ) : null}
                  </div>
                  {listQueryToolsEnabled ? (
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="relative shrink-0"
                          title="Quick filter - state code"
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
                  ) : null}
                </div>
              }
              filters={
                listQueryToolsEnabled
                  ? {
                      kind: 'listQuery',
                      resourceKey: 'workflow_form_submissions',
                      advancedFilter,
                      onApply: setAdvancedFilter,
                      getPayload: exportPayload,
                      workflowDefinitionId: definitionIdForFilters,
                    }
                  : undefined
              }
              exportConfig={
                listQueryToolsEnabled && canExport
                  ? {
                      kind: 'listQuery',
                      resourceKey: 'workflow_form_submissions',
                      filename: 'workflow_form_submissions.xlsx',
                      getPayload: exportPayload,
                      workflowDefinitionId: definitionIdForFilters,
                    }
                  : false
              }
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
              primaryAction={
                canAdd ? (
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
                ) : undefined
              }
            />
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
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>
    </div>
  );
}
