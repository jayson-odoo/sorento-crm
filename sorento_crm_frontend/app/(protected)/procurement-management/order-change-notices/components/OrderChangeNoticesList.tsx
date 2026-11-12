'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { useHasPermission } from '@/hooks/usePermissions';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { ocnStatusPillKey, ocnStatusWord, type OcnRow } from '@/types/orderChangeNotice';
import { useChangeTypesQuery, useOrderChangeNoticesQuery } from '../hooks/useOrderChangeNotices';
import { OCN_BASE_PATH, OCN_CREATE } from '../constants';


const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'resubmitted', label: 'Appealed' },
  // The word the rows show for a submitted notice waiting on its approver (the backend maps it).
  { value: 'pending_approval', label: 'Pending approval' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'processed_by_cs', label: 'Done' },
  { value: 'voided', label: 'Voided' },
];

const RISK_OPTIONS = ['Low', 'High', 'Highest'].map((v) => ({ value: v, label: v }));

function TextCell({ value }: { value?: string | null }) {
  return (
    <span className="block truncate" title={value ?? undefined}>
      {value || '-'}
    </span>
  );
}

export default function OrderChangeNoticesList() {
  const router = useRouter();
  const canCreate = useHasPermission(OCN_CREATE);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
    setStatusFilter(joinMulti(splitMulti(state.filters.status)));
    setTypeFilter(joinMulti(splitMulti(state.filters.change_type_id)));
    setRiskFilter(joinMulti(splitMulti(state.filters.risk_level)));
  });

  const { data: changeTypes = [] } = useChangeTypesQuery();

  const status = statusFilter || undefined;
  const changeTypeId = typeFilter || undefined;
  const riskLevel = riskFilter || undefined;
  const { data, isLoading, isPlaceholderData, refetch, isFetching, error } =
    useOrderChangeNoticesQuery({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      status,
      changeTypeId,
      riskLevel,
    });

  useResetPageOnFilterChange(setPagination, [statusFilter, typeFilter, riskFilter, searchQuery]);

  const rowHref = useCallback((row: OcnRow) => {
    const search = buildDetailSearch(
      { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
      { status, change_type_id: changeTypeId, risk_level: riskLevel },
    );
    return `${OCN_BASE_PATH}/${row.id}${search ? `?${search}` : ''}`;
  }, [pagination.pageIndex, pagination.pageSize, sorting, searchQuery, status, changeTypeId, riskLevel]);

  const columns = useMemo<ColumnDef<OcnRow>[]>(
    () => [
      {
        id: 'ocn_number',
        accessorKey: 'ocn_number',
        header: ({ column }) => <DataGridColumnHeader title="OCN no." column={column} />,
        size: 130,
        // The number is the record's link too, so it opens like any link (new tab included).
        cell: ({ row }) => (
          <Link
            href={rowHref(row.original)}
            className="block truncate font-medium tabular-nums hover:underline"
            title={row.original.ocn_number}
          >
            {row.original.ocn_number}
          </Link>
        ),
        meta: { headerTitle: 'OCN no.', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'ocn_date',
        accessorKey: 'ocn_date',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        size: 110,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.ocn_date ? formatDateInMalaysia(row.original.ocn_date) : '-'}
          </span>
        ),
        meta: { headerTitle: 'Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'customer_name',
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        size: 200,
        cell: ({ row }) => <TextCell value={row.original.customer_name} />,
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'customer_po_no',
        accessorKey: 'customer_po_no',
        header: ({ column }) => <DataGridColumnHeader title="Customer PO no." column={column} />,
        size: 160,
        cell: ({ row }) => <TextCell value={row.original.customer_po_no} />,
        meta: { headerTitle: 'Customer PO no.', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'change_type_name',
        accessorKey: 'change_type_name',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 130,
        cell: ({ row }) => <TextCell value={row.original.change_type_name} />,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'risk_level',
        accessorKey: 'risk_level',
        header: ({ column }) => <DataGridColumnHeader title="Risk" column={column} />,
        size: 100,
        cell: ({ row }) => <TextCell value={row.original.risk_level} />,
        meta: { headerTitle: 'Risk', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'project_title',
        accessorKey: 'project_title',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        size: 220,
        cell: ({ row }) => <TextCell value={row.original.project_title} />,
        meta: { headerTitle: 'Project', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'sales_in_charge_name',
        accessorKey: 'sales_in_charge_name',
        header: ({ column }) => <DataGridColumnHeader title="Sales in charge" column={column} />,
        size: 160,
        cell: ({ row }) => <TextCell value={row.original.sales_in_charge_name} />,
        meta: { headerTitle: 'Sales in charge', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 150,
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(ocnStatusPillKey(row.original))}`}>
            {ocnStatusWord(row.original)}
          </span>
        ),
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-24" /> },
      },
    ],
    [rowHref],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination?.total ?? 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const filtersActiveCount = (statusFilter ? 1 : 0) + (typeFilter ? 1 : 0) + (riskFilter ? 1 : 0);

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination?.total ?? 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      rowHref={rowHref}
      emptyMessage="No order change notices yet."
      standardToolbar={false}
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
                placeholder="Search..."
                className="w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: filtersActiveCount > 0,
              activeCount: filtersActiveCount,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <SearchableMultiSelect
                      value={splitMulti(statusFilter)}
                      onChange={(v) => setStatusFilter(joinMulti(v))}
                      placeholder="All statuses"
                      triggerClassName="mt-1 w-full"
                      options={STATUS_OPTIONS}
                      clearable
                    />
                  </div>
                  <div>
                    <Label>Type</Label>
                    <SearchableMultiSelect
                      value={splitMulti(typeFilter)}
                      onChange={(v) => setTypeFilter(joinMulti(v))}
                      placeholder="All types"
                      triggerClassName="mt-1 w-full"
                      options={changeTypes.map((t) => ({ value: t.id, label: t.name }))}
                      clearable
                    />
                  </div>
                  <div>
                    <Label>Risk</Label>
                    <SearchableMultiSelect
                      value={splitMulti(riskFilter)}
                      onChange={(v) => setRiskFilter(joinMulti(v))}
                      placeholder="All risk levels"
                      triggerClassName="mt-1 w-full"
                      options={RISK_OPTIONS}
                      clearable
                    />
                  </div>
                  {filtersActiveCount > 0 && (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setStatusFilter('');
                          setTypeFilter('');
                          setRiskFilter('');
                        }}
                      >
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'order_change_notices_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              canCreate ? (
                <Button onClick={() => router.push(`${OCN_BASE_PATH}/new`)}>
                  <Plus />
                  Create
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
  );
}
