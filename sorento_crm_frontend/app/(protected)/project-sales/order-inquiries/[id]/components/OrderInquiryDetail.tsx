'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import {
  Ban,
  Bookmark,
  Download,
  FileText,
  Link2,
  ListOrdered,
  Printer,
  ShoppingCart,
  Ship,
  Unlink,
  Undo2,
  Wand2,
} from 'lucide-react';
import BackToList from '@/components/common/BackToList';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { EntityDownloadsButton } from '@/components/my-downloads/EntityDownloadsButton';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useDeferredBulkAction } from '@/hooks/useDeferredBulkAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { LinkDocumentDialog } from '../../../_shared/components/LinkDocumentDialog';
import { BulkRejectOrderInquiryDialog } from '../../../_shared/components/BulkRejectOrderInquiryDialog';
import {
  ORDER_INQUIRY_HEADER_KEY,
  ORDER_INQUIRY_HEADER_LINES_KEY,
  ORDER_INQUIRY_HEADER_RELATED_DOCUMENTS_KEY,
  ORDER_INQUIRY_HEADERS_KEY,
  ORDER_INQUIRY_RESERVE_REQUESTS_KEY,
  orderInquiryHeadersPagerQuery,
  useAutoPlaceOrderInquiryRows,
  useCreateOrderInquiryReserveRequest,
  useExportOrderInquiryXlsx,
  useOrderInquiryHandshake,
  useOrderInquiryHeaderDetail,
  useOrderInquiryHeaderLines,
  useOrderInquiryHeaderRelatedDocuments,
  useOrderInquiryReserveRequests,
  useOrderInquiryRowHistory,
  useReserveOrderInquiryRow,
} from '../../../_shared/hooks/useOrderInquiry';
import { useReserveRowOptions } from '../../../_shared/hooks/useReserveRowOptions';
import { ackStateOf } from '../../../_shared/lib/orderInquiryAck';
import {
  orderInquiryHeaderStatusLabel,
  orderInquiryHeaderStatusVariant,
} from '../../../_shared/lib/orderInquiryHeaderStatus';
import {
  canCancelReserveRequest,
  resolveReserveRowRequestAnchor,
} from '../../../_shared/lib/orderInquiryReserve';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import { OrderInquiryGeneralTab } from './OrderInquiryGeneralTab';
import { ReserveRequestDialog } from './ReserveRequestDialog';
import { ReserveRowDialog, type ReserveRowDialogRow } from './ReserveRowDialog';
import {
  OrderInquiryRelatedPurchaseOrdersTab,
  OrderInquiryRelatedSposTab,
} from './OrderInquiryRelatedDocumentsTab';

/** Same grant the worklist gates Choose document / Link / Unlink / Reject / Unconfirm
 * on (`OrderInquiriesClient.tsx`). */
const ORDER_INQUIRY_ACTION_PERMISSION = 'projects.order_inquiry.action';
/** Same grant Confirm is gated on everywhere else in this module. */
const ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION = 'projects.order_inquiries.acknowledge';
/** R1 (`PLAN-oi-request-cs-reserve.md`): only the CS head confirms a reserve. */
const ORDER_INQUIRY_RESERVE_PERMISSION = 'projects.order_inquiries.reserve';

/** BLOCKER B1 (reviewer fix round): `linked_qty` deliberately EXCLUDES a reserve-kind
 * link (`links_for_rows`' own filter, `project_order_inquiry_service.py`: "a reserve
 * link is not a PO or an SPO document ... `reserved_qty` is where it actually
 * surfaces") - the row's TRUE remaining, the same arithmetic the backend's own
 * `create_request` caps `qty_requested` against, subtracts BOTH. */
function rowRemaining(row: OrderInquiryWorklistRow): number {
  return (
    Number(row.qty || '0') -
    Number(row.linked_qty || '0') -
    Number(row.reserved_qty || '0') -
    Number(row.bundled_qty || '0')
  );
}

/** AC-RS-23: why a selected row cannot be named on a "Request CS to reserve" ask - the
 * SAME rules the backend's own `create_request` enforces (3.2), read client-side off
 * the worklist row so the menu item can be gated and explained before the request is
 * even sent. `null` means the row is requestable.
 *
 * N9 (reviewer round): names the OFFENDING row - several rows can be ticked at once,
 * and a tooltip reading "already has an open reserve request" with no indication of
 * WHICH of them left the reader guessing. */
function reserveIneligibleReason(row: OrderInquiryWorklistRow): string | null {
  const item = row.item_code ?? 'This row';
  if (!['ORDER', 'ORDER_BACK'].includes(row.verb)) {
    return `${item}: not an ORDER or ORDER BACK row`;
  }
  if (!['raised', 'partly_linked'].includes(row.state)) {
    return `${item}: not open for a reserve request`;
  }
  if (rowRemaining(row) <= 0) {
    return `${item}: has nothing left to request`;
  }
  if (row.reserve_state === 'requested') {
    return `${item}: already has an open reserve request`;
  }
  return null;
}

/** A ticked line still owed a document (mirrors `OrderInquiriesClient.tsx`'s own
 * `isLinkable`, kept smaller here on purpose: a single header's lines carry none of the
 * worklist's cross-header bundling, so the extra tests that function runs have nothing
 * to answer on this screen). */
function isLinkable(row: OrderInquiryWorklistRow): boolean {
  if (ackStateOf(row) === 'rejected') return false;
  if (!['raised', 'partly_linked', 'placed'].includes(row.state)) return false;
  const linked = (row.links ?? []).reduce((sum, link) => sum + Number(link.qty || '0'), 0);
  return Number(row.qty || '0') - linked > 0;
}

export function OrderInquiryDetail({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const canAct = useHasPermission(ORDER_INQUIRY_ACTION_PERMISSION);
  const canAcknowledge = useHasPermission(ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION);
  const canReserve = useHasPermission(ORDER_INQUIRY_RESERVE_PERMISSION);
  const { data: session } = useSession();
  const currentUserId = session?.user?.id ?? null;

  const headerQuery = useOrderInquiryHeaderDetail(id);
  const linesQuery = useOrderInquiryHeaderLines(id);
  const relatedQuery = useOrderInquiryHeaderRelatedDocuments(id);
  const reserveRequestsQuery = useOrderInquiryReserveRequests(id);
  // S5 (reviewer round): the two reserve writes go through the hooks layer like every
  // other write on this page - `ReserveRequestDialog`/`ReserveRowDialog` receive the
  // mutate functions as props rather than importing the feature service themselves.
  const createReserveRequestMutation = useCreateOrderInquiryReserveRequest(id);
  const reserveRowMutation = useReserveOrderInquiryRow(id);
  const { acknowledge, unacknowledge } = useOrderInquiryHandshake();
  const autoPlace = useAutoPlaceOrderInquiryRows();
  const exportXlsx = useExportOrderInquiryXlsx(id);

  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
  const [chooseDocumentOpen, setChooseDocumentOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reserveDialogOpen, setReserveDialogOpen] = useState(false);
  // section 6c F2 / round 3 section 6d G1: which row ids `ReserveRowDialog` is open
  // for - a click on the Lines grid's own Reserve pill (`orderInquiryHeaderLinesColumns
  // .tsx`) opens exactly one; `?reserve=<request_id>` (AC-RS-65) opens every still-open
  // row of that request at once. Empty = closed.
  const [reserveDialogRowIds, setReserveDialogRowIds] = useState<string[]>([]);
  const [downloadsOpen, setDownloadsOpen] = useState(false);
  // Unlink selected (AC-DP-06, fix round UL): a server-deferred pending action
  // (`order_inquiry_row.unlink`), never a confirm dialog - one park per ticked line,
  // ONE countdown rendered inline in the header card (`useDeferredBulkAction`'s own
  // `inline` surface). Cancel withdraws every park and leaves the ticked lines ticked;
  // the selection clears only once every park has actually settled (`onFinished`),
  // never at park time.
  const unlinkSelectedAction = useDeferredBulkAction({
    actionKey: 'order_inquiry_row.unlink',
    entityType: 'order_inquiry_row',
    surface: 'inline',
    verb: 'Unlinking',
    pastVerb: 'unlinked',
    describe: (count) => `${count} line${count === 1 ? '' : 's'}`,
    invalidateKeys: [
      [ORDER_INQUIRY_HEADER_LINES_KEY, id],
      [ORDER_INQUIRY_HEADER_KEY, id],
      [ORDER_INQUIRY_HEADER_RELATED_DOCUMENTS_KEY, id],
      [ORDER_INQUIRY_HEADERS_KEY],
    ],
    onFinished: () => setRowSelection({}),
  });

  // S6 (AC-B6-4): a `?row=<id>` deep link always lands on Lines, whatever `tab` says -
  // the only tab that row could ever be found on.
  const tab = searchParams.get('row') ? 'lines' : searchParams.get('tab') || 'lines';
  function handleTabChange(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === 'lines') params.delete('tab');
    else params.set('tab', next);
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  const lines = useMemo(() => linesQuery.data ?? [], [linesQuery.data]);
  const activeLines = useMemo(() => lines.filter((l) => l.state !== 'cancelled'), [lines]);
  const selectedLines = useMemo(
    () => activeLines.filter((l) => rowSelection[l.id]),
    [activeLines, rowSelection],
  );
  const selectedIds = useMemo(() => selectedLines.map((l) => l.id), [selectedLines]);
  const selectedConfirmable = useMemo(
    () =>
      selectedLines.filter((l) => {
        const state = ackStateOf(l);
        return state === 'awaiting' || state === 'changed';
      }),
    [selectedLines],
  );
  const selectedUnconfirmable = useMemo(
    () =>
      selectedLines.filter((l) => {
        const state = ackStateOf(l);
        return state === 'acknowledged' || state === 'changed';
      }),
    [selectedLines],
  );
  // W (coordinator's ruling): nothing ticked means every confirmed line of the WHOLE
  // OI, the same ticked/whole-OI symmetry Confirm and Auto link already have - not just
  // "nothing to unconfirm". `activeLines` already holds every non-cancelled line of this
  // header (`useOrderInquiryHeaderLines` reads every page of the worklist's own
  // `inquiry_id` filter), so no extra fetch is needed for the "all" scope.
  const allUnconfirmable = useMemo(
    () =>
      activeLines.filter((l) => {
        const state = ackStateOf(l);
        return state === 'acknowledged' || state === 'changed';
      }),
    [activeLines],
  );
  const unconfirmScope = selectedIds.length > 0 ? selectedUnconfirmable : allUnconfirmable;
  const selectedRejectable = useMemo(
    () =>
      selectedLines.filter(
        (l) => ackStateOf(l) !== 'rejected' && ['raised', 'partly_linked', 'placed'].includes(l.state),
      ),
    [selectedLines],
  );
  const selectedLinkable = useMemo(() => selectedLines.filter(isLinkable), [selectedLines]);
  const selectedLinked = useMemo(
    () => selectedLines.filter((l) => l.state === 'placed' || l.state === 'partly_linked'),
    [selectedLines],
  );
  const chooseDocumentLine =
    selectedIds.length === 1 ? (activeLines.find((l) => l.id === selectedIds[0]) ?? null) : null;

  // AC-RS-23: enabled only when EVERY selected row is requestable; disabled otherwise,
  // with a tooltip naming the FIRST reason (not a tally of every one).
  const reserveIneligibleReasons = useMemo(
    () => selectedLines.map(reserveIneligibleReason).filter((reason): reason is string => Boolean(reason)),
    [selectedLines],
  );
  const canRequestReserve = selectedLines.length > 0 && reserveIneligibleReasons.length === 0;
  const reserveDisabledReason =
    selectedLines.length === 0 ? 'Select at least one row' : reserveIneligibleReasons[0];

  const reserveDialogEntries = useMemo(
    () =>
      selectedLines.map((line) => ({
        key: line.id,
        productId: line.product_id ?? null,
        location: line.location ?? null,
      })),
    [selectedLines],
  );
  const reserveDialogResolved = useReserveRowOptions(reserveDialogOpen ? reserveDialogEntries : []);
  const reserveDialogRows = useMemo(
    () =>
      selectedLines.map((line) => {
        const own = reserveDialogResolved[line.id];
        const remaining = rowRemaining(line);
        return {
          id: line.id,
          item_code: line.item_code ?? null,
          delivery_date: line.delivery_date ?? null,
          remaining: String(Math.max(0, remaining)),
          defaultLocation: own?.defaultWarehouseId ?? '',
          locationOptions: own?.options ?? [],
        };
      }),
    [selectedLines, reserveDialogResolved],
  );

  function invalidateReserveQueries() {
    // The dialog / card already toast their own success (AC-RS-22/AC-RS-26); this is
    // only the read-side refresh so the pill, the header badge and the card itself move.
    linesQuery.refetch();
    reserveRequestsQuery.refetch();
  }

  const openReserveRequest = reserveRequestsQuery.data?.find((r) => r.state === 'requested');

  // Round 3 (section 6d G1): the FIRST (primary) row `ReserveRowDialog` is open for -
  // the one the History/Unreserve/"Cancel request" controls below are scoped to. On the
  // single-row (line-click) path it is the only row; on the multi-row (`?reserve=`)
  // path every row shares the SAME request, so the primary row's own open request is
  // the whole dialog's request.
  const primaryReserveRowId = reserveDialogRowIds[0] ?? null;
  const reserveRowDialogRow = primaryReserveRowId
    ? (activeLines.find((line) => line.id === primaryReserveRowId) ?? null)
    : null;

  // section 6c F2/F3/F5: which request answers a given row - the OPEN one when it
  // still has an unanswered entry, else null (History/Unreserve for an ANSWERED row
  // resolve their own anchor separately, `reserveRowLastRequestId` below).
  const openRequestForRow = useCallback(
    (targetRowId: string | null) => {
      if (!targetRowId) return null;
      const request = (reserveRequestsQuery.data ?? []).find(
        (r) =>
          r.state === 'requested' &&
          r.rows.some((row) => row.row_id === targetRowId && row.qty_reserved == null),
      );
      const row = request?.rows.find((r) => r.row_id === targetRowId);
      if (!request || !row) return null;
      return {
        requestId: request.id,
        ordinal: request.ordinal,
        qtyRequested: row.qty_requested,
        requestedBy: request.requested_by,
        requestedByName: request.requested_by_name,
        requestedAt: request.requested_at,
      };
    },
    [reserveRequestsQuery.data],
  );
  const reserveRowOpenRequest = useMemo(
    () => openRequestForRow(primaryReserveRowId),
    [openRequestForRow, primaryReserveRowId],
  );
  const reserveRowLastRequestId = useMemo(() => {
    if (!primaryReserveRowId) return null;
    const answered = (reserveRequestsQuery.data ?? [])
      .map((r) => {
        const row = r.rows.find((row) => row.row_id === primaryReserveRowId);
        return row && row.qty_reserved != null
          ? { id: r.id, ordinal: r.ordinal, rowQtyReserved: row.qty_reserved }
          : null;
      })
      .filter((entry): entry is NonNullable<typeof entry> => entry !== null);
    return resolveReserveRowRequestAnchor(answered);
  }, [reserveRequestsQuery.data, primaryReserveRowId]);
  const reserveRowEffectiveRequestId =
    reserveRowOpenRequest?.requestId ?? reserveRowLastRequestId ?? null;

  // The dialog's own Location/Reserved defaults are resolved off the PRIMARY row's
  // product alone and shared by every section a multi-row dialog carries - the same
  // simplification the plan's own OrderInquiryDetail wiring names (item code, open
  // request, history and net reserved are the only fields mapped PER row).
  const reserveRowOptionsEntries = useMemo(
    () =>
      reserveRowDialogRow
        ? [
            {
              key: reserveRowDialogRow.id,
              productId: reserveRowDialogRow.product_id ?? null,
              location: reserveRowDialogRow.location ?? null,
            },
          ]
        : [],
    [reserveRowDialogRow],
  );
  const reserveRowOptionsResolved = useReserveRowOptions(reserveRowOptionsEntries);
  const reserveRowOptions = reserveRowDialogRow
    ? reserveRowOptionsResolved[reserveRowDialogRow.id]
    : undefined;

  const reserveRowHistoryQuery = useOrderInquiryRowHistory(
    reserveRowEffectiveRequestId,
    primaryReserveRowId,
  );
  const reserveRowHistory = useMemo(
    () =>
      (reserveRowHistoryQuery.data ?? []).map((entry) => ({
        kind: entry.kind,
        qty: entry.qty,
        location: entry.location,
        reason: entry.reason,
        actorName: entry.actor_name,
        createdAt: entry.created_at,
      })),
    [reserveRowHistoryQuery.data],
  );

  // AC-RS-65: every row this dialog holds a section for, mapped from its own line -
  // item code, open request, net reserved per row; History only follows the PRIMARY
  // row (the single-row path's own tab; a multi-row dialog never shows one).
  const reserveRowDialogRows: ReserveRowDialogRow[] = useMemo(
    () =>
      reserveDialogRowIds
        .map((rowId) => activeLines.find((line) => line.id === rowId))
        .filter((line): line is OrderInquiryWorklistRow => Boolean(line))
        .map((line) => ({
          rowId: line.id,
          itemCode: line.item_code ?? null,
          openRequest: openRequestForRow(line.id),
          history: line.id === primaryReserveRowId ? reserveRowHistory : [],
          netReservedQty: line.reserved_qty ?? '0',
        })),
    [reserveDialogRowIds, activeLines, openRequestForRow, primaryReserveRowId, reserveRowHistory],
  );

  // F2 header "Cancel request" (plan 6c): the same countdown pattern round 1's own
  // `ReserveRequestsCard` used, now built here and handed down as a prop - the dialog
  // stays free of react-query so its own vitest suite can render it with no providers.
  // Round 3: applies to the WHOLE request (1..N rows), so it stays keyed off the
  // primary row's own open request - every row this dialog carries shares one request.
  const reserveRowCancelAction = useDeferredAction({
    actionKey: 'order_inquiry_reserve_request.cancel',
    entityType: 'order_inquiry_reserve_request',
    entityId: reserveRowOpenRequest?.requestId ?? null,
    verb: 'Cancelling',
    subject: reserveRowOpenRequest ? `Request #${reserveRowOpenRequest.ordinal}` : '',
    surface: 'inline',
    watchFromMount: Boolean(reserveRowOpenRequest),
    successMessage: 'Reserve request cancelled',
    invalidateKeys: [
      [ORDER_INQUIRY_HEADER_LINES_KEY, id],
      [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, id],
    ],
  });

  // S2 (reviewer round, ADR-PRODUCT-STANDARDS D7): Unreserve is a server-deferred
  // pending action too, the same shape as the request's own Cancel above - a
  // countdown with Cancel, no confirm step, the server commits `unreserve_row` even
  // if this dialog (or the tab) closes mid-window. `entity_type` is deliberately its
  // own (`order_inquiry_reserve_row`), distinct from `order_inquiry_row.unlink`'s -
  // two different pending actions on the same row must not block each other under
  // the one-pending-action-per-record constraint. Only reachable on the single-row
  // path (a multi-row dialog's own rows are always still-open, never yet reserved).
  const reserveRowUnreserveAction = useDeferredAction({
    actionKey: 'order_inquiry_reserve_row.unreserve',
    entityType: 'order_inquiry_reserve_row',
    entityId: primaryReserveRowId,
    verb: 'Unreserving',
    subject: reserveRowDialogRow?.item_code ?? '',
    surface: 'inline',
    watchFromMount: Boolean(primaryReserveRowId),
    successMessage: 'Unreserved',
    invalidateKeys: [
      [ORDER_INQUIRY_HEADER_LINES_KEY, id],
      [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, id],
    ],
    onCommitted: () => reserveRowHistoryQuery.refetch(),
  });

  const openReserveRowDialog = useCallback((row: OrderInquiryWorklistRow) => {
    setReserveDialogRowIds([row.id]);
  }, []);

  function closeReserveRowDialog() {
    setReserveDialogRowIds([]);
    if (searchParams.get('reserve')) {
      const params = new URLSearchParams(searchParams.toString());
      params.delete('reserve');
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    }
  }

  // AC-RS-65: `?reserve=<request_id>` auto-opens the dialog with EVERY still-open row
  // of that request - once, and only while nothing else is already open.
  useEffect(() => {
    const reserveParam = searchParams.get('reserve');
    if (!reserveParam || reserveDialogRowIds.length > 0) return;
    const request = (reserveRequestsQuery.data ?? []).find((r) => r.id === reserveParam);
    const openRowIds = (request?.rows ?? [])
      .filter((row) => row.qty_reserved == null)
      .map((row) => row.row_id);
    if (openRowIds.length > 0) setReserveDialogRowIds(openRowIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, reserveRequestsQuery.data]);

  const header = headerQuery.data;

  // AC-DP-05: the visible label is simply how many lines are TICKED; disabled reads the
  // scope's own eligibility - the ticked lines' handshake state with something ticked,
  // the header's own count with nothing ticked.
  const confirmLabel = selectedIds.length > 0 ? `Confirm (${selectedIds.length})` : 'Confirm';
  const confirmDisabled =
    selectedIds.length > 0
      ? selectedConfirmable.length === 0
      : (header?.lines_to_confirm ?? 0) === 0;

  function runConfirm() {
    acknowledge.mutate(
      selectedIds.length > 0 ? { rowIds: selectedIds } : { filter: { inquiry_id: id } },
      { onSuccess: () => setRowSelection({}) },
    );
  }

  function runUnconfirm() {
    unacknowledge.mutate(
      unconfirmScope.map((l) => l.id),
      { onSuccess: () => setRowSelection({}) },
    );
  }

  function runLinkSelected() {
    if (selectedLinkable.length === 0) return;
    autoPlace.mutate(
      { row_ids: selectedLinkable.map((l) => l.id) },
      { onSuccess: () => setRowSelection({}) },
    );
  }

  /**
   * Auto link (AC-DP-06, owner markup 21 Sep): ALWAYS enabled, no confirm dialog -
   * unlike the worklist's own "Auto link all", which asks for a link-horizon date
   * first. Ticked lines -> exactly those (unfiltered - the cascade itself decides what
   * it can and cannot place, the same as the worklist's own unconditional run over
   * everything); nothing ticked -> the whole OI via `filter: { inquiry_id }` (AC-AL-01).
   * Same hook, same result reporting (`linkOutcomeText`'s toast) as "Link selected" and
   * the worklist's "Auto link all" - nothing new invented here.
   *
   * NOTE for the captain: when every ticked line already IS linkable, this sends the
   * exact same `{ row_ids }` payload through the exact same `autoPlace` mutation as
   * `runLinkSelected` above - the two differ only when a ticked line is NOT linkable
   * (rejected, or already fully placed), which `runLinkSelected` silently drops and this
   * still sends. Left both in place; not my call which one goes.
   */
  function runAutoLink() {
    autoPlace.mutate(
      selectedIds.length > 0 ? { row_ids: selectedIds } : { filter: { inquiry_id: id } },
      { onSuccess: () => setRowSelection({}) },
    );
  }

  /**
   * Unlink selected (AC-DP-06, fix round UL): one `order_inquiry_row.unlink` pending
   * action per ticked line, behind the one inline countdown `unlinkSelectedAction`
   * renders in the header card. No dialog, no immediate commit.
   */
  function unlinkSelected() {
    if (selectedLinked.length === 0) return;
    unlinkSelectedAction.run(selectedLinked.map((line) => ({ id: line.id })));
  }

  // S1 (reviewer, fix round 22 Sep 2026): `page.tsx`'s own `PageHeader` already renders
  // a `BackToList` - a second one at the top of every state here was redundant. The
  // in-card CTA on not-found stays: it is the page's own next step, not a nav duplicate.
  if (headerQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  const notFound =
    headerQuery.isError &&
    headerQuery.error instanceof Error &&
    headerQuery.error.message.includes('no longer exists');

  if (notFound) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">This order inquiry no longer exists</div>
          <BackToList listPath="/project-sales/order-inquiries" label="Back to order inquiries" />
        </Card>
      </div>
    );
  }

  if (headerQuery.isError || !header) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">Could not load this order inquiry</div>
          <p className="max-w-md text-sm text-muted-foreground">
            {headerQuery.error instanceof Error
              ? headerQuery.error.message
              : 'Try again in a moment.'}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                <CardTitle className="text-lg tabular-nums">{header.inquiry_no}</CardTitle>
                <Badge
                  variant={orderInquiryHeaderStatusVariant(header.status)}
                  appearance="light"
                  size="md"
                >
                  {orderInquiryHeaderStatusLabel(header.status)}
                </Badge>
                {openReserveRequest ? (
                  <Badge variant="warning" appearance="light" size="md">
                    Request to reserve
                  </Badge>
                ) : null}
              </div>
              <span className="text-sm text-muted-foreground">
                Raised by {header.raised_by_name ?? 'Not recorded'}
                {header.raised_at ? ` on ${formatDateTimeInMalaysia(header.raised_at)}` : ''}
              </span>
            </div>
            <DetailActions
              pager={{
                ...orderInquiryHeadersPagerQuery,
                detailPath: '/project-sales/order-inquiries',
                currentId: id,
                ariaLabel: 'order inquiry',
              }}
              gear={
                <DetailActionsMenu ariaLabel="Order inquiry options">
                  {canAct ? (
                    <>
                      <DropdownMenuItem onSelect={runAutoLink}>
                        <Wand2 className="size-4" aria-hidden />
                        Auto link
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={!chooseDocumentLine}
                        onSelect={
                          chooseDocumentLine
                            ? (e) => {
                                e.preventDefault();
                                setChooseDocumentOpen(true);
                              }
                            : undefined
                        }
                      >
                        <Link2 className="size-4" aria-hidden />
                        Choose document
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={selectedLinkable.length === 0}
                        onSelect={selectedLinkable.length ? runLinkSelected : undefined}
                      >
                        <Wand2 className="size-4" aria-hidden />
                        Link selected
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={selectedLinked.length === 0}
                        onSelect={selectedLinked.length ? unlinkSelected : undefined}
                      >
                        <Unlink className="size-4" aria-hidden />
                        Unlink selected
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={selectedRejectable.length === 0}
                        onSelect={
                          selectedRejectable.length
                            ? (e) => {
                                e.preventDefault();
                                setRejectOpen(true);
                              }
                            : undefined
                        }
                      >
                        <Ban className="size-4" aria-hidden />
                        Reject selected
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={unconfirmScope.length === 0}
                        onSelect={unconfirmScope.length ? runUnconfirm : undefined}
                      >
                        <Undo2 className="size-4" aria-hidden />
                        Unconfirm
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                    </>
                  ) : null}
                  {canAcknowledge ? (
                    canRequestReserve ? (
                      <DropdownMenuItem
                        onSelect={(e) => {
                          e.preventDefault();
                          setReserveDialogOpen(true);
                        }}
                      >
                        <Bookmark className="size-4" aria-hidden />
                        Request CS to reserve
                      </DropdownMenuItem>
                    ) : (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="block">
                            <DropdownMenuItem disabled>
                              <Bookmark className="size-4" aria-hidden />
                              Request CS to reserve
                            </DropdownMenuItem>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>{reserveDisabledReason}</TooltipContent>
                      </Tooltip>
                    )
                  ) : null}
                  <DropdownMenuItem
                    disabled={exportXlsx.isPending}
                    onSelect={
                      exportXlsx.isPending ? undefined : () => exportXlsx.mutate()
                    }
                  >
                    <Download className="size-4" aria-hidden />
                    Export Excel
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={(e) => {
                      e.preventDefault();
                      setDownloadsOpen(true);
                    }}
                  >
                    <Printer className="size-4" aria-hidden />
                    Download history
                  </DropdownMenuItem>
                </DetailActionsMenu>
              }
              primary={
                canAcknowledge ? (
                  <Button
                    size="sm"
                    onClick={runConfirm}
                    disabled={confirmDisabled || acknowledge.isPending}
                  >
                    {confirmLabel}
                  </Button>
                ) : undefined
              }
            />
          </div>
          {unlinkSelectedAction.countdown ? (
            <div className="mt-3">{unlinkSelectedAction.countdown}</div>
          ) : null}
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={handleTabChange} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start">
          <TabsTrigger value="lines">
            <ListOrdered />
            <span>Lines</span>
          </TabsTrigger>
          <TabsTrigger value="general">
            <FileText />
            <span>General</span>
          </TabsTrigger>
          <TabsTrigger value="related_po">
            <ShoppingCart />
            <span>Related PO</span>
          </TabsTrigger>
          <TabsTrigger value="related_spo">
            <Ship />
            <span>Related SPO</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="lines" className="mt-0 focus-visible:outline-none">
          <OrderInquiryLinesTab
            lines={lines}
            isLoading={linesQuery.isLoading}
            rowSelection={rowSelection}
            onRowSelectionChange={setRowSelection}
            onReserveClick={openReserveRowDialog}
          />
        </TabsContent>

        <TabsContent value="general" className="mt-0 focus-visible:outline-none">
          <OrderInquiryGeneralTab header={header} />
        </TabsContent>

        <TabsContent value="related_po" className="mt-0 focus-visible:outline-none">
          <OrderInquiryRelatedPurchaseOrdersTab
            rows={relatedQuery.data?.purchase_orders ?? []}
            isLoading={relatedQuery.isLoading}
          />
        </TabsContent>

        <TabsContent value="related_spo" className="mt-0 focus-visible:outline-none">
          <OrderInquiryRelatedSposTab
            rows={relatedQuery.data?.spos ?? []}
            isLoading={relatedQuery.isLoading}
          />
        </TabsContent>
      </Tabs>

      {chooseDocumentOpen && chooseDocumentLine ? (
        <LinkDocumentDialog
          rowId={chooseDocumentLine.id}
          itemCode={chooseDocumentLine.item_code}
          qty={chooseDocumentLine.qty}
          linkedQty={String(
            (chooseDocumentLine.links ?? []).reduce((sum, l) => sum + Number(l.qty || '0'), 0),
          )}
          deliveryDate={chooseDocumentLine.delivery_date}
          onDone={() => {
            setChooseDocumentOpen(false);
            setRowSelection({});
          }}
        />
      ) : null}

      <BulkRejectOrderInquiryDialog
        rowIds={selectedRejectable.map((l) => l.id)}
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        onRejected={() => setRowSelection({})}
      />

      {reserveDialogOpen ? (
        <ReserveRequestDialog
          open={reserveDialogOpen}
          onOpenChange={setReserveDialogOpen}
          rows={reserveDialogRows}
          onSend={(payload) => createReserveRequestMutation.mutateAsync(payload)}
          onSent={() => {
            setRowSelection({});
            invalidateReserveQueries();
          }}
        />
      ) : null}

      {reserveRowDialogRows.length > 0 ? (
        <ReserveRowDialog
          open
          onOpenChange={(next) => {
            if (!next) closeReserveRowDialog();
          }}
          rows={reserveRowDialogRows}
          locationOptions={reserveRowOptions?.options ?? []}
          defaultLocationId={reserveRowOptions?.defaultWarehouseId ?? null}
          availableQtyByLocation={reserveRowOptions?.availableQtyByWarehouseId ?? {}}
          canAct={canReserve}
          onReserve={(requestId, rowId, payload) =>
            reserveRowMutation.mutateAsync({
              requestId,
              rowId,
              payload,
              // N1 (AC-RS-26 "toast wording kept"): "Reserved, <requester> notified" -
              // the parent already resolves the requester's name for the panel above
              // the form, so the mutation's own toast reads the same one.
              requestedByName: reserveRowOpenRequest?.requestedByName ?? null,
            })
          }
          cancelControl={
            canCancelReserveRequest(currentUserId, reserveRowOpenRequest?.requestedBy, canReserve)
              ? {
                  isPending: reserveRowCancelAction.isPending,
                  isBlocked: reserveRowCancelAction.isBlocked,
                  countdown: reserveRowCancelAction.countdown,
                  start: () => reserveRowCancelAction.start(),
                }
              : null
          }
          unreserveControl={
            canReserve
              ? {
                  isPending: reserveRowUnreserveAction.isPending,
                  isBlocked: reserveRowUnreserveAction.isBlocked,
                  countdown: reserveRowUnreserveAction.countdown,
                  start: ({ qty, note }) =>
                    reserveRowUnreserveAction.start({
                      request_id: reserveRowEffectiveRequestId,
                      qty,
                      note,
                    }),
                }
              : null
          }
          onConfirmed={() => {
            invalidateReserveQueries();
            reserveRowHistoryQuery.refetch();
          }}
        />
      ) : null}

      <EntityDownloadsButton
        entityType="order_inquiry"
        entityId={id}
        label={header.inquiry_no}
        open={downloadsOpen}
        onOpenChange={setDownloadsOpen}
      />
    </div>
  );
}

export default OrderInquiryDetail;
