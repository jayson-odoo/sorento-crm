'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  AlertTriangle,
  CheckCheck,
  Download,
  LayoutGrid,
  Link2,
  List,
  PackageSearch,
  Search,
  Undo2,
  Upload,
  Wand2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { selectedRowIds } from '@/components/ui/data-grid-select-column';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia } from '@/lib/helpers';
import { AutoLinkOrderInquiryDialog } from '../../_shared/components/AutoLinkOrderInquiryDialog';
import { UnlinkAllOrderInquiryDialog } from '../../_shared/components/UnlinkAllOrderInquiryDialog';
import {
  useOrderInquiryHandshake,
  useOrderInquiryWorklist,
  useOrderInquiryWorklistSummary,
  useUnplaceAllPreview,
} from '../../_shared/hooks/useOrderInquiry';
import { ACK_LABELS, ACK_STATES } from '../../_shared/lib/orderInquiryAck';
import { OrderInquiryUploadMenu } from './OrderInquiryUploadMenu';
import { facetSegments } from '../../_shared/lib/orderInquiryKinds';
import type { OrderInquiryKind } from '../../_shared/lib/orderInquiryKinds';
import { buildOrderInquiryMatrix } from '../../_shared/lib/orderInquiryMatrix';
import { deliveryMonthLabel, formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import { saveBlobAs } from '../../_shared/services/fileDownload';
import { downloadOrderInquiryWorklistXlsx } from '../../_shared/services/orderInquiryService';
import type {
  OrderInquiryMatrixAxis,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
} from '../../_shared/types/orderInquiry.types';
import { OrderInquiryMatrixCellDrilldown } from './OrderInquiryMatrixCellDrilldown';
import { OrderInquiryScheduleMatrix } from './OrderInquiryScheduleMatrix';
import { OrderInquiryStrip } from './OrderInquiryStrip';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

const STATE_OPTIONS = [
  { value: 'raised', label: 'Raised' },
  { value: 'partly_linked', label: 'Partly linked' },
  { value: 'actioned', label: 'Actioned' },
  { value: 'cancelled', label: 'Cancelled' },
  // Stored as `placed`; read as Linked everywhere (AC-I1).
  { value: 'placed', label: 'Linked' },
];

/**
 * WHERE the row is linked (AC-I5), which is a different question from what state it is
 * in: a buyer asking "what have I still not put on anything" wants `none`, and one
 * chasing shipping orders wants `spo`.
 */
const LINKED_OPTIONS = [
  { value: 'po', label: 'A purchase order' },
  { value: 'spo', label: 'An SPO' },
  { value: 'none', label: 'Nothing yet' },
];

type OrderInquiryView = 'list' | 'schedule';

/** Persisted in the URL as `?view=schedule`. List is the default the page shipped as. */
function viewFrom(value: string | null): OrderInquiryView {
  return value === 'schedule' ? 'schedule' : 'list';
}

/** The vertical axis the captain named, in the order they named it (rework of D1). */
const MATRIX_AXIS_OPTIONS = [
  { value: 'product', label: 'Product' },
  { value: 'sales_order', label: 'Sales order' },
  { value: 'customer', label: 'Customer' },
  { value: 'agent', label: 'Agent' },
];

const MATRIX_AXES: OrderInquiryMatrixAxis[] = ['product', 'sales_order', 'customer', 'agent'];

function matrixAxisFrom(value: string | null): OrderInquiryMatrixAxis {
  return MATRIX_AXES.includes(value as OrderInquiryMatrixAxis)
    ? (value as OrderInquiryMatrixAxis)
    : 'product';
}

const MATRIX_GRANULARITY_OPTIONS = [
  { value: 'day', label: 'By day' },
  { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' },
  { value: 'year', label: 'By year' },
];

const MATRIX_GRANULARITIES: OrderInquiryMatrixGranularity[] = ['day', 'week', 'month', 'year'];

function matrixGranularityFrom(value: string | null): OrderInquiryMatrixGranularity {
  return MATRIX_GRANULARITIES.includes(value as OrderInquiryMatrixGranularity)
    ? (value as OrderInquiryMatrixGranularity)
    : 'week';
}

/**
 * The unpaged fetch the Schedule view groups client-side, the same limit-1000 idiom the
 * old day drilldown used. A delivery-filtered worklist has never approached that many rows
 * in practice; if one ever does, the fix is a real server-side aggregate, not a bigger
 * number here.
 */
const MATRIX_FETCH_LIMIT = 1000;

/** Same slug the backend gates `unplace-all(-preview)` and `mark`/`auto-place` on. */
const ORDER_INQUIRY_ACTION_PERMISSION = 'projects.order_inquiry.action';

/**
 * The handshake's own grant (`PLAN-scm-oi-handshake.md`): Acknowledge, Reject, Link now
 * and the book uploads. CS holds the read and sees the column and the filter; taking an
 * instruction on is purchasing's, and they may not do it for themselves.
 */
const ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION = 'project_sales.order_inquiries.acknowledge';

/** Where the handshake stands (AC-H4), in the four words the column prints. */
const ACK_OPTIONS = ACK_STATES.map((state) => ({
  value: state,
  label: ACK_LABELS[state],
}));

/**
 * Purchasing's own order inquiry, across every project and every adopted sales order.
 *
 * The per-project screen answers "what did this project raise". This one answers "what do
 * I still have to buy", which is a different job with a different owner - and the rows an
 * ADOPTED AutoCount order raises belong to no project at all, so before this page existed
 * they were reachable only from the one sales order that raised them.
 *
 * Two ways to read the same worklist (D1, reworked - the captain: "vertically I can see by
 * product, by sales order, by customer, by agent etc, then horizontally is the dates, then
 * of course I can view by date, by month, by year"):
 * - List: their own spreadsheet's columns, their order, unpaged filters including a
 *     delivery-month select. Everything the page has always been.
 * - Schedule: a 2D matrix like the fulfilment planning board's - rows by product, sales
 *     order, customer or agent, columns by day, week, month or year, built entirely off
 *     the same filtered worklist rows the list already fetches (one request, grouped in
 *     the browser). Clicking a cell narrows the SAME columns below it to that cell's own
 *     rows - reusing the list's own columns rather than a second set invented for it.
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
  const canActOnOrderInquiry = useHasPermission(ORDER_INQUIRY_ACTION_PERMISSION);
  const canAcknowledge = useHasPermission(ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION);
  const { acknowledge, linkNow } = useOrderInquiryHandshake();

  const [view, setView] = React.useState<OrderInquiryView>(() =>
    viewFrom(searchParams.get('view')),
  );
  // Sourced from `?query=` on mount (captain: the demand drill's click-through -
  // `orderInquiryWorklistHref` - lands here with an SO number already in the URL), and
  // kept URL-synced the same way as `view`/`rows`/`granularity` below, so a link to a
  // filtered worklist is shareable. `debounced` starts at the same value as `search` so
  // the deep link filters on first render rather than after a 300ms flash of "every row".
  const [search, setSearch] = React.useState(() => searchParams.get('query') ?? '');
  const [debounced, setDebounced] = React.useState(() => searchParams.get('query') ?? '');
  const [month, setMonth] = React.useState('');
  const [stateFilter, setStateFilter] = React.useState('');
  const [supplierFilter, setSupplierFilter] = React.useState('');
  const [projectFilter, setProjectFilter] = React.useState('');
  const [raisedDate, setRaisedDate] = React.useState('');
  const [raisedByFilter, setRaisedByFilter] = React.useState('');
  const [linkedFilter, setLinkedFilter] = React.useState('');
  // Sourced from `?ack=` on mount and kept URL-synced, like `view` and `query`: the plan
  // page's "N awaiting acknowledgement" chip links straight into this list narrowed to
  // them, and a chip that landed on an unfiltered list would leave the buyer to find them.
  const [ackFilter, setAckFilter] = React.useState(() => searchParams.get('ack') ?? '');
  // Which rows are ticked for the bulk Acknowledge (AC-H2). react-table's own selection
  // state through `buildSelectColumn`, never a hand-rolled Set: the canonical toolbar
  // reads exactly this for its bulk strip.
  const [rowSelection, setRowSelection] = React.useState<Record<string, boolean>>({});
  // The last upload this page queued, so the completion state can offer Link now and the
  // purchase orders it just wrote (AC-H13). Null until somebody uploads a book here.
  const [uploaded, setUploaded] = React.useState(false);
  // Which card is pressed (AC-I11). Not one of the toolbar's filters: it lives on the
  // strip above BOTH views, so the same press narrows the matrix and the list. It IS
  // sent with the summary's own request all the same - only the `kinds` facet inside it
  // drops the card, server-side, which is what keeps the other two cards readable while
  // one is held down (see `listFilters` below).
  const [kindFilter, setKindFilter] = React.useState<OrderInquiryKind | null>(null);
  const [exporting, setExporting] = React.useState(false);
  const [autoPlacing, setAutoPlacing] = React.useState(false);
  const [unplacingAll, setUnplacingAll] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'delivery_date', desc: false },
  ]);
  const [matrixAxis, setMatrixAxis] = React.useState<OrderInquiryMatrixAxis>(() =>
    matrixAxisFrom(searchParams.get('rows')),
  );
  const [matrixGranularity, setMatrixGranularity] = React.useState<OrderInquiryMatrixGranularity>(
    () => matrixGranularityFrom(searchParams.get('granularity')),
  );
  const [openCell, setOpenCell] = React.useState<OrderInquiryMatrixCell | null>(null);

  // `view`, `rows`, `granularity` and `query` travel in the URL, so a link to the Schedule
  // view or a filtered search is shareable. `replace`, not `push`: turning a dial (or
  // typing a search) is not a place in history to go back to.
  React.useEffect(() => {
    const next = new URLSearchParams(searchParams.toString());
    if (view === 'list') next.delete('view');
    else next.set('view', view);
    if (matrixAxis === 'product') next.delete('rows');
    else next.set('rows', matrixAxis);
    if (matrixGranularity === 'week') next.delete('granularity');
    else next.set('granularity', matrixGranularity);
    if (debounced) next.set('query', debounced);
    else next.delete('query');
    if (ackFilter) next.set('ack', ackFilter);
    else next.delete('ack');
    const nextQuery = next.toString();
    if (nextQuery === searchParams.toString()) return;
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }, [
    view,
    matrixAxis,
    matrixGranularity,
    debounced,
    ackFilter,
    pathname,
    router,
    searchParams,
  ]);

  // A cell drawn from one axis/granularity is not a selection under a different one.
  React.useEffect(() => {
    setOpenCell(null);
  }, [matrixAxis, matrixGranularity]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing changes which rows exist, so page 3 of the old set is a page of nothing in
  // the new one.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [
    debounced,
    month,
    stateFilter,
    supplierFilter,
    projectFilter,
    raisedDate,
    raisedByFilter,
    linkedFilter,
    ackFilter,
    kindFilter,
  ]);

  const filters = React.useMemo(
    () => ({
      query: debounced || undefined,
      delivery_month: month || undefined,
      raised_date: raisedDate || undefined,
      state: stateFilter || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
      raised_by: raisedByFilter || undefined,
      linked: (linkedFilter || undefined) as 'po' | 'spo' | 'none' | undefined,
      ack: (ackFilter || undefined) as
        | 'awaiting'
        | 'acknowledged'
        | 'changed'
        | 'rejected'
        | undefined,
    }),
    [
      debounced,
      month,
      raisedDate,
      stateFilter,
      supplierFilter,
      projectFilter,
      raisedByFilter,
      linkedFilter,
      ackFilter,
    ],
  );

  // Everything the screen reads honours whichever card is pressed - the rows, the
  // totals, the export. Only the `kinds` facet inside the summary drops it, and it does
  // that server-side, the same rule the month, supplier, project and raised-by controls
  // are computed by: a control that empties itself the moment you use it cannot be used
  // a second time.
  const listFilters = React.useMemo(
    () => ({ ...filters, kind: kindFilter ?? undefined }),
    [filters, kindFilter],
  );

  // "Unplace all"'s own scope (the captain, 20-21 Aug): the SAME filters as `filters`,
  // minus `state` - the action is always about placed rows, whatever else is filtered,
  // so a State=raised selection must not zero its own scope out.
  const unplaceAllFilters = React.useMemo(
    () => ({
      query: debounced || undefined,
      delivery_month: month || undefined,
      raised_date: raisedDate || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
      raised_by: raisedByFilter || undefined,
    }),
    [debounced, month, raisedDate, supplierFilter, projectFilter, raisedByFilter],
  );

  const params = React.useMemo(
    () => ({
      ...listFilters,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      sort: sorting[0]?.id ?? 'delivery_date',
      dir: (sorting[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
    }),
    [listFilters, pagination, sorting],
  );

  const list = useOrderInquiryWorklist(params, { enabled: view === 'list' });
  // Asked WITH the pressed card, so the header badges and the month / supplier / project
  // controls describe the rows actually on screen. Its `kinds` facet is the one thing
  // computed with the card dropped (server-side), which is what keeps the other two
  // cards readable while one is held down.
  const summary = useOrderInquiryWorklistSummary(listFilters);

  // The Schedule view's own request: the same filters, unpaged, so the matrix groups
  // exactly what the list would otherwise page through.
  const matrixParams = React.useMemo(
    () => ({
      ...listFilters,
      limit: MATRIX_FETCH_LIMIT,
      sort: 'delivery_date',
      dir: 'asc' as const,
    }),
    [listFilters],
  );
  const matrixList = useOrderInquiryWorklist(matrixParams, { enabled: view === 'schedule' });
  const matrix = React.useMemo(
    () => buildOrderInquiryMatrix(matrixList.data?.data ?? [], matrixAxis, matrixGranularity),
    [matrixList.data, matrixAxis, matrixGranularity],
  );

  const rows = React.useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.total ?? 0;
  const months = summary.data?.by_month ?? [];
  const filtered = Boolean(
    debounced ||
      month ||
      stateFilter ||
      supplierFilter ||
      projectFilter ||
      raisedDate ||
      raisedByFilter ||
      linkedFilter ||
      ackFilter ||
      kindFilter,
  );

  // S2/S3 (code review, 20 Aug 2026): what the confirm dialog names as the scope. `state`
  // is never one of these - `unplaceAllFilters` above always drops it, so the dialog must
  // never claim "the current view" (which DOES include State) as its scope; it says
  // exactly the filters that narrowed it, or "every placed row" when none did. Supplier/
  // project resolve through the SAME lists the filter selects already render, so this
  // never puts a raw id on screen.
  const activeUnplaceScopeLabels = React.useMemo(() => {
    const parts: string[] = [];
    if (debounced) parts.push(`matching "${debounced}"`);
    if (month) parts.push(`for delivery ${deliveryMonthLabel(month) ?? month}`);
    if (raisedDate) parts.push(`raised on ${formatDateInMalaysia(raisedDate)}`);
    if (supplierFilter) {
      const supplier = (summary.data?.suppliers ?? []).find((s) => s.id === supplierFilter);
      if (supplier) parts.push(`from ${supplier.label}`);
    }
    if (projectFilter) {
      const project = (summary.data?.projects ?? []).find((p) => p.id === projectFilter);
      if (project) parts.push(`for ${project.label}`);
    }
    if (raisedByFilter) {
      const person = (summary.data?.raised_by ?? []).find((p) => p.id === raisedByFilter);
      if (person) parts.push(`raised by ${person.label}`);
    }
    return parts;
  }, [
    debounced,
    month,
    raisedDate,
    supplierFilter,
    projectFilter,
    raisedByFilter,
    summary.data,
  ]);

  // "Unplace all" (the captain, 20-21 Aug) operates on the CURRENT worklist scope - one
  // product when the filters happen to narrow to it, every placed row when they name
  // nothing. The count comes from the server, resolved against the full matching set
  // (never just the loaded page - the worklist paginates server-side), so it is right
  // whether the scope is a single product or the whole company.
  //
  // Gated on `canActOnOrderInquiry` (N1, code review, 20 Aug 2026): the preview route is
  // ACTION-gated on the backend (it previews a write, not a browse), so a view-only
  // principal 403'd it, `count` fell back to 0, and the disabled tooltip lied - "No placed
  // rows to unplace" on a company that may hold hundreds. Held off entirely rather than
  // fired-and-403'd for a person who could never press the button anyway.
  const unplacePreview = useUnplaceAllPreview(unplaceAllFilters, {
    enabled: view === 'list' && canActOnOrderInquiry,
  });
  const unplaceCount = unplacePreview.data?.count ?? 0;

  const columns = useOrderInquiryWorklistColumns({
    selectable: canAcknowledge,
    canAcknowledge,
  });

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: canAcknowledge,
    onRowSelectionChange: setRowSelection,
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
      const blob = await downloadOrderInquiryWorklistXlsx(listFilters);
      saveBlobAs(blob, `order-inquiry-${month || 'all-months'}.xlsx`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to export the order inquiry',
      );
    } finally {
      setExporting(false);
    }
  }

  // A pressed CARD counts as a filter here even though it lives on the strip rather than
  // in this popover: it narrows exactly what the rest of these narrow, so leaving it out
  // hid "Clear filters" from the one person who most needs it - somebody who pressed Buy,
  // sees three rows, and has nothing on the toolbar offering to give the rest back.
  const filtersActiveCount =
    (month ? 1 : 0) +
    (stateFilter ? 1 : 0) +
    (supplierFilter ? 1 : 0) +
    (projectFilter ? 1 : 0) +
    (raisedDate ? 1 : 0) +
    (raisedByFilter ? 1 : 0) +
    (linkedFilter ? 1 : 0) +
    (ackFilter ? 1 : 0) +
    (kindFilter ? 1 : 0);

  const openCellRow = openCell
    ? matrix.rows.find((row) => row.key === openCell.row_key)
    : undefined;
  const openCellBucket = openCell
    ? matrix.buckets.find((bucket) => bucket.key === openCell.bucket_key)
    : undefined;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">Order inquiries</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">
            {`${(summary.data?.total_rows ?? total).toLocaleString()} rows`}
          </Badge>
          <Badge variant="outline">
            {`${formatInquiryQty(summary.data?.total_qty) || '0'} qty`}
          </Badge>
          <Badge variant="warning" appearance="light">
            {`${(summary.data?.by_state.raised ?? 0).toLocaleString()} still to link`}
          </Badge>
        </div>
      </header>

      {/* List | Schedule: the list reads the spreadsheet's own columns one page at a time;
          the schedule reads the same rows as a 2D matrix - by product, sales order,
          customer or agent down the side, by day, week, month or year across the top. A
          toggle, not two pages, because it is the same worklist either way. */}
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
          variant={view === 'schedule' ? 'primary' : 'ghost'}
          className="rounded-s-none border-s border-input"
          aria-pressed={view === 'schedule'}
          onClick={() => setView('schedule')}
        >
          <LayoutGrid className="size-4" aria-hidden />
          Schedule
        </Button>
      </div>

      {/* The three cards, above BOTH views and pressed in both (AC-I11/AC-I14): what the
          rows in view still need, in the same colours the cells and the "Linked to"
          column draw. No legend beside them - each card carries its own swatch and its
          own words, so there is nothing left for a legend to say. */}
      <OrderInquiryStrip
        totals={facetSegments(summary.data?.kinds)}
        active={kindFilter}
        onToggle={(kind) => setKindFilter((current) => (current === kind ? null : kind))}
      />

      {/* An upload this page queued has landed on the worker (AC-H13). Two next steps and
          no third: link what the new documents can now cover, or go and look at the
          purchase orders that arrived. Dismissed by acting, never by a timer. */}
      {uploaded && canAcknowledge ? (
        <Alert appearance="light">
          <AlertIcon>
            <Upload />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>The book is being read</AlertTitle>
            <AlertDescription>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={linkNow.isPending}
                  onClick={() =>
                    linkNow.mutate({}, { onSuccess: () => setUploaded(false) })
                  }
                >
                  <Link2 className="size-4" aria-hidden />
                  {linkNow.isPending ? 'Linking…' : 'Link now'}
                </Button>
                <Button asChild size="sm" variant="outline">
                  <Link href="/scm/purchase-orders">Open purchase orders</Link>
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setUploaded(false)}
                >
                  Dismiss
                </Button>
              </div>
            </AlertDescription>
          </AlertContent>
        </Alert>
      ) : null}

      {view === 'schedule' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="matrix-rows" className="text-sm text-muted-foreground">
                Rows
              </Label>
              <div className="w-44">
                <SearchableSelect
                  id="matrix-rows"
                  value={matrixAxis}
                  onChange={(value) => setMatrixAxis(value as OrderInquiryMatrixAxis)}
                  options={MATRIX_AXIS_OPTIONS}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="matrix-granularity" className="text-sm text-muted-foreground">
                By
              </Label>
              <div className="w-40">
                <SearchableSelect
                  id="matrix-granularity"
                  value={matrixGranularity}
                  onChange={(value) =>
                    setMatrixGranularity(value as OrderInquiryMatrixGranularity)
                  }
                  options={MATRIX_GRANULARITY_OPTIONS}
                />
              </div>
            </div>
          </div>

          {matrixList.isError ? (
            <Alert variant="destructive" appearance="light">
              <AlertIcon>
                <AlertTriangle />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>The schedule could not be loaded</AlertTitle>
                <AlertDescription>
                  {matrixList.error instanceof Error
                    ? matrixList.error.message
                    : 'Try again in a moment.'}
                </AlertDescription>
              </AlertContent>
            </Alert>
          ) : matrixList.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-72 w-full" />
            </div>
          ) : matrix.rows.length === 0 ? (
            <Card>
              <CardContent className="px-6 py-10 text-center">
                <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
                <h3 className="mt-2 text-sm font-semibold">No inquiries in this view</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {filtered
                    ? 'Clear the month and the filters to see everything purchasing has been told to buy.'
                    : 'Confirming supply in Fulfilment Planning raises the rows purchasing acts on.'}
                </p>
              </CardContent>
            </Card>
          ) : (
            <OrderInquiryScheduleMatrix
              buckets={matrix.buckets}
              rows={matrix.rows}
              rowHeader={
                MATRIX_AXIS_OPTIONS.find((option) => option.value === matrixAxis)?.label ??
                'Product'
              }
              cells={matrix.cells}
              onOpenCell={setOpenCell}
            />
          )}

          {openCell && (
            <OrderInquiryMatrixCellDrilldown
              cell={openCell}
              rowLabel={openCellRow?.label ?? ''}
              bucketLabel={openCellBucket?.label ?? ''}
              onClose={() => setOpenCell(null)}
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
                      placeholder="Search S/O, item, product, customer or CS name…"
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
                        <Label className="text-xs text-muted-foreground">Linked</Label>
                        <SearchableSelect
                          value={linkedFilter}
                          onChange={setLinkedFilter}
                          clearable
                          options={LINKED_OPTIONS}
                          placeholder="Anywhere"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">
                          Acknowledgement
                        </Label>
                        <SearchableSelect
                          value={ackFilter}
                          onChange={setAckFilter}
                          clearable
                          options={ACK_OPTIONS.map((option) => {
                            const count = summary.data?.ack?.[
                              option.value as keyof NonNullable<typeof summary.data.ack>
                            ];
                            return {
                              value: option.value,
                              label:
                                count === undefined
                                  ? option.label
                                  : `${option.label} (${count})`,
                            };
                          })}
                          placeholder="Any"
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
                        <Label className="text-xs text-muted-foreground">Raised by</Label>
                        <SearchableSelect
                          value={raisedByFilter}
                          onChange={setRaisedByFilter}
                          clearable
                          options={(summary.data?.raised_by ?? []).map((entry) => ({
                            value: entry.id,
                            label: entry.label,
                          }))}
                          placeholder="Everyone"
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
                            setRaisedByFilter('');
                            setLinkedFilter('');
                            setAckFilter('');
                            // Counted above, so it is cleared here: "Clear filters" that
                            // left a card pressed would leave the screen still narrowed.
                            setKindFilter(null);
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
                // The press purchasing works this page with (AC-H2): tick the rows,
                // take them on, and whatever open document can cover them is linked at
                // that moment. Count-bearing, because a bulk action that does not say how
                // many it is about is one nobody presses twice.
                bulkActions={
                  canAcknowledge
                    ? [
                        {
                          key: 'acknowledge',
                          label: `Acknowledge (${selectedRowIds(table).length})`,
                          icon: CheckCheck,
                          disabled: acknowledge.isPending,
                          onClick: () =>
                            acknowledge.mutate(selectedRowIds(table), {
                              onSuccess: () => setRowSelection({}),
                            }),
                        },
                      ]
                    : []
                }
                secondaryActions={[
                  {
                    key: 'auto-place',
                    label: 'Auto-link',
                    icon: Wand2,
                    onClick: () => setAutoPlacing(true),
                  },
                  {
                    key: 'unplace-all',
                    label: 'Unlink all',
                    icon: Undo2,
                    onClick: () => setUnplacingAll(true),
                    // N1: a lacking action grant, or the preview call failing for any
                    // other reason, must never read the same as "genuinely nothing to
                    // unplace" - each says its own thing.
                    disabled:
                      !canActOnOrderInquiry || unplacePreview.isError || unplaceCount === 0,
                    disabledReason: !canActOnOrderInquiry
                      ? "You don't have permission to unlink rows"
                      : unplacePreview.isError
                        ? 'Could not check linked rows - try again'
                        : unplaceCount === 0
                          ? 'No linked rows to unlink'
                          : undefined,
                  },
                ]}
                primaryAction={
                  <div className="flex items-center gap-2">
                    {/* The books purchasing works from, uploaded from THEIR page (AC-H12):
                        the same two dialogs and the same worker jobs as the reorder and
                        purchase-order pages, so nothing is a second importer. */}
                    {canAcknowledge ? (
                      <OrderInquiryUploadMenu onQueued={() => setUploaded(true)} />
                    ) : null}
                    <Button type="button" onClick={() => void handleExport()} disabled={exporting}>
                      <Download className="size-4" aria-hidden />
                      {exporting ? 'Preparing…' : 'Export Excel'}
                    </Button>
                  </div>
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

      <AutoLinkOrderInquiryDialog open={autoPlacing} onOpenChange={setAutoPlacing} />
      <UnlinkAllOrderInquiryDialog
        open={unplacingAll}
        onOpenChange={setUnplacingAll}
        filters={unplaceAllFilters}
        count={unplaceCount}
        productCode={unplacePreview.data?.product_code}
        scopeLabels={activeUnplaceScopeLabels}
      />
    </div>
  );
}
