'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Ban, CheckCheck, Download, RotateCcw, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useOrderInquiryMutations,
  useOrderInquiryRows,
  useOrderInquirySummary,
} from '../../../_shared/hooks/useOrderInquiry';
import { useProject } from '../../../_shared/hooks/useProjects';
import { downloadOrderInquiryXlsx } from '../../../_shared/services/orderInquiryService';
import type { OrderInquiryRow } from '../../../_shared/types/orderInquiry.types';
import { InfoHint } from '../../components/InfoHint';
import {
  BUYING_VERBS,
  OrderInquiryStatePill,
  OrderInquiryVerbPill,
  VERB_LABEL,
} from './OrderInquiryVerbPill';

const VERB_OPTIONS = Object.entries(VERB_LABEL).map(([value, label]) => ({ value, label }));

const STATE_OPTIONS = [
  { value: 'raised', label: 'Raised' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'cancelled', label: 'Cancelled' },
];

/**
 * What purchasing has been told to do on one project (P10, AC-I1 to AC-I7).
 *
 * Rows are not authored here. They are derived when a sales order or an amendment
 * publishes, so there is no Add button and there never should be: an instruction typed
 * by hand is the email this screen exists to replace.
 *
 * Three columns carry the whole slice. The instruction is the verb. The coverage says
 * why an ORDER row was not raised, naming the pre-order or the shipment that covers it.
 * The location is the confirmed allocation, and it is EMPTY when nobody has confirmed
 * one, because a default there would send stock from a place nobody chose.
 */
export function OrderInquiryClient({ projectId }: { projectId: string }) {
  const [search, setSearch] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [verbFilter, setVerbFilter] = React.useState('');
  const [stateFilter, setStateFilter] = React.useState('');
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [exporting, setExporting] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'delivery_date', desc: false },
  ]);

  const project = useProject(projectId);
  const { mark } = useOrderInquiryMutations(projectId);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing the set changes which rows exist, so page 3 of the old set is a page of
  // nothing in the new one. The selection goes with it: acting on a row that scrolled
  // out from under the filter is how the wrong thing gets marked done.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
    setRowSelection({});
  }, [debounced, verbFilter, stateFilter]);

  const params = React.useMemo(
    () => ({
      query: debounced || undefined,
      verb: verbFilter || undefined,
      state: stateFilter || undefined,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      sort: sorting[0]?.id ?? 'delivery_date',
      dir: (sorting[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
    }),
    [debounced, verbFilter, stateFilter, pagination, sorting],
  );

  const inquiry = useOrderInquiryRows(projectId, params);
  const summary = useOrderInquirySummary(projectId);

  const rows = React.useMemo(() => inquiry.data?.data ?? [], [inquiry.data]);
  const total = inquiry.data?.total ?? 0;
  const filtered = Boolean(debounced || verbFilter || stateFilter);
  const stillToBuy = rows.filter(
    (row) => BUYING_VERBS.includes(row.verb) && row.state === 'raised',
  ).length;

  const columns = React.useMemo<ColumnDef<OrderInquiryRow>[]>(
    () => [
      buildSelectColumn<OrderInquiryRow>(),
      {
        accessorKey: 'sales_order_ref',
        header: ({ column }) => <DataGridColumnHeader title="S/O no" column={column} />,
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'S/O no', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => {
          const reference = row.original.sales_order_ref ?? 'Not numbered';
          return (
            <div className="min-w-0">
              <span className="block truncate font-medium" title={reference}>
                {reference}
              </span>
              {row.original.is_amendment && (
                <span className="block truncate text-xs text-muted-foreground">
                  From an amendment
                </span>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        size: 170,
        meta: { headerTitle: 'Item code', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.item_code ?? ''}>
            {row.original.item_code || <Muted>Unresolved</Muted>}
          </span>
        ),
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 100,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => <span className="tabular-nums">{row.original.qty}</span>,
      },
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        size: 140,
        meta: { headerTitle: 'Delivery date', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.delivery_date ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.delivery_date)}
            </span>
          ) : (
            <Muted>No date</Muted>
          ),
      },
      {
        accessorKey: 'stock_location',
        header: ({ column }) => <DataGridColumnHeader title="Stock location" column={column} />,
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Stock location', skeleton: <Skeleton className="h-4 w-20" /> },
        // Empty is the honest answer, not a default (AC-H5).
        cell: ({ row }) =>
          row.original.stock_location ? (
            <span className="block truncate" title={row.original.stock_location}>
              {row.original.stock_location}
            </span>
          ) : (
            <Muted>Not allocated yet</Muted>
          ),
      },
      {
        accessorKey: 'verb',
        header: ({ column }) => <DataGridColumnHeader title="Instruction" column={column} />,
        size: 210,
        meta: { headerTitle: 'Instruction', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <div className="min-w-0 space-y-1">
            <OrderInquiryVerbPill verb={row.original.verb} />
            {row.original.note && (
              <span
                className="block truncate text-xs text-muted-foreground"
                title={row.original.note}
              >
                {row.original.note}
              </span>
            )}
          </div>
        ),
      },
      {
        id: 'coverage',
        accessorFn: (row) => row.covered_by ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Covered by" column={column} />,
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Covered by', skeleton: <Skeleton className="h-4 w-28" /> },
        cell: ({ row }) => {
          const covered = row.original.covered_by;
          if (!covered) {
            return BUYING_VERBS.includes(row.original.verb) ? (
              <Muted>Nothing covers this</Muted>
            ) : (
              <Muted>Not a buying instruction</Muted>
            );
          }
          return (
            <span className="block truncate" title={covered}>
              {covered}
            </span>
          );
        },
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 120,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => <OrderInquiryStatePill state={row.original.state} />,
      },
      {
        id: 'actioned',
        accessorFn: (row) => row.actioned_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Actioned" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Actioned', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => {
          if (!row.original.actioned_at) return <Muted>Not yet</Muted>;
          const who = row.original.actioned_by_name ?? 'Someone';
          const when = formatDateInMalaysia(row.original.actioned_at);
          return (
            <span className="block truncate" title={`${who} on ${when}`}>
              {`${who} on ${when}`}
            </span>
          );
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const selectedIds = table.getSelectedRowModel().rows.map((row) => row.id);

  async function runMark(state: string) {
    if (selectedIds.length === 0) return;
    await mark.mutateAsync({ rowIds: selectedIds, state });
    setRowSelection({});
  }

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await downloadOrderInquiryXlsx(projectId, {
        query: debounced || undefined,
        verb: verbFilter || undefined,
        state: stateFilter || undefined,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `order-inquiry-${project.data?.project_code ?? 'project'}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export the order inquiry');
    } finally {
      setExporting(false);
    }
  }

  const bulkActions: ToolbarAction[] = [
    {
      key: 'actioned',
      label: 'Mark actioned',
      icon: CheckCheck,
      disabled: mark.isPending,
      onClick: () => void runMark('actioned'),
    },
    {
      key: 'cancelled',
      label: 'Cancel rows',
      icon: Ban,
      destructive: true,
      disabled: mark.isPending,
      onClick: () => void runMark('cancelled'),
    },
    {
      key: 'raised',
      label: 'Reopen',
      icon: RotateCcw,
      disabled: mark.isPending,
      onClick: () => void runMark('raised'),
    },
  ];

  const filtersActiveCount = (verbFilter ? 1 : 0) + (stateFilter ? 1 : 0);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex items-center gap-1">
            <h1 className="text-xl font-semibold">Order inquiry</h1>
            <InfoHint label="About the order inquiry">
              <p>
                Rows are derived when a sales order or an amendment publishes. Quantity a
                pre-order or an inbound shipment already covers is netted off first, so no
                row asks purchasing to buy stock that is already on the water.
              </p>
            </InfoHint>
          </div>
          {project.data && (
            <p className="mt-0.5 text-sm text-muted-foreground break-words">
              {project.data.title}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {summary.data && (
            <>
              <Badge variant="outline">{`${summary.data.total.toLocaleString()} rows`}</Badge>
              <Badge variant="outline">{`${summary.data.raised.toLocaleString()} raised`}</Badge>
              <Badge variant="outline">{`${summary.data.actioned.toLocaleString()} actioned`}</Badge>
            </>
          )}
          {stillToBuy > 0 && (
            <Badge variant="warning" appearance="light">
              {`${stillToBuy} still to buy on this page`}
            </Badge>
          )}
        </div>
      </header>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={inquiry.isLoading}
        // Pinned, never the pathname default: the fallback keys column preferences on
        // the current URL, and this route carries a project id, so it would write one
        // preferences row per project.
        listingKey="projects.projects.view::project-order-inquiry"
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-semibold">
              {filtered ? 'No rows match' : 'Nothing has been raised yet'}
            </p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {filtered
                ? 'Clear the filters to see everything raised on this project.'
                : 'Publishing a sales order raises the rows purchasing acts on.'}
            </p>
            {!filtered && (
              <Button asChild variant="outline" className="mt-4">
                <Link href={`/project-sales/${projectId}?tab=sales-orders`}>
                  Go to the sales orders
                </Link>
              </Button>
            )}
          </div>
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative w-full max-w-xs">
                  <Search
                    className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden
                  />
                  <Input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search item code, SPO or S/O…"
                    className="ps-9"
                    aria-label="Search order inquiry rows"
                  />
                  {search && (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearch('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: filtersActiveCount > 0,
                activeCount: filtersActiveCount,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Instruction</Label>
                      <SearchableSelect
                        value={verbFilter}
                        onChange={setVerbFilter}
                        clearable
                        options={VERB_OPTIONS}
                        placeholder="Every instruction"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">State</Label>
                      <SearchableSelect
                        value={stateFilter}
                        onChange={setStateFilter}
                        clearable
                        options={STATE_OPTIONS}
                        placeholder="Every state"
                      />
                    </div>
                    {filtersActiveCount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setVerbFilter('');
                          setStateFilter('');
                        }}
                      >
                        Clear filters
                      </Button>
                    )}
                  </div>
                ),
              }}
              // The client's own spreadsheet, with their own headings, is the export
              // anyone outside the system reads (AC-I5), so the generic
              // selection-scoped one is replaced rather than offered beside it.
              exportConfig={false}
              bulkActions={bulkActions}
              primaryAction={
                <Button type="button" onClick={() => void handleExport()} disabled={exporting}>
                  <Download className="size-4" aria-hidden />
                  {exporting ? 'Preparing…' : 'Export Excel'}
                </Button>
              }
              onRefresh={() => {
                void inquiry.refetch();
                void summary.refetch();
              }}
              isRefreshing={inquiry.isFetching && !inquiry.isLoading}
            />
          </CardHeader>
          <CardTable>
            {inquiry.isError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
                <h2 className="text-sm font-semibold text-destructive">
                  The order inquiry could not be loaded
                </h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {inquiry.error instanceof Error ? inquiry.error.message : 'Try again shortly.'}
                </p>
              </div>
            ) : (
              <ScrollArea>
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}
