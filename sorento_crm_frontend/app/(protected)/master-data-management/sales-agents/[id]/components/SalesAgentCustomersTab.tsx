'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { UserMinus } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { useDeferredRowAction, useRowPending } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  CUSTOMER_SELECT_PAGE_SIZE,
  searchCustomersSelect,
} from '@/app/(protected)/order-management/customers/services/customerService';
import {
  salesAgentCustomersKey,
  useAssignSalesAgentCustomer,
  useSalesAgentCustomers,
} from '../../hooks/useSalesAgents';
import type { AgentCustomer } from '../../types/salesAgent.types';

/**
 * Sales agent -> Customers tab: the customers this agent handles (`customers.sales_agent_id`),
 * searchable and paged. "Assign customer" moves a customer here from wherever it was; the
 * customer form's own "Sales agent" field writes the same column. Read-only without
 * `master_data.sales_agents.edit`.
 */
export default function SalesAgentCustomersTab({ agentId }: { agentId: string }) {
  const canEdit = useHasPermission('master_data.sales_agents.edit');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'customer_code', desc: false }]);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
  } = useDebouncedSearch();
  useResetPageOnFilterChange(setPagination, [debouncedSearch, sorting]);

  const { data, isLoading, isPlaceholderData, isError, error, isFetching } =
    useSalesAgentCustomers(agentId, {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery: debouncedSearch,
    });
  const assign = useAssignSalesAgentCustomer(agentId);

  // Unassign asks nothing (D7): the row dims and a toast counts down with Cancel. The payload
  // names the agent so the server clears the column only while it still equals it.
  const unassign = useDeferredRowAction({
    actionKey: 'customer.unassign_sales_agent',
    entityType: 'customer',
    verb: 'Unassigning',
    successMessage: 'Customer unassigned',
    invalidateKeys: [salesAgentCustomersKey(agentId), ['contact-customers']],
  });
  const rowPending = useRowPending<AgentCustomer>('customer');

  const rows = useMemo<AgentCustomer[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const columns = useMemo<ColumnDef<AgentCustomer>[]>(() => {
    const base: ColumnDef<AgentCustomer>[] = [
      {
        accessorKey: 'customer_code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.customer_code}>
            {row.original.customer_code}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.customer_name}>
            {row.original.customer_name}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'region',
        header: ({ column }) => <DataGridColumnHeader title="Region" column={column} />,
        cell: ({ row }) =>
          row.original.region ? (
            <span className="truncate" title={row.original.region}>
              {row.original.region}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 150,
        meta: { headerTitle: 'Region', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'market_segment_code',
        header: ({ column }) => <DataGridColumnHeader title="Market segment" column={column} />,
        cell: ({ row }) =>
          row.original.market_segment_code ? (
            <span className="truncate" title={row.original.market_segment_code}>
              {row.original.market_segment_code}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 160,
        meta: { headerTitle: 'Market segment', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'}>
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-14" /> },
      },
    ];
    if (!canEdit) return base;
    return [
      ...base,
      {
        id: 'unassign',
        header: () => <span className="sr-only">Unassign</span>,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              // The row is a link to the customer; this button is not.
              e.preventDefault();
              e.stopPropagation();
              unassign.run({
                id: row.original.id,
                subject: row.original.customer_name,
                payload: { sales_agent_id: agentId },
              });
            }}
          >
            <UserMinus className="size-4" />
            Unassign
          </Button>
        ),
        size: 120,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Unassign', skeleton: <Skeleton className="h-6 w-20" /> },
      },
    ];
  }, [canEdit, unassign.run, agentId]);

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    rowCount: total,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <div className="space-y-3">
      {isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load customers.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        isPlaceholderData={isPlaceholderData}
        listingKey="master_data.sales_agents.view::customers"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        emptyMessage={
          <div className="py-4 text-center">
            <p className="text-sm font-medium text-foreground">No customers assigned</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Assign the customers this agent handles
            </p>
          </div>
        }
        rowHref={(row) => `/order-management/customers/${row.id}`}
        rowPending={rowPending}
      >
        <Card>
          <CardHeader className="block">
            <div className="flex flex-wrap items-center gap-2">
              <ListSearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                isSettling={isSearchInFlight(debouncedSearchSettling, isFetching, debouncedSearch)}
                placeholder="Search code or name..."
                className="w-full sm:w-64"
              />
              {canEdit ? (
                <SearchableSelect
                  value=""
                  onChange={(customerId) => {
                    if (customerId) assign.mutate(customerId);
                  }}
                  fetchOptions={searchCustomersSelect}
                  paginated
                  pageSize={CUSTOMER_SELECT_PAGE_SIZE}
                  clearable
                  placeholder="Assign customer"
                  emptyMessage="No customers match."
                  aria-label="Assign customer"
                  disabled={assign.isPending}
                  className="w-full sm:w-80"
                />
              ) : null}
            </div>
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
