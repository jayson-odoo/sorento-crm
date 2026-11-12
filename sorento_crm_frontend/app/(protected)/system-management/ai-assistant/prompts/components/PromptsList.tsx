'use client';

/**
 * The AI assistant prompts list, on the standard DataGrid listing (AI-PROMPTS-STD-VIEWS).
 *
 * Same shape as every other list: `DataGridListToolbar` (search, multi-select filters,
 * columns, export, refresh), server-side sort on every column, pagination, Odoo-style row
 * select, and the whole row opens the prompt with the list state in its URL (Back + pager).
 */

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { RiErrorWarningFill } from '@remixicon/react';
import { useHasPermission } from '@/hooks/usePermissions';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { joinMulti, multiChipLabel, splitMulti } from '@/lib/list-filters/multiValue';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { usePromptList } from '../../hooks/useAIAssistantPrompts';
import { usePromptBlocksStatus } from '../../hooks/usePromptBlocksStatus';
import type { PromptListRow } from '../../services/aiPromptsService';

const VIEW_PERMISSION = 'system.ai_assistant_settings.view';
const DETAIL_PATH = '/system-management/ai-assistant/prompts';

const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'dormant', label: 'Dormant' },
];
const DEFAULT_MODEL = 'default';
const DEFAULT_MODEL_LABEL = 'Default model';

function labelsFor(values: string[], options: { value: string; label: string }[]): string[] {
  return values.map((v) => options.find((o) => o.value === v)?.label ?? v);
}

export function PromptsList() {
  const hasPermission = useHasPermission(VIEW_PERMISSION);
  // Chatbot turn re-architecture (AC-1552): whether `chatbot_domains` / `chatbot_entity_kinds`
  // have moved since the labelled parser version was published. Read-only, never blocks the list.
  const blocksStatus = usePromptBlocksStatus();

  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  // Comma-joined, the shape the URL (Back, pager) carries them in.
  const [statusFilter, setStatusFilter] = useState('');
  const [modelFilter, setModelFilter] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting.length ? state.sorting : [{ id: 'name', desc: false }]);
    resetSearch(state.searchQuery);
    setStatusFilter(state.filters.status ?? '');
    setModelFilter(state.filters.model ?? '');
  });
  useResetPageOnFilterChange(setPagination, [statusFilter, modelFilter, searchQuery]);

  const statusValues = splitMulti(statusFilter);
  const modelValues = splitMulti(modelFilter);

  const { data, isLoading, isFetching, isPlaceholderData, error, refetch } = usePromptList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusValues,
    model: modelValues,
  });

  const modelOptions = useMemo(
    () => [
      { value: DEFAULT_MODEL, label: DEFAULT_MODEL_LABEL },
      ...(data?.model_options ?? []).map((m) => ({ value: m, label: m })),
    ],
    [data?.model_options],
  );

  // Every filter rides in the row's URL, so the detail page's Back and pager rebuild this page.
  const rowHref = (row: PromptListRow) => {
    const extra: Record<string, string> = {};
    if (statusFilter) extra.status = statusFilter;
    if (modelFilter) extra.model = modelFilter;
    const search = buildDetailSearch(
      { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
      Object.keys(extra).length ? extra : undefined,
    );
    return `${DETAIL_PATH}/${encodeURIComponent(row.name)}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<PromptListRow>[]>(
    () => [
      buildSelectColumn<PromptListRow>({ rowLabel: (row) => `Select ${row.original.name}` }),
      {
        id: 'name',
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Prompt" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-mono font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 240,
        meta: { headerTitle: 'Prompt' },
        enableHiding: true,
      },
      {
        id: 'role',
        accessorKey: 'role',
        header: ({ column }) => <DataGridColumnHeader title="Role" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground" title={row.original.role}>
            {row.original.role}
          </span>
        ),
        size: 300,
        meta: { headerTitle: 'Role' },
      },
      {
        id: 'status',
        accessorFn: (r) => (r.active ? 'active' : 'dormant'),
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.active ? (
            <Badge status="active">Active</Badge>
          ) : (
            <Badge variant="warning" appearance="light">
              {row.original.activates_in ? `Dormant (${row.original.activates_in})` : 'Dormant'}
            </Badge>
          ),
        size: 140,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'model',
        accessorKey: 'model',
        header: ({ column }) => <DataGridColumnHeader title="Runs on" column={column} />,
        cell: ({ row }) =>
          row.original.model ? (
            <span className="truncate font-mono text-xs" title={row.original.model}>
              {row.original.model}
            </span>
          ) : (
            <span className="text-muted-foreground">{DEFAULT_MODEL_LABEL}</span>
          ),
        size: 170,
        meta: { headerTitle: 'Runs on' },
      },
      {
        id: 'production_version',
        accessorKey: 'production_version',
        header: ({ column }) => <DataGridColumnHeader title="Production" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.production_version != null ? `v${row.original.production_version}` : '-'}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Production' },
      },
      {
        id: 'latest_version',
        accessorKey: 'latest_version',
        header: ({ column }) => <DataGridColumnHeader title="Latest" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums text-muted-foreground">
            {row.original.latest_version != null ? `v${row.original.latest_version}` : '-'}
          </span>
        ),
        size: 100,
        meta: { headerTitle: 'Latest' },
      },
      {
        id: 'updated_at',
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Last edited" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {row.original.updated_at ? formatDateTimeInMalaysia(row.original.updated_at) : '-'}
          </span>
        ),
        size: 180,
        meta: { headerTitle: 'Last edited' },
      },
      {
        id: 'updated_by_name',
        accessorKey: 'updated_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Edited by" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground" title={row.original.updated_by_name ?? ''}>
            {row.original.updated_by_name ?? '-'}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'Edited by' },
      },
    ],
    [],
  );

  const total = data?.pagination.total ?? 0;
  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  if (!hasPermission) {
    return (
      <div className="rounded-md border p-6 text-sm text-muted-foreground">
        Forbidden - you don&apos;t have permission to view AI assistant prompts.
      </div>
    );
  }

  const activeSummary: { label: string; onClear: () => void }[] = [];
  if (statusValues.length) {
    activeSummary.push({
      label: multiChipLabel('Status', labelsFor(statusValues, STATUS_OPTIONS)),
      onClear: () => setStatusFilter(''),
    });
  }
  if (modelValues.length) {
    activeSummary.push({
      label: multiChipLabel('Runs on', labelsFor(modelValues, modelOptions)),
      onClear: () => setModelFilter(''),
    });
  }

  return (
    <div className="space-y-4">
      {blocksStatus.data?.stale ? (
        <Alert variant="mono" icon="warning" data-testid="domain-block-stale-banner">
          <AlertIcon>
            <RiErrorWarningFill />
          </AlertIcon>
          <AlertTitle>
            Domain block out of date - a Chatbot Domain or Entity kind changed since{' '}
            {blocksStatus.data.published_version != null
              ? `v${blocksStatus.data.published_version}`
              : 'the published version'}{' '}
            went live. Publish a new{' '}
            <Link href={`${DETAIL_PATH}/chatbot_semantic_parser`} className="underline">
              chatbot_semantic_parser
            </Link>{' '}
            version to pick it up.
          </AlertTitle>
        </Alert>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        error={error}
        onRetry={() => void refetch()}
        isPlaceholderData={isPlaceholderData}
        rowHref={rowHref}
        emptyMessage="No prompts match this search and filter."
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                  placeholder="Search prompts..."
                  className="w-64"
                />
              }
              filters={{
                kind: 'custom',
                active: activeSummary.length > 0,
                activeCount: activeSummary.length,
                activeSummary,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label>Status</Label>
                      <SearchableMultiSelect
                        id="prompt-status-filter"
                        value={statusValues}
                        onChange={(v) => setStatusFilter(joinMulti(v))}
                        options={STATUS_OPTIONS}
                        placeholder="All statuses"
                        triggerClassName="mt-1"
                        clearable
                      />
                    </div>
                    <div>
                      <Label>Runs on</Label>
                      <SearchableMultiSelect
                        id="prompt-model-filter"
                        value={modelValues}
                        onChange={(v) => setModelFilter(joinMulti(v))}
                        options={modelOptions}
                        placeholder="All models"
                        triggerClassName="mt-1"
                        clearable
                      />
                    </div>
                    {activeSummary.length ? (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setStatusFilter('');
                            setModelFilter('');
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'ai_assistant_prompts.xlsx' }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
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
    </div>
  );
}
