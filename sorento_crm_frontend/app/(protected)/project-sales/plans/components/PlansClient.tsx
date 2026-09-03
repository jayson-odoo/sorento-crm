'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { PackageSearch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { STATUS_PILL_BASE } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { usePlans } from '../../_shared/hooks/useFulfilmentPlanning';
import { planBoardHref, planRowHref } from '../../_shared/lib/fulfilmentPlanningRows';
import { PLAN_SORT_FIELDS, type PlanRow, type PlanState } from '../../_shared/types/fulfilmentPlanning.types';
import { InfoHint } from '../../[projectId]/components/InfoHint';
import { PageHeader } from '@/components/common/PageHeader';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

/** Soft-pastel per state, kept local: `challenged` deserves amber (something moved under a
 * confirmed decision) and `superseded` a neutral slate, neither of which the shared status
 * pill palette carries yet. */
const PLAN_STATE_PILL: Record<PlanState, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  superseded: 'bg-slate-200 text-slate-700',
  challenged: 'bg-amber-100 text-amber-800',
};

const PLAN_STATE_LABEL: Record<PlanState, string> = {
  active: 'Active',
  superseded: 'Superseded',
  challenged: 'Challenged',
};

const STATE_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'superseded', label: 'Superseded' },
  { value: 'challenged', label: 'Challenged' },
];

const SORTABLE_COLUMNS = new Set<string>(PLAN_SORT_FIELDS);

const DEFAULT_SORTING: SortingState = [{ id: 'decided_at', desc: true }];

/**
 * The Plans page (PLAN-demo-followups-19aug-ladder-v2 D1): "is the plan stored, how do I
 * review it" - the captain, after the 19 August demo.
 *
 * Every supply decision, one row per revision, cross-order - what the board's Confirm
 * actually wrote. `state` defaults to Active because the question is "what is committed
 * NOW"; Superseded and Challenged stay a click away in the filter for whoever wants the
 * history behind a revision.
 */
export function PlansClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [planState, setPlanState] = React.useState<PlanState>('active');
  const [agentCode, setAgentCode] = React.useState('');
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debounced,
    isSettling: debouncedSettling,
  } = useDebouncedSearch();
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>(() => {
    const field = searchParams.get('sort');
    if (!field || !SORTABLE_COLUMNS.has(field)) return DEFAULT_SORTING;
    return [{ id: field, desc: searchParams.get('dir') !== 'asc' }];
  });

  React.useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: 0 }));
  }, [debounced, planState, agentCode, sorting]);

  React.useEffect(() => {
    const next = new URLSearchParams(searchParams.toString());
    if (sorting[0]) {
      next.set('sort', sorting[0].id);
      next.set('dir', sorting[0].desc ? 'desc' : 'asc');
    } else {
      next.delete('sort');
      next.delete('dir');
    }
    const query = next.toString();
    if (query === searchParams.toString()) return;
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorting, pathname, router]);

  const plans = usePlans({
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    query: debounced || undefined,
    state: planState,
    agent_code: agentCode.trim() || undefined,
    sort: sorting[0] ? (sorting[0].id as (typeof PLAN_SORT_FIELDS)[number]) : undefined,
    dir: sorting[0] ? (sorting[0].desc ? 'desc' : 'asc') : undefined,
  });

  const rows = React.useMemo(() => plans.data?.data ?? [], [plans.data]);

  const columns = React.useMemo<ColumnDef<PlanRow>[]>(() => {
    const defs: ColumnDef<PlanRow>[] = [
      {
        id: 'so_number',
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) => {
          const reference = row.original.so_number || 'Not linked';
          const href = planRowHref(row.original);
          return href ? (
            <Link
              href={href}
              title={reference}
              className="block truncate font-medium tabular-nums text-primary hover:underline"
            >
              {reference}
            </Link>
          ) : (
            <span className="block truncate font-medium tabular-nums" title={reference}>
              {reference}
            </span>
          );
        },
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Sales order', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) =>
          row.original.customer_name ? (
            <span className="block truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Not recorded</span>
          ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'agent_code',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        cell: ({ row }) =>
          row.original.agent_code ? (
            <span
              className="block truncate tabular-nums"
              title={row.original.agent_label ?? row.original.agent_code}
            >
              {row.original.agent_code}
            </span>
          ) : (
            <span className="text-muted-foreground">Not stated</span>
          ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Agent', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        id: 'revision_no',
        header: ({ column }) => <DataGridColumnHeader title="Revision" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums">{`Rev ${row.original.revision_no}`}</span>
        ),
        size: 90,
        minSize: 80,
        meta: { headerTitle: 'Revision', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => (
          <span
            className={`${STATUS_PILL_BASE} ${PLAN_STATE_PILL[row.original.state]}`}
            title={row.original.challenged_reason ?? ''}
          >
            {PLAN_STATE_LABEL[row.original.state]}
          </span>
        ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-5 w-20 rounded-full" /> },
      },
      {
        id: 'components_summary',
        header: 'Components',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.components_summary ? (
            <span
              className="block truncate"
              title={row.original.components_summary}
            >
              {`${row.original.components_summary} · ${row.original.line_count} line${
                row.original.line_count === 1 ? '' : 's'
              }`}
            </span>
          ) : (
            <span className="text-muted-foreground">{`${row.original.line_count} line${
              row.original.line_count === 1 ? '' : 's'
            }, nothing held`}</span>
          ),
        size: 260,
        minSize: 180,
        meta: { headerTitle: 'Components', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'decided_by_name',
        header: 'Decided by',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.decided_by_name ? (
            <span className="block truncate" title={row.original.decided_by_name}>
              {row.original.decided_by_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Unknown</span>
          ),
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Decided by', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'decided_at',
        header: ({ column }) => <DataGridColumnHeader title="Decided" column={column} />,
        cell: ({ row }) =>
          row.original.decided_at ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.decided_at)}
            </span>
          ) : (
            <span className="text-muted-foreground">Unknown</span>
          ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Decided', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => {
          const href = planRowHref(row.original);
          const boardHref = planBoardHref(row.original);
          if (!href) return <span className="text-sm text-muted-foreground">Not linked</span>;
          return (
            <div className="flex items-center gap-1">
              <Button asChild type="button" size="sm" variant="ghost">
                <Link href={href}>Open</Link>
              </Button>
              {boardHref ? (
                <Button asChild type="button" size="sm" variant="ghost">
                  <Link href={boardHref}>Open on board</Link>
                </Button>
              ) : null}
            </div>
          );
        },
        size: 190,
        minSize: 100,
        enableResizing: false,
        meta: { headerTitle: 'Action', skeleton: <Skeleton className="h-7 w-16" /> },
      },
    ];

    return defs.map((column) => {
      const id = String(column.id);
      if (!SORTABLE_COLUMNS.has(id)) return column;
      return {
        ...column,
        enableSorting: true,
        accessorFn: (row: PlanRow) => (row as unknown as Record<string, unknown>)[id],
      };
    });
  }, []);

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((plans.data?.total ?? 0) / pagination.pageSize) || 0,
    getRowId: (row) => `${row.project_sales_order_id}:${row.revision_no}`,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const filtersActive = (planState !== 'active' ? 1 : 0) + (agentCode.trim() ? 1 : 0);

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2">
            Plans
            <InfoHint label="About plans">
              Every confirmed composition, one row per revision, most recent first.
            </InfoHint>
          </span>
        }
      />

      <DataGrid
        table={table}
        recordCount={plans.data?.total ?? 0}
        isLoading={plans.isLoading}
        isPlaceholderData={plans.isPlaceholderData}
        listingKey="projects.projects.view::project-supply-plans-v1"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={false}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  isSettling={isSearchInFlight(debouncedSettling, plans.isFetching, debounced)}
                  placeholder="Search sales order, customer or agent"
                  className="w-full"
                />
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">State</p>
                      <SearchableSelect
                        value={planState}
                        onChange={(value) => setPlanState(value as PlanState)}
                        options={STATE_OPTIONS}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">Agent code</p>
                      <Input
                        placeholder="e.g. JEREMY"
                        value={agentCode}
                        onChange={(event) => setAgentCode(event.target.value)}
                      />
                    </div>
                  </div>
                ),
              }}
              onRefresh={async () => {
                await plans.refetch();
              }}
              isRefreshing={plans.isFetching}
            />
          </CardHeader>

          <CardTable>
            {plans.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  The plans list could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {plans.error instanceof Error ? plans.error.message : 'Try again in a moment.'}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4"
                  onClick={() => plans.refetch()}
                >
                  Try again
                </Button>
              </div>
            ) : !plans.isLoading && rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
                <h3 className="mt-2 text-sm font-semibold">
                  {planState === 'active' ? 'No plans yet' : `No ${planState} plans`}
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {planState === 'active'
                    ? 'Nothing has been confirmed yet. Plan and confirm a sales order on the board to see it here.'
                    : 'Clear the state filter to see the rest of the plans.'}
                </p>
                <Button asChild variant="outline" className="mt-4">
                  <Link href="/project-sales/fulfilment-planning">Open Fulfilment Planning</Link>
                </Button>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          {(plans.data?.total ?? 0) > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>
    </>
  );
}
