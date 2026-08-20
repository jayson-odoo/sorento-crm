'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { format } from 'date-fns';
import {
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { CalendarDays, Download, List, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useOrderInquiryWorklist,
  useOrderInquiryWorklistSummary,
} from '../../_shared/hooks/useOrderInquiry';
import { deliveryMonthLabel, formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import { saveBlobAs } from '../../_shared/services/fileDownload';
import { downloadOrderInquiryWorklistXlsx } from '../../_shared/services/orderInquiryService';
import { OrderInquiryCalendarView } from './OrderInquiryCalendarView';
import { OrderInquiryDayDrilldown } from './OrderInquiryDayDrilldown';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

const STATE_OPTIONS = [
  { value: 'raised', label: 'Raised' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'cancelled', label: 'Cancelled' },
];

type OrderInquiryView = 'list' | 'calendar';

/** Persisted in the URL as `?view=calendar`. List is the default the page shipped as. */
function viewFrom(value: string | null): OrderInquiryView {
  return value === 'calendar' ? 'calendar' : 'list';
}

/**
 * Purchasing's own order inquiry, across every project and every adopted sales order.
 *
 * The per-project screen answers "what did this project raise". This one answers "what do
 * I still have to buy", which is a different job with a different owner - and the rows an
 * ADOPTED AutoCount order raises belong to no project at all, so before this page existed
 * they were reachable only from the one sales order that raised them.
 *
 * Two ways to read the same worklist (D1, the captain: "instead of putting the months at
 * the top, we should have a calendar view"):
 *   - List: their own spreadsheet's columns, their order, unpaged filters including a
 *     delivery-month select. Everything the page has always been.
 *   - Calendar: a month grid, one cell per delivery day, with the day's row/qty totals
 *     and its biggest items as chips. Clicking a day narrows the SAME list below the grid
 *     to that one day - reusing the list's own columns and the list's own table, rather
 *     than a slide-over with a second column set invented for it.
 * Both views read whatever state/supplier/project/query/raised-date filters are already
 * set; only the List view carries the toolbar that sets them, so there is one filter UI
 * rather than two that could disagree.
 *
 * Nothing is authored here. A row is derived when CS confirms supply, which is the only
 * moment the instruction is true, so there is no Add button and there never should be.
 */
export function OrderInquiriesClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [view, setView] = React.useState<OrderInquiryView>(() =>
    viewFrom(searchParams.get('view')),
  );
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
  // The calendar's own displayed month - independent of the list's `delivery_month`
  // filter, because paging the calendar must not narrow the list underneath it. Defaults
  // to a shared `?delivery_month=` deep link when one is present, else the current month.
  const [calendarMonth, setCalendarMonth] = React.useState(
    () => searchParams.get('delivery_month') || format(new Date(), 'yyyy-MM'),
  );
  const [selectedDay, setSelectedDay] = React.useState<string | null>(null);

  // Only `view` travels in the URL (D1). `replace`, not `push`: switching views is not a
  // place in history to go back to.
  React.useEffect(() => {
    const next = new URLSearchParams(searchParams.toString());
    if (view === 'list') next.delete('view');
    else next.set('view', view);
    const query = next.toString();
    if (query === searchParams.toString()) return;
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [view, pathname, router, searchParams]);

  // A day drawn from a month that is no longer on screen is not a selection anymore.
  React.useEffect(() => {
    setSelectedDay(null);
  }, [calendarMonth]);

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

  const list = useOrderInquiryWorklist(params, { enabled: view === 'list' });
  const summary = useOrderInquiryWorklistSummary(filters);

  // The calendar's own request: the same filters MINUS delivery_month (the calendar names
  // its own range through `month` instead), plus that range.
  const calendarFilters = React.useMemo(
    () => ({
      query: debounced || undefined,
      raised_date: raisedDate || undefined,
      state: stateFilter || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
      month: calendarMonth,
    }),
    [debounced, raisedDate, stateFilter, supplierFilter, projectFilter, calendarMonth],
  );
  const calendarSummary = useOrderInquiryWorklistSummary(calendarFilters, {
    enabled: view === 'calendar',
  });
  const dayDrilldownFilters = React.useMemo(
    () => ({
      query: debounced || undefined,
      raised_date: raisedDate || undefined,
      state: stateFilter || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
    }),
    [debounced, raisedDate, stateFilter, supplierFilter, projectFilter],
  );

  const rows = React.useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.total ?? 0;
  const months = summary.data?.by_month ?? [];
  const filtered = Boolean(
    debounced || month || stateFilter || supplierFilter || projectFilter || raisedDate,
  );

  const columns = useOrderInquiryWorklistColumns();

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
    (month ? 1 : 0) +
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

      {/* List | Calendar (D1): the list reads the spreadsheet's own columns one page at a
          time; the calendar reads the same rows by delivery day, which is the shape
          purchasing actually plans a month in. A toggle, not two pages, because it is the
          same worklist either way. */}
      <div
        className="inline-flex rounded-md border border-input"
        role="group"
        aria-label="Order inquiry view"
      >
        <Button
          type="button"
          size="sm"
          variant={view === 'list' ? 'primary' : 'ghost'}
          className="rounded-e-none"
          aria-pressed={view === 'list'}
          onClick={() => setView('list')}
        >
          <List className="size-4" aria-hidden />
          List
        </Button>
        <Button
          type="button"
          size="sm"
          variant={view === 'calendar' ? 'primary' : 'ghost'}
          className="rounded-s-none border-s border-input"
          aria-pressed={view === 'calendar'}
          onClick={() => setView('calendar')}
        >
          <CalendarDays className="size-4" aria-hidden />
          Calendar
        </Button>
      </div>

      {view === 'calendar' ? (
        <div className="space-y-5">
          <Card className="p-4">
            <OrderInquiryCalendarView
              month={calendarMonth}
              onMonthChange={setCalendarMonth}
              byDay={calendarSummary.data?.by_day ?? []}
              isLoading={calendarSummary.isLoading}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
            />
          </Card>
          {selectedDay && (
            <OrderInquiryDayDrilldown
              day={selectedDay}
              monthFilters={dayDrilldownFilters}
              onClose={() => setSelectedDay(null)}
            />
          )}
        </div>
      ) : (
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
                        <Label className="text-xs text-muted-foreground">
                          Delivery month
                        </Label>
                        <SearchableSelect
                          value={month}
                          onChange={setMonth}
                          clearable
                          options={months.map((entry) => ({
                            value: entry.month,
                            label: `${entry.label ?? deliveryMonthLabel(entry.month) ?? entry.month} (${entry.rows})`,
                          }))}
                          placeholder="Every month"
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
                            setMonth('');
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
      )}
    </div>
  );
}
