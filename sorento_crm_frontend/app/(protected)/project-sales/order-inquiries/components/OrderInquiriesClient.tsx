'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Download, Search, X } from 'lucide-react';
import { toast } from 'sonner';
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
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import { OrderInquiryStatePill } from '../../_shared/components/OrderInquiryVerbPill';
import {
  useOrderInquiryWorklist,
  useOrderInquiryWorklistSummary,
} from '../../_shared/hooks/useOrderInquiry';
import {
  deliveryMonthLabel,
  formatInquiryQty,
  orderInquiryRowHref,
} from '../../_shared/lib/orderInquiryWorklist';
import { saveBlobAs } from '../../_shared/services/fileDownload';
import { downloadOrderInquiryWorklistXlsx } from '../../_shared/services/orderInquiryService';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

const STATE_OPTIONS = [
  { value: 'raised', label: 'Raised' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'cancelled', label: 'Cancelled' },
];

/**
 * Purchasing's own order inquiry, across every project and every adopted sales order.
 *
 * The per-project screen answers "what did this project raise". This one answers "what do
 * I still have to buy", which is a different job with a different owner - and the rows an
 * ADOPTED AutoCount order raises belong to no project at all, so before this page existed
 * they were reachable only from the one sales order that raised them.
 *
 * The shape is the spreadsheet purchasing already works from: their columns, their order,
 * one sheet per delivery MONTH. So the month is the primary control here rather than one
 * filter among many, and the export writes the same workbook back out.
 *
 * Nothing is authored here. A row is derived when CS confirms supply, which is the only
 * moment the instruction is true, so there is no Add button and there never should be.
 */
export function OrderInquiriesClient() {
  const [search, setSearch] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [month, setMonth] = React.useState('');
  const [stateFilter, setStateFilter] = React.useState('');
  const [supplierFilter, setSupplierFilter] = React.useState('');
  const [projectFilter, setProjectFilter] = React.useState('');
  const [raisedDate, setRaisedDate] = React.useState('');
  const [exporting, setExporting] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'delivery_date', desc: false },
  ]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing changes which rows exist, so page 3 of the old set is a page of nothing in
  // the new one.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debounced, month, stateFilter, supplierFilter, projectFilter, raisedDate]);

  const filters = React.useMemo(
    () => ({
      query: debounced || undefined,
      delivery_month: month || undefined,
      raised_date: raisedDate || undefined,
      state: stateFilter || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
    }),
    [debounced, month, raisedDate, stateFilter, supplierFilter, projectFilter],
  );

  const params = React.useMemo(
    () => ({
      ...filters,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      sort: sorting[0]?.id ?? 'delivery_date',
      dir: (sorting[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
    }),
    [filters, pagination, sorting],
  );

  const list = useOrderInquiryWorklist(params);
  const summary = useOrderInquiryWorklistSummary(filters);

  const rows = React.useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.total ?? 0;
  const months = summary.data?.by_month ?? [];
  const filtered = Boolean(
    debounced || month || stateFilter || supplierFilter || projectFilter || raisedDate,
  );

  const columns = React.useMemo<ColumnDef<OrderInquiryWorklistRow>[]>(
    () => [
      {
        accessorKey: 'so_date',
        header: ({ column }) => <DataGridColumnHeader title="SO date" column={column} />,
        size: 120,
        meta: { headerTitle: 'SO date', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.so_date ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.so_date)}
            </span>
          ) : (
            <Muted>No date</Muted>
          ),
      },
      {
        accessorKey: 'so_number',
        header: ({ column }) => <DataGridColumnHeader title="S/O no" column={column} />,
        size: 150,
        meta: { headerTitle: 'S/O no', skeleton: <Skeleton className="h-4 w-20" /> },
        // The way in. An adopted row reaches the CORE sales order and an authored one its
        // project document; a row that can reach neither is plain text rather than a link
        // that answers 404.
        cell: ({ row }) => {
          const reference = row.original.so_number ?? 'Not numbered';
          const href = orderInquiryRowHref(row.original);
          if (!href)
            return (
              <span className="block truncate" title={reference}>
                {reference}
              </span>
            );
          return (
            <Link
              href={href}
              className="block truncate font-medium text-primary hover:underline"
              title={reference}
            >
              {reference}
            </Link>
          );
        },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item code" column={column} />,
        size: 180,
        meta: { headerTitle: 'Item code', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate font-medium" title={row.original.item_code ?? ''}>
              {row.original.item_code || <Muted>Unresolved</Muted>}
            </span>
            {/* Only when it says something the code does not: plenty of products are
                named after their own code, and printing it twice reads as a defect. */}
            {row.original.product_name &&
              row.original.product_name !== row.original.item_code && (
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={row.original.product_name}
                >
                  {row.original.product_name}
                </span>
              )}
          </div>
        ),
      },
      {
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 90,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
        cell: ({ row }) => (
          <span className="tabular-nums">{formatInquiryQty(row.original.qty)}</span>
        ),
      },
      {
        accessorKey: 'delivery_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Delivery date" column={column} />
        ),
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
        accessorKey: 'project_customer',
        header: ({ column }) => (
          <DataGridColumnHeader title="Project / customer" column={column} />
        ),
        size: 260,
        meta: {
          headerTitle: 'Project / customer',
          skeleton: <Skeleton className="h-4 w-40" />,
        },
        cell: ({ row }) =>
          row.original.project_customer ? (
            <span className="block truncate" title={row.original.project_customer}>
              {row.original.project_customer}
            </span>
          ) : (
            <Muted>Not attributed</Muted>
          ),
      },
      {
        accessorKey: 'supplier',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        size: 150,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-20" /> },
        // Blank means nobody has placed it yet, exactly as a blank cell does on their
        // sheet. Never filled in with a guess at who would supply it.
        cell: ({ row }) =>
          row.original.supplier ? (
            <span className="block truncate" title={row.original.supplier}>
              {row.original.supplier}
            </span>
          ) : (
            <Muted>Not placed</Muted>
          ),
      },
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO no" column={column} />,
        size: 150,
        meta: { headerTitle: 'PO no', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.po_number ? (
            <span className="block truncate tabular-nums" title={row.original.po_number}>
              {row.original.po_number}
            </span>
          ) : (
            <Muted>Not placed</Muted>
          ),
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 120,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => (
          <div className="min-w-0 space-y-1">
            <OrderInquiryStatePill state={row.original.state} />
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
        accessorKey: 'raised_at',
        header: ({ column }) => <DataGridColumnHeader title="Raised" column={column} />,
        size: 130,
        meta: { headerTitle: 'Raised', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) =>
          row.original.raised_at ? (
            <span className="whitespace-nowrap">
              {formatDateInMalaysia(row.original.raised_at)}
            </span>
          ) : (
            <Muted>Unknown</Muted>
          ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await downloadOrderInquiryWorklistXlsx(filters);
      saveBlobAs(blob, `order-inquiry-${month || 'all-months'}.xlsx`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to export the order inquiry',
      );
    } finally {
      setExporting(false);
    }
  }

  const filtersActiveCount =
    (stateFilter ? 1 : 0) +
    (supplierFilter ? 1 : 0) +
    (projectFilter ? 1 : 0) +
    (raisedDate ? 1 : 0);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">Order inquiries</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Every project and every adopted sales order, by delivery month.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">
            {`${(summary.data?.total_rows ?? total).toLocaleString()} rows`}
          </Badge>
          <Badge variant="outline">
            {`${formatInquiryQty(summary.data?.total_qty) || '0'} qty`}
          </Badge>
          <Badge variant="warning" appearance="light">
            {`${(summary.data?.by_state.raised ?? 0).toLocaleString()} still to place`}
          </Badge>
        </div>
      </header>

      {/* The month is the primary control, because the sheet this replaces is one tab per
          delivery month and that is the unit purchasing plans in. */}
      <nav
        aria-label="Delivery month"
        className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2"
      >
        <Button
          type="button"
          size="sm"
          variant={month === '' ? 'primary' : 'ghost'}
          onClick={() => setMonth('')}
        >
          All months
        </Button>
        {months.map((entry) => (
          <Button
            key={entry.month}
            type="button"
            size="sm"
            variant={month === entry.month ? 'primary' : 'ghost'}
            onClick={() => setMonth(entry.month)}
          >
            {entry.label ?? deliveryMonthLabel(entry.month) ?? entry.month}
            <span className="ms-1.5 text-xs opacity-70">{entry.rows}</span>
          </Button>
        ))}
        {months.length === 0 && !summary.isLoading && (
          <span className="px-2 text-sm text-muted-foreground">
            No delivery months yet
          </span>
        )}
      </nav>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={list.isLoading}
        listingKey="projects.projects.view::order-inquiry-worklist"
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-semibold">
              {filtered ? 'No rows match' : 'Nothing has been raised yet'}
            </p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {filtered
                ? 'Clear the month and the filters to see everything purchasing has been told to buy.'
                : 'Confirming supply in Fulfilment Planning raises the rows purchasing acts on.'}
            </p>
            {!filtered && (
              <Button asChild variant="outline" className="mt-4">
                <Link href="/project-sales/fulfilment-planning">
                  Open Fulfilment Planning
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
                    placeholder="Search S/O, item, product or customer…"
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
                      <Label className="text-xs text-muted-foreground">State</Label>
                      <SearchableSelect
                        value={stateFilter}
                        onChange={setStateFilter}
                        clearable
                        options={STATE_OPTIONS}
                        placeholder="Every state"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Supplier</Label>
                      <SearchableSelect
                        value={supplierFilter}
                        onChange={setSupplierFilter}
                        clearable
                        options={(summary.data?.suppliers ?? []).map((entry) => ({
                          value: entry.id,
                          label: entry.label,
                        }))}
                        placeholder="Every supplier"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Project</Label>
                      <SearchableSelect
                        value={projectFilter}
                        onChange={setProjectFilter}
                        clearable
                        options={(summary.data?.projects ?? []).map((entry) => ({
                          value: entry.id,
                          label: entry.label,
                        }))}
                        placeholder="Every project"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground" htmlFor="raised-on">
                        Raised on
                      </Label>
                      <Input
                        id="raised-on"
                        type="date"
                        value={raisedDate}
                        onChange={(event) => setRaisedDate(event.target.value)}
                      />
                    </div>
                    {filtersActiveCount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setStateFilter('');
                          setSupplierFilter('');
                          setProjectFilter('');
                          setRaisedDate('');
                        }}
                      >
                        Clear filters
                      </Button>
                    )}
                  </div>
                ),
              }}
              // Their own workbook, with their own headings and a sheet per delivery
              // month, is the file anyone outside the system reads - so the generic
              // selection-scoped export is replaced rather than offered beside it.
              exportConfig={false}
              primaryAction={
                <Button type="button" onClick={() => void handleExport()} disabled={exporting}>
                  <Download className="size-4" aria-hidden />
                  {exporting ? 'Preparing…' : 'Export Excel'}
                </Button>
              }
              onRefresh={() => {
                void list.refetch();
                void summary.refetch();
              }}
              isRefreshing={list.isFetching && !list.isLoading}
            />
          </CardHeader>
          <CardTable>
            {list.isError ? (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
                <h2 className="text-sm font-semibold text-destructive">
                  The order inquiry could not be loaded
                </h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {list.error instanceof Error ? list.error.message : 'Try again shortly.'}
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
