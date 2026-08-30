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
  Ban,
  CheckCheck,
  ChevronDown,
  Download,
  LayoutGrid,
  Link2,
  List,
  PackageSearch,
  Undo2,
  Unlink,
  Upload,
  Wand2,
  } from 'lucide-react';
import { toast } from 'sonner';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTable,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia } from '@/lib/helpers';
import { AutoLinkOrderInquiryDialog } from '../../_shared/components/AutoLinkOrderInquiryDialog';
import { BulkRejectOrderInquiryDialog } from '../../_shared/components/BulkRejectOrderInquiryDialog';
import { LinkDocumentDialog } from '../../_shared/components/LinkDocumentDialog';
import { UnlinkAllOrderInquiryDialog } from '../../_shared/components/UnlinkAllOrderInquiryDialog';
import { OutstandingUploadDialog } from '../../../scm/reorder/components/OutstandingUploadDialog';
import {
  useOrderInquiryHandshake,
  useOrderInquiryWorklist,
  useOrderInquiryWorklistSummary,
  useUnplaceAllPreview,
  useUploadedBook,
} from '../../_shared/hooks/useOrderInquiry';
import {
  ACK_ANY,
  ACK_FILTER_OPTIONS,
  ACK_TO_CONFIRM,
  isAcknowledgeable,
  isBulkRejectable,
} from '../../_shared/lib/orderInquiryAck';
import {
  NO_LINK_HORIZON,
  initialLinkHorizon,
  linkHorizonRequest,
  readStoredLinkHorizon,
  readUrlLinkHorizon,
  startsCleared,
  storeLinkHorizon,
} from '../../_shared/lib/linkHorizon';
import { facetSegments } from '../../_shared/lib/orderInquiryKinds';
import type { OrderInquiryKind } from '../../_shared/lib/orderInquiryKinds';
import { buildOrderInquiryMatrix } from '../../_shared/lib/orderInquiryMatrix';
import { deliveryMonthLabel } from '../../_shared/lib/orderInquiryWorklist';
import { saveBlobAs } from '../../_shared/services/fileDownload';
import {
  downloadOrderInquiryWorklistXlsx,
  unplaceOrderInquiryRow,
} from '../../_shared/services/orderInquiryService';
import type {
  OrderInquiryMatrixAxis,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryWorklistParams,
} from '../../_shared/types/orderInquiry.types';
import { OrderInquiryMatrixCellDrilldown } from './OrderInquiryMatrixCellDrilldown';
import { OrderInquiryScheduleMatrix } from './OrderInquiryScheduleMatrix';
import { OrderInquiryStrip } from './OrderInquiryStrip';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import { PageHeader } from '@/components/common/PageHeader';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

/**
 * WHETHER anything in either book covers the row, and out of which one (AC-D15). The
 * State column and its filter went with the drafts (item 11): what a buyer wants to know
 * is whether a document was FOUND, which this column already answers, so a second
 * vocabulary beside it was one thing too many to read. The stored values are untouched.
 */
const LINKED_OPTIONS = [
  { value: 'po', label: 'Found: a purchase order' },
  { value: 'spo', label: 'Found: an SPO' },
  { value: 'none', label: 'Not found' },
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

const MATRIX_AXES: OrderInquiryMatrixAxis[] = [
  'product',
  'sales_order',
  'customer',
  'agent',
];

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

const MATRIX_GRANULARITIES: OrderInquiryMatrixGranularity[] = [
  'day',
  'week',
  'month',
  'year',
];

function matrixGranularityFrom(
  value: string | null,
): OrderInquiryMatrixGranularity {
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
const ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION =
  'projects.order_inquiries.acknowledge';

/**
 * What the page opens on (R3/AC-D12): the rows nobody has said yes to yet. Purchasing
 * works this page as a to-do list, and a to-do list that opens on every row ever raised
 * is a list nobody works.
 *
 * A CLEARED filter travels as `?ack=all`, never as an absent parameter: an absent one
 * means "nobody has chosen" and the default would go straight back over the choice on
 * the next reload.
 */
function ackFilterFrom(value: string | null): string {
  if (value === null) return ACK_TO_CONFIRM;
  return value === ACK_ANY ? '' : value;
}

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
  const canActOnOrderInquiry = useHasPermission(
    ORDER_INQUIRY_ACTION_PERMISSION,
  );
  const canAcknowledge = useHasPermission(ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION);
  const { acknowledge, linkNow } = useOrderInquiryHandshake();
  const [unlinkingSelected, setUnlinkingSelected] = React.useState(false);

  const [view, setView] = React.useState<OrderInquiryView>(() =>
    viewFrom(searchParams.get('view')),
  );
  // Sourced from `?query=` on mount (captain: the demand drill's click-through -
  // `orderInquiryWorklistHref` - lands here with an SO number already in the URL), and
  // kept URL-synced the same way as `view`/`rows`/`granularity` below, so a link to a
  // filtered worklist is shareable. `useDebouncedSearch` seeds both halves from the same
  // value so the deep link filters on first render rather than after a flash of "every row".
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debounced,
    isSettling: debouncedSettling,
  } = useDebouncedSearch(searchParams.get('query') ?? '');
  const [month, setMonth] = React.useState('');
  const [supplierFilter, setSupplierFilter] = React.useState('');
  const [projectFilter, setProjectFilter] = React.useState('');
  const [raisedDate, setRaisedDate] = React.useState('');
  const [raisedByFilter, setRaisedByFilter] = React.useState('');
  const [linkedFilter, setLinkedFilter] = React.useState('');
  // Sourced from `?ack=` on mount and kept URL-synced, like `view` and `query`: the plan
  // page's "N to confirm" chip links straight into this list narrowed to them, and a chip
  // that landed on an unfiltered list would leave the buyer to find them. With NO `?ack=`
  // at all the page opens on its own default (AC-D12).
  const [ackFilter, setAckFilter] = React.useState(() =>
    ackFilterFrom(searchParams.get('ack')),
  );
  // How far out the three presses link (AC-LH1/AC-LH5). Sourced from the URL on mount -
  // `?link_up_to=` for a date and `?link_horizon=none` for a cleared box - then from this
  // browser's own memory, and seeded from the reorder plan's coverage date once the
  // summary answers. The URL first, because a shared link is the buyer telling somebody
  // else which horizon to look at. `seededHorizon` is what stops that seeding from
  // overwriting a date the buyer has since cleared on purpose.
  const storedHorizon = React.useRef(readStoredLinkHorizon());
  const urlHorizon = React.useRef(readUrlLinkHorizon(searchParams));
  const [linkUpTo, setLinkUpTo] = React.useState(() =>
    initialLinkHorizon(urlHorizon.current, storedHorizon.current, null),
  );
  // The buyer took the horizon OFF, as opposed to never having set one (S1). The two used
  // to be the same empty box: an empty date sent nothing, the server read that as "the
  // caller named none" and used the plan's own, so once a plan run named a horizon this
  // page could not link a far-future row at all. Held apart here, remembered per browser,
  // carried in the URL as `link_horizon=none`, and stated on the wire the same way.
  const [horizonCleared, setHorizonCleared] = React.useState(() =>
    startsCleared(urlHorizon.current, storedHorizon.current),
  );
  const seededHorizon = React.useRef(false);
  // What every press says about the horizon - one fragment, four callers, so Acknowledge,
  // Link selected, Link now and Auto-link can never mean different things by the same box.
  const horizonRequest = React.useMemo(
    () => linkHorizonRequest(linkUpTo, horizonCleared),
    [linkUpTo, horizonCleared],
  );
  // Which rows are ticked for the bulk Acknowledge (AC-H2). react-table's own selection
  // state through `buildSelectColumn`, never a hand-rolled Set: the canonical toolbar
  // reads exactly this for its bulk strip.
  const [rowSelection, setRowSelection] = React.useState<
    Record<string, boolean>
  >({});
  // The last upload this page queued, by job id, so the two next steps can be offered when
  // the WORKER is done with it rather than when the request was accepted (AC-H13). Null
  // until somebody uploads a book here.
  const [uploadJobId, setUploadJobId] = React.useState<string | null>(null);
  // Which card is pressed (AC-I11). Not one of the toolbar's filters: it lives on the
  // strip above BOTH views, so the same press narrows the matrix and the list. It IS
  // sent with the summary's own request all the same - only the `kinds` facet inside it
  // drops the card, server-side, which is what keeps the other two cards readable while
  // one is held down (see `listFilters` below).
  const [kindFilter, setKindFilter] = React.useState<OrderInquiryKind | null>(
    null,
  );
  const [exporting, setExporting] = React.useState(false);
  const [autoPlacing, setAutoPlacing] = React.useState(false);
  const [unplacingAll, setUnplacingAll] = React.useState(false);
  // Unlink selected asks first, like every other detach on this page (the ADR's own
  // "confirm before every destructive OR detach action"): it takes the documents off
  // several rows at once, and the quantities go back to demand with nothing to undo it.
  const [unlinkingSelectedOpen, setUnlinkingSelectedOpen] =
    React.useState(false);
  const [rejectingSelected, setRejectingSelected] = React.useState(false);
  // The ONE ticked row the manual Link dialog is about (R8). Held by id rather than by
  // the row, so a refetch between the press and the dialog cannot hand it a stale copy.
  const [linkingRowId, setLinkingRowId] = React.useState<string | null>(null);
  const [uploadingBook, setUploadingBook] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'delivery_date', desc: false },
  ]);
  const [matrixAxis, setMatrixAxis] = React.useState<OrderInquiryMatrixAxis>(
    () => matrixAxisFrom(searchParams.get('rows')),
  );
  const [matrixGranularity, setMatrixGranularity] =
    React.useState<OrderInquiryMatrixGranularity>(() =>
      matrixGranularityFrom(searchParams.get('granularity')),
    );
  const [openCell, setOpenCell] = React.useState<OrderInquiryMatrixCell | null>(
    null,
  );

  // The queued book, watched through the drawer's own feed, and what it wrote once the
  // worker is done with it (AC-H13). Nothing is offered before `landed`: linking against
  // a book still being read links the half of it that exists.
  const uploadedBook = useUploadedBook(uploadJobId);
  const uploadLanded = uploadedBook.landed;
  const uploadFailed = uploadedBook.failed;
  const uploadedProducts = uploadedBook.scope?.product_ids ?? [];
  // The purchase orders THIS upload wrote, when it can name them - the list filters on
  // exactly those numbers. A book naming more than the endpoint lists (or none at all, as
  // a failed read does) sends the buyer to the unfiltered list rather than to a filter
  // that would quietly show fifty of two hundred documents as if they were all of them.
  const uploadedDocuments = uploadedBook.scope?.documents ?? [];
  const purchaseOrdersHref =
    uploadedDocuments.length > 0 &&
    uploadedDocuments.length === (uploadedBook.scope?.document_count ?? 0)
      ? `/scm/purchase-orders?documents=${encodeURIComponent(uploadedDocuments.join(','))}`
      : '/scm/purchase-orders';

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
    // A CLEARED Confirmed filter says so out loud, because an absent `ack` is what the
    // DEFAULT is read from (AC-D12): dropping the parameter would put To confirm back on
    // the next reload and read as the clear having failed.
    next.set('ack', ackFilter || ACK_ANY);
    if (linkUpTo) next.set('link_up_to', linkUpTo);
    else next.delete('link_up_to');
    // A CLEARED horizon travels too (item 6). Dropping `link_up_to` and putting nothing in
    // its place says "nobody has chosen", which is the one thing the buyer did not say, and
    // the browser the link is shared with would open on the plan's own date instead.
    if (!linkUpTo && horizonCleared) next.set('link_horizon', NO_LINK_HORIZON);
    else next.delete('link_horizon');
    const nextQuery = next.toString();
    if (nextQuery === searchParams.toString()) return;
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
      scroll: false,
    });
  }, [
    view,
    matrixAxis,
    matrixGranularity,
    debounced,
    ackFilter,
    linkUpTo,
    horizonCleared,
    pathname,
    router,
    searchParams,
  ]);

  // A cell drawn from one axis/granularity is not a selection under a different one.
  React.useEffect(() => {
    setOpenCell(null);
  }, [matrixAxis, matrixGranularity]);

  // Narrowing changes which rows exist, so page 3 of the old set is a page of nothing in
  // the new one.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [
    debounced,
    month,
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
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
      raised_by: raisedByFilter || undefined,
      linked: (linkedFilter || undefined) as 'po' | 'spo' | 'none' | undefined,
      ack: (ackFilter || undefined) as OrderInquiryWorklistParams['ack'],
    }),
    [
      debounced,
      month,
      raisedDate,
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
  // minus the ones about where the row stands - the action is always about linked rows,
  // whatever else is filtered.
  const unplaceAllFilters = React.useMemo(
    () => ({
      query: debounced || undefined,
      delivery_month: month || undefined,
      raised_date: raisedDate || undefined,
      supplier_id: supplierFilter || undefined,
      project_id: projectFilter || undefined,
      raised_by: raisedByFilter || undefined,
    }),
    [
      debounced,
      month,
      raisedDate,
      supplierFilter,
      projectFilter,
      raisedByFilter,
    ],
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
  const planHorizon = summary.data?.link_up_to_default ?? null;

  // The plan's own coverage date, taken ONCE and only when neither the URL nor this
  // browser already carried one (AC-LH5). Once, because after the first answer the date on
  // screen is the buyer's - re-seeding on every refetch would put it back the moment they
  // cleared it, and a control that undoes itself is one nobody uses twice.
  React.useEffect(() => {
    if (seededHorizon.current || horizonCleared || !planHorizon) return;
    seededHorizon.current = true;
    setLinkUpTo((current) => current || planHorizon);
  }, [horizonCleared, planHorizon]);

  // Remembered per browser, so the buyer states their horizon once rather than every visit
  // - INCLUDING "no horizon", which used to remove the key and so read as "never chosen"
  // on the next visit, letting the plan default seed straight back over the choice.
  React.useEffect(() => {
    storeLinkHorizon(linkUpTo || (horizonCleared ? NO_LINK_HORIZON : null));
  }, [horizonCleared, linkUpTo]);

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
  const matrixList = useOrderInquiryWorklist(matrixParams, {
    enabled: view === 'schedule',
  });
  const matrix = React.useMemo(
    () =>
      buildOrderInquiryMatrix(
        matrixList.data?.data ?? [],
        matrixAxis,
        matrixGranularity,
      ),
    [matrixList.data, matrixAxis, matrixGranularity],
  );

  const rows = React.useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.total ?? 0;
  const months = summary.data?.by_month ?? [];
  const filtered = Boolean(
    debounced ||
    month ||
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
      const supplier = (summary.data?.suppliers ?? []).find(
        (s) => s.id === supplierFilter,
      );
      if (supplier) parts.push(`from ${supplier.label}`);
    }
    if (projectFilter) {
      const project = (summary.data?.projects ?? []).find(
        (p) => p.id === projectFilter,
      );
      if (project) parts.push(`for ${project.label}`);
    }
    if (raisedByFilter) {
      const person = (summary.data?.raised_by ?? []).find(
        (p) => p.id === raisedByFilter,
      );
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

  // Purchasing's page: the acknowledge grant is what marks purchasing, and CS (action
  // grant only) ticks nothing here.
  const canBulkLink = canAcknowledge && canActOnOrderInquiry;
  const columns = useOrderInquiryWorklistColumns({
    selectable: canAcknowledge,
  });

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    // The PREDICATE lives on the table, which is where TanStack reads `getCanSelect` from -
    // a column-level `enableRowSelection` is silently ignored, and every row would tick
    // (`FulfilmentPlanningClient` carries the same note over the same trap). As a plain
    // boolean this let a cancelled or already-acknowledged row be ticked, and the press
    // then failed on the whole batch.
    // A row stays tickable after Acknowledge (the captain, 27 Aug): the tick now feeds
    // three presses - Acknowledge, Link selected, Unlink selected - and each counts only
    // the ticked rows it applies to. Only a cancelled or actioned row has nothing left.
    enableRowSelection: (row) =>
      (canAcknowledge && isAcknowledgeable(row.original)) ||
      (canBulkLink &&
        row.original.state !== 'cancelled' &&
        row.original.state !== 'actioned'),
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

  const selectedRows = table
    .getSelectedRowModel()
    .rows.map((row) => row.original);
  const selectedAcknowledgeable = selectedRows.filter((row) =>
    isAcknowledgeable(row),
  );
  const selectedLinked = selectedRows.filter(
    (row) => row.state === 'placed' || row.state === 'partly_linked',
  );
  // Every OWED row, linked or not (plan section 1): with drafts written at raise most
  // rows in front of purchasing are already `placed`, so a Reject that only took
  // unlinked ones would refuse almost nothing.
  const selectedRejectable = selectedRows.filter((row) =>
    isBulkRejectable(row),
  );
  // The manual Link dialog is a ONE-row override (R8), so it is offered at exactly one
  // tick: two ticked rows would leave the page choosing which of them it meant.
  const linkTarget =
    selectedRows.length === 1 ? (selectedRows[0] ?? null) : null;
  const linkingRow = linkingRowId
    ? (rows.find((row) => row.id === linkingRowId) ?? null)
    : null;

  async function unlinkSelected() {
    if (selectedLinked.length === 0) return;
    setUnlinkingSelected(true);
    try {
      for (const row of selectedLinked) {
        await unplaceOrderInquiryRow(row.id);
      }
      toast.success(`Unlinked ${selectedLinked.length}`);
      setUnlinkingSelectedOpen(false);
      setRowSelection({});
      void list.refetch();
      void summary.refetch();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to unlink');
    } finally {
      setUnlinkingSelected(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await downloadOrderInquiryWorklistXlsx(listFilters);
      saveBlobAs(blob, `order-inquiry-${month || 'all-months'}.xlsx`);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : 'Failed to export the order inquiry',
      );
    } finally {
      setExporting(false);
    }
  }

  // A pressed CARD counts as a filter here even though it lives on the strip rather than
  // in this popover: it narrows exactly what the rest of these narrow, so leaving it out
  // hid "Clear filters" from the one person who most needs it - somebody who pressed Buy,
  // sees three rows, and has nothing on the toolbar offering to give the rest back.
  // How many rows the default filter is about (AC-D12), off the server's own facet: it
  // counts the filtered set, and a client that added two of the other counts together
  // would be answering a different question the moment either gained a state.
  const toConfirmCount = summary.data?.ack?.to_confirm;

  // What the chip above the grid says, so the buyer can see WHY the list is short and
  // take the narrowing off in one press (AC-D12).
  const ackChipLabel = ackFilter
    ? `Confirmed: ${
        ACK_FILTER_OPTIONS.find((option) => option.value === ackFilter)
          ?.label ?? ackFilter
      }`
    : null;

  const filtersActiveCount =
    (month ? 1 : 0) +
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
      <PageHeader title="Order inquiries">
        {/* The date every link on this page reaches up to by default: the latest
            completed reorder plan's own Plan until (`plan_link_horizon`). Stated here
            because it was only ever readable inside the Auto link dialog (the captain,
            28 Aug 2026: "show the plan until ... for visibility"). */}
        <p
          data-testid="oi-plan-until"
          className="text-sm text-muted-foreground"
        >
          {summary.isPending
            ? 'Plan until ...'
            : planHorizon
              ? `Plan until ${formatDateInMalaysia(planHorizon)}`
              : 'No Plan until in force'}
        </p>
      </PageHeader>

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
        onToggle={(kind) =>
          setKindFilter((current) => (current === kind ? null : kind))
        }
      />

      {/* The book this page queued has been READ (AC-H13) - the worker is done with it,
          which is when its documents exist to link against. Two next steps and no third:
          link what they can now cover, or go and look at the purchase orders that
          arrived. Dismissed by acting, never by a timer. */}
      {uploadLanded && canAcknowledge ? (
        <Alert appearance="light">
          <AlertIcon>
            <Upload />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>
              {uploadFailed
                ? 'The book could not be read'
                : 'The book has been read'}
            </AlertTitle>
            <AlertDescription>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={linkNow.isPending}
                  onClick={() =>
                    linkNow.mutate(
                      // The products the upload wrote, so one book does not re-deal every
                      // open instruction in the company. Empty means the job named none,
                      // and then it IS every acknowledged row - the same rule the endpoint
                      // states for an omitted list.
                      {
                        ...(uploadedProducts.length
                          ? { product_ids: uploadedProducts }
                          : {}),
                        ...horizonRequest,
                      },
                      { onSuccess: () => setUploadJobId(null) },
                    )
                  }
                >
                  <Link2 className="size-4" aria-hidden />
                  {linkNow.isPending ? 'Linking…' : 'Link now'}
                </Button>
                <Button asChild size="sm" variant="outline">
                  <Link href={purchaseOrdersHref}>Open purchase orders</Link>
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setUploadJobId(null)}
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
              <Label
                htmlFor="matrix-rows"
                className="text-sm text-muted-foreground"
              >
                Rows
              </Label>
              <div className="w-44">
                <SearchableSelect
                  id="matrix-rows"
                  value={matrixAxis}
                  onChange={(value) =>
                    setMatrixAxis(value as OrderInquiryMatrixAxis)
                  }
                  options={MATRIX_AXIS_OPTIONS}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Label
                htmlFor="matrix-granularity"
                className="text-sm text-muted-foreground"
              >
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
                <PackageSearch
                  className="mx-auto size-6 text-muted-foreground"
                  aria-hidden
                />
                <h3 className="mt-2 text-sm font-semibold">
                  No inquiries in this view
                </h3>
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
                MATRIX_AXIS_OPTIONS.find(
                  (option) => option.value === matrixAxis,
                )?.label ?? 'Product'
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
          tableLayout={{
            width: 'fixed',
            columnsResizable: true,
            columnsVisibility: true,
          }}
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
                  <ListSearchInput
                    value={search}
                    onChange={setSearch}
                    isSettling={debouncedSettling}
                    placeholder="Search S/O, item, product, customer or CS name…"
                    aria-label="Search order inquiry rows"
                    className="w-full max-w-xs"
                  />
                }
                filters={{
                  kind: 'custom',
                  active: filtersActiveCount > 0,
                  activeCount: filtersActiveCount,
                  // The page opens narrowed to what purchasing has not confirmed, and a
                  // list that is short for a reason nobody stated reads as missing data.
                  activeSummary: ackChipLabel
                    ? { label: ackChipLabel, onClear: () => setAckFilter('') }
                    : undefined,
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
                        <Label className="text-xs text-muted-foreground">
                          Linked
                        </Label>
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
                          Confirmed
                        </Label>
                        <SearchableSelect
                          value={ackFilter}
                          onChange={setAckFilter}
                          clearable
                          options={ACK_FILTER_OPTIONS.map((option) => {
                            const count =
                              option.value === ACK_TO_CONFIRM
                                ? toConfirmCount
                                : summary.data?.ack?.[
                                    option.value as keyof NonNullable<
                                      typeof summary.data.ack
                                    >
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
                        <Label className="text-xs text-muted-foreground">
                          Supplier
                        </Label>
                        <SearchableSelect
                          value={supplierFilter}
                          onChange={setSupplierFilter}
                          clearable
                          options={(summary.data?.suppliers ?? []).map(
                            (entry) => ({
                              value: entry.id,
                              label: entry.label,
                            }),
                          )}
                          placeholder="Every supplier"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">
                          Project
                        </Label>
                        <SearchableSelect
                          value={projectFilter}
                          onChange={setProjectFilter}
                          clearable
                          options={(summary.data?.projects ?? []).map(
                            (entry) => ({
                              value: entry.id,
                              label: entry.label,
                            }),
                          )}
                          placeholder="Every project"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">
                          Raised by
                        </Label>
                        <SearchableSelect
                          value={raisedByFilter}
                          onChange={setRaisedByFilter}
                          clearable
                          options={(summary.data?.raised_by ?? []).map(
                            (entry) => ({
                              value: entry.id,
                              label: entry.label,
                            }),
                          )}
                          placeholder="Everyone"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label
                          className="text-xs text-muted-foreground"
                          htmlFor="raised-on"
                        >
                          Raised on
                        </Label>
                        <Input
                          id="raised-on"
                          type="date"
                          value={raisedDate}
                          onChange={(event) =>
                            setRaisedDate(event.target.value)
                          }
                        />
                      </div>
                      {filtersActiveCount > 0 && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full"
                          onClick={() => {
                            setMonth('');
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
                // The bulk strip keeps its COUNT and its Clear and nothing else
                // (item 12, AC-D13). Every press moved into the Actions menu, where
                // each one states how many ticked rows it applies to - a strip of
                // buttons on the left and a menu of the same names on the right was two
                // places to look for one action.
                bulkActions={[]}
                secondaryActions={[
                  {
                    key: 'auto-place',
                    label: 'Auto link all\u2026',
                    icon: Wand2,
                    onClick: () => setAutoPlacing(true),
                  },
                  ...(canBulkLink
                    ? [
                        {
                          key: 'link-selected',
                          label: `Link selected (${linkTarget ? 1 : 0})`,
                          icon: Link2,
                          disabled: !linkTarget,
                          disabledReason: linkTarget
                            ? undefined
                            : 'Tick exactly one row to choose its document by hand.',
                          onClick: () =>
                            setLinkingRowId(linkTarget?.id ?? null),
                        },
                        {
                          key: 'unlink-selected',
                          label: `Unlink selected (${selectedLinked.length})`,
                          icon: Unlink,
                          disabled:
                            selectedLinked.length === 0 || unlinkingSelected,
                          disabledReason:
                            selectedLinked.length === 0
                              ? 'Tick linked rows to unlink.'
                              : undefined,
                          onClick: () => setUnlinkingSelectedOpen(true),
                        },
                      ]
                    : []),
                  ...(canAcknowledge
                    ? [
                        {
                          key: 'reject-selected',
                          label: `Reject selected (${selectedRejectable.length})`,
                          icon: Ban,
                          destructive: true,
                          disabled: selectedRejectable.length === 0,
                          disabledReason:
                            selectedRejectable.length === 0
                              ? 'Tick rows purchasing still owes an answer on.'
                              : undefined,
                          onClick: () => setRejectingSelected(true),
                        },
                      ]
                    : []),
                  {
                    key: 'unplace-all',
                    label: 'Unlink all\u2026',
                    icon: Undo2,
                    onClick: () => setUnplacingAll(true),
                    // N1: a lacking action grant, or the preview call failing for any
                    // other reason, must never read the same as "genuinely nothing to
                    // unplace" - each says its own thing.
                    disabled:
                      !canActOnOrderInquiry ||
                      unplacePreview.isError ||
                      unplaceCount === 0,
                    disabledReason: !canActOnOrderInquiry
                      ? "You don't have permission to unlink rows"
                      : unplacePreview.isError
                        ? 'Could not check linked rows - try again'
                        : unplaceCount === 0
                          ? 'No linked rows to unlink'
                          : undefined,
                  },
                  {
                    key: 'export',
                    label: exporting ? 'Preparing\u2026' : 'Export Excel',
                    icon: Download,
                    disabled: exporting,
                    onClick: () => void handleExport(),
                  },
                ]}
                // START: the two things purchasing DOES here (item 12). Feeding the book
                // and saying yes to the rows are the whole job, so they sit behind one
                // primary press rather than a split button and a wide count-bearing one
                // that together pushed the left cluster onto a second row.
                primaryAction={
                  canAcknowledge ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button type="button" size="sm">
                          Start
                          <ChevronDown
                            className="size-3.5 opacity-60"
                            aria-hidden
                          />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-60">
                        <DropdownMenuItem
                          onSelect={() => setUploadingBook(true)}
                        >
                          <Upload className="size-4" aria-hidden />
                          Upload purchase orders
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={
                            selectedAcknowledgeable.length === 0 ||
                            acknowledge.isPending
                          }
                          title={
                            selectedAcknowledgeable.length === 0
                              ? 'Tick the rows you are taking on.'
                              : undefined
                          }
                          onSelect={() => {
                            if (selectedAcknowledgeable.length === 0) return;
                            acknowledge.mutate(
                              {
                                rowIds: selectedAcknowledgeable.map(
                                  (row) => row.id,
                                ),
                                // No horizon of its own (R6): Confirm links the
                                // remainder of rows somebody has already decided to
                                // take on, and the plan's own date is the right reach
                                // for that. The cut off belongs to Auto link all, which
                                // is the press that reaches rows nobody has looked at.
                              },
                              { onSuccess: () => setRowSelection({}) },
                            );
                          }}
                        >
                          <CheckCheck className="size-4" aria-hidden />
                          {`Confirm selected (${selectedAcknowledgeable.length})`}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null
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
                    {list.error instanceof Error
                      ? list.error.message
                      : 'Try again shortly.'}
                  </p>
                </div>
              ) : (
                <DataGridTable />
              )}
            </CardTable>
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          </Card>
        </DataGrid>
      )}

      <AutoLinkOrderInquiryDialog
        open={autoPlacing}
        onOpenChange={setAutoPlacing}
        linkUpTo={linkUpTo}
        horizonCleared={horizonCleared}
        onHorizonChange={(value, cleared) => {
          setLinkUpTo(value);
          setHorizonCleared(cleared);
        }}
      />
      {/* One reason for the batch (item 15/AC-D6). */}
      <BulkRejectOrderInquiryDialog
        open={rejectingSelected}
        onOpenChange={setRejectingSelected}
        rowIds={selectedRejectable.map((row) => row.id)}
        onRejected={() => setRowSelection({})}
      />
      {/* The manual override for ONE ticked row (R8), reached from the Actions menu. */}
      {linkingRow ? (
        <LinkDocumentDialog
          rowId={linkingRow.id}
          itemCode={linkingRow.item_code}
          qty={linkingRow.qty}
          linkedQty={linkingRow.linked_qty}
          deliveryDate={linkingRow.delivery_date}
          linkUpTo={linkUpTo}
          onDone={() => setLinkingRowId(null)}
        />
      ) : null}
      {/* The book purchasing feeds, from purchasing's own page (AC-H12) - the SAME dialog
          and the same worker job the purchase orders list mounts, never a second
          importer. The history book is not offered here: it is a different desk's file. */}
      {uploadingBook ? (
        <OutstandingUploadDialog
          open
          onOpenChange={(next) => !next && setUploadingBook(false)}
          kind="purchase-orders"
          onQueued={(queued) => setUploadJobId(queued.job_id)}
        />
      ) : null}
      <AlertDialog
        open={unlinkingSelectedOpen}
        onOpenChange={setUnlinkingSelectedOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unlink selected</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedLinked.length === 1
                ? 'Remove this row\u2019s links? That quantity goes back to demand, and the next reorder suggestion counts it again.'
                : `Remove every link on the ${selectedLinked.length} selected rows? Those quantities go back to demand, and the next reorder suggestion counts them again.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unlinkingSelected}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void unlinkSelected();
              }}
              disabled={unlinkingSelected}
            >
              Unlink
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
