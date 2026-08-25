'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { buildDetailSearch } from '@/lib/listNavQuery';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Plus, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatMyrExact } from '@/app/(protected)/project-sales/_shared/lib/money';
import { buildPlanActions } from '../lib/planActions';
import { formatStatusLabel } from '@/lib/status-badge';
import { demandClassBadge } from '../../lib/demandClass';
import {
  SALES_ORDER_STATUS_FILTER_OPTIONS,
  salesOrderPriorityVariant,
  salesOrderStatusLabel,
  salesOrderStatusVariant,
} from '../../lib/salesOrderStatus';
import { useCustomerOptions } from '../../hooks/useScmOptions';
import { useRouter } from 'next/navigation';
import { useCreateSalesOrder, useDeleteSalesOrder, useSalesOrders } from '../../hooks/useSalesOrders';
import { useSalesAgentOptions } from '../hooks/useSalesAgentOptions';
import { fmtDate, fmtInt } from '../../lib/format';
import type { SalesOrder, SalesOrderFormData } from '../../types/scm.types';
import { SalesOrderFormModal } from './SalesOrderFormModal';
// The order book upload lives on Reorder planning - the whole plan is computed from it, so
// it is a planning action there. This list is the other place someone reasonably looks for
// it, so the same dialog (never forked) is reused here too.
import { OutstandingUploadDialog } from '../../reorder/components/OutstandingUploadDialog';
import { runHistoryKey, todayRunKey } from '../../reorder/hooks/useReorderRun';

/**
 * THE sales-order table. One component, two places: the Sales Orders list (`SalesOrdersList`,
 * which is this with no props) and the Sales orders tab on a sales agent's record.
 *
 * Extracted rather than copied. A second, smaller table of the same rows is how one screen
 * comes to word a status differently from the other, or to print a total the first one
 * computes another way - and the reader has no way to tell a deliberate difference from an
 * accidental one. What the agent tab changes is stated as props (see `SalesOrdersGridProps`)
 * and amounts to hiding what that context already answers; the columns, the cell renderers,
 * the toolbar, the row click and the footer are the list's own.
 */

/** Who wrote the order. `Order inquiry` is separate from `Sales order upload` because an
 *  order Joey's sheet created is one CS has never seen, and it decides who may edit it. */
const SOURCE_FILTER_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'inquiry', label: 'Order inquiry' },
  { value: 'upload', label: 'Sales order upload' },
  { value: 'history', label: 'Absorbed history' },
  { value: 'manual', label: 'Manual' },
];

/** How many purchase orders to name in the cell before collapsing the rest into a count. */
const WAITING_ON_LIMIT = 2;

/** Same cap for the inquiry numbers, for the same reason. */
const ORDER_INQUIRY_LIMIT = 2;

/**
 * How many orders may be planned together, matching the board's own bound
 * (`FulfilmentPlanningClient.MAX_BOARD_SELECTION`). The whole book is 862 products across
 * 349 dates, so a board of everything is roughly 300,000 cells and is not a screen. Stated
 * here so the action can say why it is refusing BEFORE the board is opened.
 */
const MAX_PLAN_SELECTION = 50;

/** Who may open the fulfilment planning board. Same gate the board's own page carries. */
const PLAN_PERMISSION = 'projects.projects.view';

const SOURCE_LABELS: Record<string, string> = {
  inquiry: 'Order inquiry',
  // Named after the channel as the toolbar now names it: that upload carries the whole book,
  // outstanding orders and completed ones alike, so calling the source "Outstanding upload"
  // described a scope the file never had.
  upload: 'Sales order upload',
  // 11,006 of the orders in the book were absorbed from a six-year AutoCount export. Calling
  // one "Manual" claims somebody keyed a 2020 order by hand, and it is the same word the
  // detail page uses so the two screens cannot disagree about the same row.
  history: 'Absorbed history',
  manual: 'Manual',
};

/** The planning class - what the classification agents actually resolved, as distinct from
 *  the rarely-stated `order_type_label`. `unclassified` reads `demand_class IS NULL`. */
const DEMAND_CLASS_FILTER_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'project', label: 'Project' },
  { value: 'retail', label: 'Retail' },
  { value: 'unclassified', label: 'Unclassified' },
];

const PRIORITY_FILTER_OPTIONS = [
  { value: '', label: 'All priorities' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'normal', label: 'Normal' },
  { value: 'low', label: 'Low' },
];

/**
 * When an order's lines are due: the earliest date, and the rest behind a "+N".
 *
 * Every distinct date, never a range. An order due on 12 January and on 10 March is due on
 * two DAYS; printing "12/01/2026 - 10/03/2026" claims the eight weeks in between, which
 * nothing in the data says and which a planner reads as a delivery window.
 *
 * The expander is a popover rather than more text in the cell, so a row keeps its height
 * and the column keeps its width whether the order is due on one day or on nine.
 */
function DeliveryDatesCell({ dates }: { dates: string[] }) {
  if (!dates.length) return <span className="text-muted-foreground">-</span>;
  const [first, ...rest] = dates;
  const all = dates.map(fmtDate).join(', ');
  if (!rest.length) {
    return (
      <span className="truncate text-muted-foreground" title={all}>
        {fmtDate(first)}
      </span>
    );
  }
  return (
    <div className="flex min-w-0 items-center gap-1">
      <span className="truncate text-muted-foreground" title={all}>
        {fmtDate(first)}
      </span>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="dim"
            size="sm"
            className="h-6 shrink-0 px-1.5 text-xs"
            // The row underneath opens the order; this opens the list of dates.
            onClick={(e) => e.stopPropagation()}
            aria-label={`Show all ${dates.length} delivery dates`}
          >
            +{rest.length}
            <ChevronDown className="size-3" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          className="w-44 p-2"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex flex-col gap-1">
            {dates.map((d) => (
              <span key={d} className="text-sm tabular-nums">
                {fmtDate(d)}
              </span>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export interface SalesOrdersGridProps {
  /**
   * Pin the grid to ONE agent's orders.
   *
   * Set by the sales-agent detail page's Sales orders tab. With it, the Agent column and
   * the Agent filter come off (every row would say the same thing), and so do the two
   * writes that belong to the book rather than to one agent - Add sales order and Upload
   * sales orders. Everything else is the list, unchanged: the same columns, the same cell
   * renderers, the same toolbar, the same footer. There is no second sales-order table in
   * this product, so the two surfaces cannot drift apart.
   */
  salesAgentId?: string;
  /**
   * Where the reader's column order/visibility is stored. Left unset, `DataGrid` keys off
   * the route, which is right for the list and wrong inside a record page - the path
   * carries the agent's id, so every agent would get their own saved layout.
   */
  listingKey?: string;
}

export default function SalesOrdersGrid({ salesAgentId, listingKey }: SalesOrdersGridProps = {}) {
  // One agent's orders, inside that agent's record. What it turns off is listed on the prop.
  const pinnedToAgent = !!salesAgentId;
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  // "Show me the orders the Order Inquiry sheet created" is a filter on this list rather
  // than a screen of its own: a second list of the same entity is how two screens start
  // disagreeing about the same order.
  const [sourceFilter, setSourceFilter] = useState('');
  // The three questions this screen is actually asked: what came in over these dates, whose
  // orders are these, and what is still owed.
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [customerFilter, setCustomerFilter] = useState('');
  // The planning class the classification agents resolved - `order_type_label` is the ERP
  // document type and is blank on almost every row, so it never answered this question.
  const [demandClassFilter, setDemandClassFilter] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [outstandingOnly, setOutstandingOnly] = useState(false);

  // Create-only: editing happens on the detail page in place (A5), the same shape as the
  // project sales order screen, and the row click is the way there.
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<SalesOrder | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  // Which orders to plan together. The board is a URL, not a stored plan, so the selection
  // is the whole state there is: nothing is saved by picking rows here.
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const canPlan = useHasPermission(PLAN_PERMISSION);

  const queryClient = useQueryClient();

  // A pinned agent wins over the filter, which is not offered while it is pinned.
  const effectiveAgentId = salesAgentId ?? (agentFilter || null);

  const { data, isLoading, refetch } = useSalesOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter || null,
    priority: priorityFilter || null,
    source: sourceFilter || null,
    dateFrom: dateFrom || null,
    dateTo: dateTo || null,
    customerId: customerFilter || null,
    outstanding: outstandingOnly,
    salesAgentId: effectiveAgentId,
    demandClass: demandClassFilter || null,
  });

  const customerOptions = useCustomerOptions();
  const agentOptions = useSalesAgentOptions();
  const router = useRouter();

  const createMut = useCreateSalesOrder();
  const deleteMut = useDeleteSalesOrder();

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [
    searchQuery,
    statusFilter,
    priorityFilter,
    sourceFilter,
    dateFrom,
    dateTo,
    customerFilter,
    agentFilter,
    outstandingOnly,
    demandClassFilter,
  ]);

  const rows = useMemo<SalesOrder[]>(() => data?.data ?? [], [data]);

  // Carried into the detail URL so its prev/next pager walks the SAME filtered, sorted page
  // the user was reading (same param names as the list GET). Mirrors the purchase-order list.
  const detailSearch = useMemo(
    () =>
      buildDetailSearch(
        { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
        {
          status: statusFilter || undefined,
          priority: priorityFilter || undefined,
          source: sourceFilter || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          customer_code: customerFilter || undefined,
          outstanding: outstandingOnly ? 'true' : undefined,
          sales_agent_id: effectiveAgentId || undefined,
          demand_class: demandClassFilter || undefined,
        },
      ),
    [
      pagination.pageIndex,
      pagination.pageSize,
      sorting,
      searchQuery,
      statusFilter,
      priorityFilter,
      sourceFilter,
      dateFrom,
      dateTo,
      customerFilter,
      effectiveAgentId,
      outstandingOnly,
      demandClassFilter,
    ],
  );

  const detailHref = (so: SalesOrder) =>
    `/scm/sales-orders/${so.id}${detailSearch ? `?${detailSearch}` : ''}`;

  const handleSubmit = async (formData: SalesOrderFormData) => {
    await createMut.mutateAsync(formData);
    setFormOpen(false);
  };

  // The dialog itself toasts and links to the job page (Confirm -> apply -> onApplied); this
  // list only has to refresh once the write lands. The reorder plan is computed from the same
  // order book, so its two queries are invalidated alongside this list's own, the same as
  // Reorder planning's own `uploadQueued`.
  const handleUploadQueued = () => {
    void queryClient.invalidateQueries({ queryKey: ['scm', 'sales-orders'] });
    void queryClient.invalidateQueries({ queryKey: todayRunKey });
    void queryClient.invalidateQueries({ queryKey: runHistoryKey });
  };

  const columns = useMemo<ColumnDef<SalesOrder>[]>(
    () => [
      // Picking orders to plan together is what this list is for, beside reading it: the
      // fulfilment board takes a set of sales orders and nothing else. Each box says WHICH
      // order it ticks - a grid of "Select row" tells a screen reader nothing.
      buildSelectColumn<SalesOrder>({
        rowLabel: (row) => `Select ${row.original.so_number}`,
      }),
      {
        accessorKey: 'so_number',
        header: ({ column }) => <DataGridColumnHeader title="SO number" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            {/* The document number IS the way in, the same as the purchase-order list. The
                list query rides along so the detail page's prev/next walks the page the
                user was actually reading. */}
            <Link
              href={detailHref(row.original)}
              onClick={(e) => e.stopPropagation()}
              className="font-medium text-primary hover:underline"
            >
              {row.original.so_number}
            </Link>
            <span className="text-xs text-muted-foreground">{fmtDate(row.original.order_date)}</span>
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'SO number', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
            {row.original.market_segment ? (
              <span className="text-xs text-muted-foreground">{row.original.market_segment}</span>
            ) : null}
          </div>
        ),
        size: 200,
        meta: { headerTitle: 'Customer' },
      },
      // Off inside an agent's own record: a column whose every cell repeats the name at the
      // top of the page is a column that answers nothing.
      ...(pinnedToAgent
        ? []
        : [
            {
              accessorKey: 'sales_agent_code',
              header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
              cell: ({ row }) => {
                const code = row.original.sales_agent_code;
                if (!code) return <span className="text-muted-foreground">-</span>;
                return (
                  <span className="truncate" title={row.original.sales_agent_label || code}>
                    {code}
                  </span>
                );
              },
              size: 120,
              enableSorting: false,
              meta: { headerTitle: 'Agent' },
            } as ColumnDef<SalesOrder>,
          ]),
      {
        accessorKey: 'demand_class',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        // `order_type_label` is the ERP document type, and it is EMPTY on nearly every row
        // in this book - the AutoCount export rarely states one. `demand_class` is what the
        // classification agents actually resolved, so it is the primary answer here; the
        // document type rides along as a subline only when the order carries one AND it
        // says something different from Project/Retail.
        cell: ({ row }) => {
          const cls = demandClassBadge(row.original.demand_class);
          const label = row.original.order_type_label;
          const showLabel = label && label !== cls.label;
          return (
            <div className="flex flex-col gap-0.5">
              {/* The pill shape the sales-agents master uses, which is the page the captain
                  pointed at as the reference: `appearance="light" size="md"` for an enum. */}
              <Badge variant={cls.variant} appearance="light" size="md">
                {cls.label}
              </Badge>
              {showLabel ? (
                <span className="truncate text-2xs text-muted-foreground" title={label}>
                  {label}
                </span>
              ) : null}
            </div>
          );
        },
        size: 140,
        meta: { headerTitle: 'Type' },
      },
      {
        accessorKey: 'priority',
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={salesOrderPriorityVariant(row.original.priority)}
            appearance="light"
            size="md"
          >
            {formatStatusLabel(row.original.priority)}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Priority' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        // The same light chip as every other pill in this table. It was a ghost chip with a
        // dot, on the theory that a STATE is a different kind of thing from an enum; the
        // captain's verdict on a bare green dot beside a word was that it reads as an
        // unfinished control, so the colour is carried by the chip itself. Worded the way
        // AutoCount words it: `open` is Outstanding, `closed` is Completed.
        cell: ({ row }) => (
          <Badge
            variant={salesOrderStatusVariant(row.original.status)}
            appearance="light"
            size="md"
          >
            {salesOrderStatusLabel(row.original.status)}
          </Badge>
        ),
        size: 160,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'order_inquiries',
        header: ({ column }) => <DataGridColumnHeader title="Order inquiries" column={column} />,
        // What purchasing has been told to do about this order, by NUMBER. There is no
        // planning record to show and no "Planning" column: the business sees sales orders
        // and order inquiries, so the order names its inquiries and links to them.
        cell: ({ row }) => {
          const inquiries = row.original.order_inquiries ?? [];
          if (!inquiries.length) return <span className="text-muted-foreground">-</span>;
          const shown = inquiries.slice(0, ORDER_INQUIRY_LIMIT);
          const hidden = inquiries.length - shown.length;
          // One line per inquiry on the tooltip: who raised it, when, and how far
          // purchasing has got with it. The cell itself stays a row of numbers.
          const title = inquiries
            .map(
              (i) =>
                `${i.inquiry_no ?? 'Unnumbered'}: raised ${fmtDate(i.raised_at)}` +
                `${i.raised_by_name ? ` by ${i.raised_by_name}` : ''}` +
                `, ${i.rows_placed}/${i.rows_total} placed`,
            )
            .join('\n');
          return (
            <span className="truncate" title={title}>
              {shown.map((inquiry, index) => (
                <span key={inquiry.inquiry_no ?? index}>
                  {index > 0 ? ', ' : null}
                  <Link
                    href={`/project-sales/order-inquiries?query=${encodeURIComponent(
                      row.original.so_number,
                    )}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-primary hover:underline"
                  >
                    {inquiry.inquiry_no ?? 'Unnumbered'}
                  </Link>
                </span>
              ))}
              {hidden > 0 ? <span className="text-muted-foreground"> +{hidden} more</span> : null}
            </span>
          );
        },
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Order inquiries' },
      },
      {
        accessorKey: 'total_qty',
        header: ({ column }) => <DataGridColumnHeader title="Total qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.total_qty),
        size: 100,
        meta: { headerTitle: 'Total qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'committed_qty',
        header: ({ column }) => <DataGridColumnHeader title="Committed" column={column} />,
        cell: ({ row }) => (
          <span className={row.original.committed_qty > 0 ? 'font-medium' : 'text-muted-foreground'}>
            {fmtInt(row.original.committed_qty)}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Committed', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'total_amount',
        header: ({ column }) => <DataGridColumnHeader title="Total amount" column={column} />,
        // The same figure the detail page's Totals card prints, through the same formatter,
        // so the list and the order cannot disagree about what it is worth. `-` and not
        // `RM 0` when nobody priced it: 15,000 of the absorbed rows carry no money at all,
        // and an order nobody priced is not an order worth nothing.
        cell: ({ row }) =>
          row.original.total_amount ? formatMyrExact(row.original.total_amount) : '-',
        size: 140,
        // Not sortable: the total is summed from the LINES (each line's stated total, or
        // the arithmetic its parts support), so there is no column for Postgres to order
        // by and a SQL rewrite of that rule could disagree with the figure on screen.
        enableSorting: false,
        meta: {
          headerTitle: 'Total amount',
          headerClassName: 'text-right',
          cellClassName: 'text-right tabular-nums',
        },
      },
      {
        // The id stays `delivery_date_from` though the value is now a LIST: it is the sort
        // key the backend knows (`min(required_date)`) and the id every saved column layout
        // names, so renaming it would silently drop both.
        id: 'delivery_date_from',
        accessorFn: (so) => so.delivery_dates?.[0],
        header: ({ column }) => <DataGridColumnHeader title="Delivery date" column={column} />,
        // The LINE dates, not the header's `requested_delivery_date`: one order routinely
        // ships on several days, and the header figure is blank on most of this book. Every
        // DISTINCT date, never a range - an order due on 12 January and 10 March is due on
        // two days, and "12/01/2026 - 10/03/2026" claims the eight weeks between them.
        // The cell prints the earliest and puts the rest behind a "+N", so the column keeps
        // its width whether the order is due on one day or on nine. Sorted by the earliest,
        // which is the question the column is scanned with: what is due first.
        cell: ({ row }) => <DeliveryDatesCell dates={row.original.delivery_dates ?? []} />,
        size: 190,
        meta: { headerTitle: 'Delivery date' },
      },
      // No Location column here. A location is a property of a LINE - one order routinely
      // lands in two - so it lives on the detail page's lines grid, where it belongs to the
      // row it describes rather than being flattened into a list on the header.
      {
        accessorKey: 'linked_purchase_orders',
        header: ({ column }) => <DataGridColumnHeader title="Waiting on" column={column} />,
        cell: ({ row }) => {
          // The UNRESOLVED ones only. "Which of my orders is stuck behind a purchase order
          // we have not received" is the question this column exists to answer, and listing
          // the matched ones alongside would bury it.
          const waiting = (row.original.linked_purchase_orders ?? []).filter(
            (l) => !l.resolved,
          );
          if (!waiting.length) return <span className="text-muted-foreground">-</span>;
          // Capped, because a real order waits on 23 purchase orders and the full list
          // renders as a wall of text that says less than the first two plus a count. The
          // whole list is still on the title attribute for anyone who needs it.
          const numbers = waiting.map((l) => l.po_number);
          const shown = numbers.slice(0, WAITING_ON_LIMIT).join(', ');
          const hidden = numbers.length - Math.min(numbers.length, WAITING_ON_LIMIT);
          return (
            <span className="truncate" title={numbers.join(', ')}>
              {shown}
              {hidden > 0 ? (
                <span className="text-muted-foreground"> +{hidden} more</span>
              ) : null}
            </span>
          );
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Waiting on' },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <Badge
            variant={row.original.source === 'inquiry' ? 'primary' : 'secondary'}
            appearance="light"
            size="md"
          >
            {SOURCE_LABELS[row.original.source ?? 'manual'] ?? 'Manual'}
          </Badge>
        ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Source' },
      },
      {
        id: 'actions',
        header: '',
        // Delete only. Editing is the detail page's job - the row already opens it, and a
        // pencil beside a clickable row is a second door to the same screen. Creating a
        // delivery order is a delivery decision, not a list one.
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              className="h-8 w-8 text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleting(row.original);
              }}
              aria-label="Delete"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
        size: 70,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    // `detailSearch` is read by the SO-number link and the row-click handler. Left out of
    // the deps, the columns kept the query from the FIRST render, so every row linked to
    // page 1 of an unfiltered list and the detail pager walked a set the user never chose.
    [detailSearch, pinnedToAgent],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  // The orders the board would be opened on, in the order the list shows them. Document
  // NUMBERS, not ids: the board's URL is the plan (`?orders=SO1,SO2`), and it is a link a
  // person can read, keep and send.
  const selectedSoNumbers = table
    .getSelectedRowModel()
    .rows.map((r) => r.original.so_number);

  const planActions = buildPlanActions(
    { selectedCount: selectedSoNumbers.length, canPlan, max: MAX_PLAN_SELECTION },
    {
      onPlan: () =>
        router.push(
          `/project-sales/fulfilment-planning?orders=${encodeURIComponent(
            selectedSoNumbers.join(','),
          )}`,
        ),
    },
  );

  const filtersActive =
    (statusFilter ? 1 : 0) +
    (priorityFilter ? 1 : 0) +
    (sourceFilter ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0) +
    (customerFilter ? 1 : 0) +
    (agentFilter ? 1 : 0) +
    (outstandingOnly ? 1 : 0) +
    (demandClassFilter ? 1 : 0);

  // An empty book and an over-filtered one look identical in the grid, so they say different
  // things: one is a dead end the user can clear, the other is the step they have not done yet.
  // Inside an agent's record the third answer is neither: the book is full, this agent simply
  // has none of it, and pointing them at an upload would be pointing at the wrong screen.
  const emptyMessage =
    filtersActive || searchQuery ? (
      'No sales order matches this search and filter.'
    ) : pinnedToAgent ? (
      'No sales orders for this agent.'
    ) : (
      <span>
        No sales orders yet. Upload the Order Inquiry sheet from{' '}
        <Link href="/scm/reorder" className="text-primary underline underline-offset-2">
          Reorder planning
        </Link>{' '}
        to create them, or add one with Add sales order.
      </span>
    );

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        emptyMessage={emptyMessage}
        // The whole row opens the order. The SO-number link stays a real anchor so
        // middle-click and copy-link still work, and stops its own click propagating.
        onRowClick={(row) => router.push(detailHref(row))}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        listingKey={listingKey}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    // Four things, because those are the four a person holds when they come
                    // looking: the document number, who it is for, what is on it, and who
                    // sold it. The backend's `query` matches all four (`sales_order_service
                    // .list`), so the placeholder is not a promise the search cannot keep.
                    placeholder="Search SO, customer, product or agent..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-64 ps-9"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-3 rounded-md border p-2.5">
                      {/* The same words the detail page's Totals card and the lines grid's
                          own column use. "Still owed" was a third phrasing of one figure. */}
                      <Label htmlFor="so-outstanding-only" className="cursor-pointer">
                        Outstanding qty
                      </Label>
                      <Switch
                        id="so-outstanding-only"
                        checked={outstandingOnly}
                        onCheckedChange={setOutstandingOnly}
                      />
                    </div>
                    <div>
                      <Label htmlFor="so-customer" className="mb-1 block">
                        Customer
                      </Label>
                      <SearchableSelect
                        id="so-customer"
                        value={customerFilter}
                        onChange={setCustomerFilter}
                        options={customerOptions.data ?? []}
                        placeholder="All customers"
                        clearable
                      />
                    </div>
                    {/* Not offered while the grid is pinned to one agent: the answer is
                        already the page the reader is on. */}
                    {pinnedToAgent ? null : (
                      <div>
                        <Label htmlFor="so-agent" className="mb-1 block">
                          Agent
                        </Label>
                        <SearchableSelect
                          id="so-agent"
                          value={agentFilter}
                          onChange={setAgentFilter}
                          options={agentOptions.options}
                          placeholder="All agents"
                          clearable
                        />
                      </div>
                    )}
                    <div>
                      <Label htmlFor="so-date-range" className="mb-1 block">
                        Ordered
                      </Label>
                      <DateRangePicker
                        id="so-date-range"
                        from={dateFrom || null}
                        to={dateTo || null}
                        onChange={({ from, to }) => {
                          setDateFrom(from ?? '');
                          setDateTo(to ?? '');
                        }}
                        placeholder="All dates"
                      />
                    </div>
                    <div>
                      <Label htmlFor="so-type" className="mb-1 block">
                        Type
                      </Label>
                      <SearchableSelect
                        id="so-type"
                        value={demandClassFilter}
                        onChange={setDemandClassFilter}
                        options={DEMAND_CLASS_FILTER_OPTIONS}
                        placeholder="All types"
                      />
                    </div>
                    <div>
                      <Label htmlFor="so-status" className="mb-1 block">
                        Status
                      </Label>
                      <SearchableSelect
                        id="so-status"
                        value={statusFilter}
                        onChange={setStatusFilter}
                        options={SALES_ORDER_STATUS_FILTER_OPTIONS}
                        placeholder="All statuses"
                      />
                    </div>
                    <div>
                      <Label htmlFor="so-priority" className="mb-1 block">
                        Priority
                      </Label>
                      <SearchableSelect
                        id="so-priority"
                        value={priorityFilter}
                        onChange={setPriorityFilter}
                        options={PRIORITY_FILTER_OPTIONS}
                        placeholder="All priorities"
                      />
                    </div>
                    <div>
                      <Label htmlFor="so-source" className="mb-1 block">
                        Source
                      </Label>
                      <SearchableSelect
                        id="so-source"
                        value={sourceFilter}
                        onChange={setSourceFilter}
                        options={SOURCE_FILTER_OPTIONS}
                        placeholder="All sources"
                        clearable
                      />
                    </div>
                    {filtersActive > 0 ? (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setStatusFilter('');
                            setPriorityFilter('');
                            setSourceFilter('');
                            setDateFrom('');
                            setDateTo('');
                            setCustomerFilter('');
                            setAgentFilter('');
                            setOutstandingOnly(false);
                            setDemandClassFilter('');
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              // No `bulkActions`: the strip keeps its count, its Export and Clear, and
              // nothing else. Plan lives in the "Actions" dropdown below instead - the
              // strip only exists once rows are ticked, so an action that lived there
              // could not be found by anyone who had not already guessed it was there,
              // and its refusal over the board's bound read as a dead click.
              exportConfig={{ filename: 'sales_orders_export.xlsx' }}
              // Two secondary actions is what makes the shared toolbar collapse them into
              // an "Actions" dropdown (data-grid-list-toolbar.tsx) instead of a single loose
              // button, matching Delivery Orders (OrdersList.tsx).
              secondaryActions={[
                // First, because it is the action this list's row selection exists for.
                // Present (and disabled, with its reason) even with nothing ticked, so the
                // menu teaches that the orders are picked here.
                ...planActions,
                {
                  key: 'refresh',
                  label: 'Refresh',
                  icon: RefreshCw,
                  onClick: () => void refetch(),
                },
                // The upload carries the WHOLE book, so it belongs to the book's own screen.
                // Offering it inside one agent's record reads as "upload this agent's orders",
                // which is not what the file is.
                ...(pinnedToAgent
                  ? []
                  : [
                      {
                        key: 'upload-sales-orders',
                        // The file carries the whole book - orders still owed and orders already
                        // completed - so naming the action "outstanding" claimed a scope it
                        // never had.
                        label: 'Upload sales orders',
                        icon: Upload,
                        onClick: () => setUploadOpen(true),
                      },
                    ]),
              ]}
              primaryAction={
                // Same reason: a new order created from here would carry no agent, so the
                // record it was added from would not list it.
                pinnedToAgent ? undefined : (
                  <Button onClick={() => setFormOpen(true)}>
                    <Plus />
                    Add sales order
                  </Button>
                )
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      {/* Mounted only while open, the same as `UploadDataMenu` on Reorder planning: a closed
          dialog starts from a clean flow rather than whatever the last upload left behind. */}
      {uploadOpen ? (
        <OutstandingUploadDialog
          open
          onOpenChange={setUploadOpen}
          kind="sales-orders"
          onQueued={handleUploadQueued}
        />
      ) : null}

      {/* No Add action while pinned to an agent, so no form to mount either. */}
      {pinnedToAgent ? null : (
        <SalesOrderFormModal
          open={formOpen}
          onOpenChange={setFormOpen}
          onSubmit={handleSubmit}
          isPending={createMut.isPending}
        />
      )}

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        description={
          <>
            Delete sales order <span className="font-medium">{deleting?.so_number}</span> for{' '}
            {deleting?.customer_name}? This action cannot be undone.
          </>
        }
        onDelete={async () => {
          if (deleting) await deleteMut.mutateAsync(deleting.id);
        }}
        successMessage="Sales order deleted"
        onSuccess={() => setDeleting(null)}
      />
    </>
  );
}
