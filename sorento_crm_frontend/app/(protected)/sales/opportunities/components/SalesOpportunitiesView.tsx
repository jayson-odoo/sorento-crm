'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatCurrency, formatDate } from '@/lib/helpers';
import { useSalesOpportunities } from '../hooks/useSalesOpportunities';
import type { SalesOpportunityListItem } from '../types/salesOpportunity.types';
import SalesOpportunityModal from './SalesOpportunityModal';

/**
 * Sales > Opportunities (UAC S2-12, S2-13; plan 3.4, 3.5, section 16).
 *
 * DataGrid with fixed layout and resizable columns: number, title, customer or prospect,
 * stage `Badge`, amount, close date, Source (Portal/CRM). `rowHref` to the detail page;
 * `Log opportunity` is the header's one primary action, gated on `sales.opportunities.add`.
 */
const SOURCE_LABEL: Record<string, string> = { portal: 'Portal', crm: 'CRM' };

export default function SalesOpportunitiesView() {
  const canAdd = useHasPermission('sales.opportunities.add');
  const [modalOpen, setModalOpen] = useState(false);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();

  const { data, isLoading, isFetching, isPlaceholderData, isError, refetch } = useSalesOpportunities({
    pageIndex: 0,
    pageSize: 50,
    sorting: [],
    searchQuery: debouncedSearch,
  });
  const rows = useMemo<SalesOpportunityListItem[]>(() => data?.data ?? [], [data]);

  const addButton = (
    <Button variant="primary" onClick={() => setModalOpen(true)}>
      <Plus className="size-4" />
      Log opportunity
    </Button>
  );

  const columns = useMemo<ColumnDef<SalesOpportunityListItem>[]>(
    () => [
      {
        accessorKey: 'opportunity_no',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        size: 130,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.opportunity_no}>
            {row.original.opportunity_no}
          </span>
        ),
        meta: { headerTitle: 'Number', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Title" column={column} />,
        size: 220,
        cell: ({ row }) => (
          <a
            href={`/sales/opportunities/${row.original.id}`}
            onClick={(e) => e.stopPropagation()}
            className="block truncate font-medium text-primary hover:underline"
            title={row.original.title}
          >
            {row.original.title}
          </a>
        ),
        meta: { headerTitle: 'Title', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'customer',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        size: 200,
        enableSorting: false,
        cell: ({ row }) => {
          const label = row.original.customer_name ?? row.original.prospect_name ?? '-';
          return (
            <span className="truncate" title={label}>
              {label}
            </span>
          );
        },
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'stage_label',
        header: ({ column }) => <DataGridColumnHeader title="Stage" column={column} />,
        size: 130,
        enableSorting: false,
        cell: ({ row }) => <Badge appearance="light">{row.original.stage_label}</Badge>,
        meta: { headerTitle: 'Stage', skeleton: <Skeleton className="h-5 w-20" /> },
      },
      {
        accessorKey: 'expected_amount',
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        size: 130,
        cell: ({ row }) => formatCurrency(row.original.expected_amount),
        meta: { headerTitle: 'Amount', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'expected_close_date',
        header: ({ column }) => <DataGridColumnHeader title="Close date" column={column} />,
        size: 130,
        cell: ({ row }) => formatDate(row.original.expected_close_date),
        meta: { headerTitle: 'Close date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 100,
        enableSorting: false,
        cell: ({ row }) => SOURCE_LABEL[row.original.source] ?? row.original.source,
        meta: { headerTitle: 'Source', skeleton: <Skeleton className="h-4 w-14" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessage = debouncedSearch ? (
    'No opportunities match this search.'
  ) : (
    <div className="flex w-full flex-col items-center gap-3 py-6">
      <span className="text-sm font-medium">No opportunities yet</span>
      {canAdd ? addButton : null}
    </div>
  );

  return (
    <>
      <Container>
        <PageHeader title="Opportunities" actions={canAdd ? addButton : undefined} />
      </Container>
      <Container>
        <div className="space-y-3">
          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              Failed to load opportunities.{' '}
              <button type="button" className="underline" onClick={() => refetch()}>
                Retry
              </button>
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={rows.length}
            isLoading={isLoading}
            isPlaceholderData={isPlaceholderData}
            listingKey="sales.opportunities.view"
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            emptyMessage={emptyMessage}
            rowHref={(row) => `/sales/opportunities/${row.id}`}
          >
            <Card>
              <CardHeader className="flex flex-wrap items-center gap-3 py-3">
                <ListSearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
                  placeholder="Search opportunities..."
                  className="w-full sm:w-64"
                />
              </CardHeader>
              <CardTable>
                <DataGridTable />
              </CardTable>
            </Card>
          </DataGrid>
        </div>
      </Container>
      <SalesOpportunityModal open={modalOpen} onOpenChange={setModalOpen} />
    </>
  );
}
