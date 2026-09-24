'use client';

import { useCallback, useMemo, useState } from 'react';
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
  useCommitOrderInquiryReserve,
  useCreateOrderInquiryReserveRequest,
  useExportOrderInquiryXlsx,
  useOrderInquiryHandshake,
  useOrderInquiryHeaderDetail,
  useOrderInquiryHeaderLines,
  useOrderInquiryHeaderRelatedDocuments,
  useOrderInquiryReserveRequests,
  useOrderInquiryRowHistory,
} from '../../../_shared/hooks/useOrderInquiry';
import { useReserveRowOptions } from '../../../_shared/hooks/useReserveRowOptions';
import { ackStateOf } from '../../../_shared/lib/orderInquiryAck';
import {
  orderInquiryHeaderStatusLabel,
  orderInquiryHeaderStatusVariant,
} from '../../../_shared/lib/orderInquiryHeaderStatus';
import {
  bareLocationCode,
  canCancelReserveRequest,
  resolveReserveRowRequestAnchor,
} from '../../../_shared/lib/orderInquiryReserve';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import { OrderInquiryGeneralTab } from './OrderInquiryGeneralTab';
import { ReserveRequestDialog } from './ReserveRequestDialog';
import { ReserveLineForm } from './ReserveLineForm';
import { ReserveLineHistoryDialog } from './ReserveLineHistoryDialog';
import type { StagedReserveEntry } from './orderInquiryHeaderLinesColumns';
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
  const commitReserveMutation = useCommitOrderInquiryReserve(id);
  const { acknowledge, unacknowledge } = useOrderInquiryHandshake();
  const autoPlace = useAutoPlaceOrderInquiryRows();
  const exportXlsx = useExportOrderInquiryXlsx(id);

  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
  const [chooseDocumentOpen, setChooseDocumentOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reserveDialogOpen, setReserveDialogOpen] = useState(false);
  // Round 4 (`PLAN-oi-request-cs-reserve.md` 6e.2): CS's own staged (not yet
  // committed) decisions, keyed by OI row id - cleared on a successful commit or an
  // individual Undo. A page reload loses it by design (plan's own words: "a reload
  // loses it - trigger for server drafts: CS asks to stage across sessions").
  const [stagedByRowId, setStagedByRowId] = useState<Record<string, StagedReserveEntry>>({});
  // Which row `ReserveLineForm` is open for, and in which mode - the tick (AC-RS-84)
  // never opens this at all, it stages directly.
  const [editingRow, setEditingRow] = useState<{
    row: OrderInquiryWorklistRow;
    mode: 'reserve' | 'amend';
  } | null>(null);
  // Which row `ReserveLineHistoryDialog` is open for (AC-RS-89).
  const [historyRow, setHistoryRow] = useState<OrderInquiryWorklistRow | null>(null);
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
    linesQuery.refetch();
    reserveRequestsQuery.refetch();
  }

  // AC-RS-83/84/87: the OI's own open reserve request, if any - round 4 keeps a
  // single-open-request-at-a-time model (the same one the Lines tab's own State
  // filter and the header CTA both key off); a row that already carries a link
  // answered by a PAST (no longer open) request is reached through `answeredRequestRowFor`
  // below instead.
  const openReserveRequest = reserveRequestsQuery.data?.find((r) => r.state === 'requested');

  // 6c F2/6e.2: the row's own OPEN (unanswered) request-row entry, extended with the
  // warehouse the request itself was raised against (R3's own default pool) - the
  // tick (AC-RS-84) stages against exactly this, no dialog, no second resolution.
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
        warehouseId: row.warehouse_id,
        location: row.location,
        requestedBy: request.requested_by,
        requestedByName: request.requested_by_name,
        requestedAt: request.requested_at,
      };
    },
    [reserveRequestsQuery.data],
  );

  // AC-RS-86/89: the ANSWERED request row that still anchors History/Amend for a
  // RESERVED line - the highest-ordinal request that still holds a link on it (or any
  // answered one), the same `resolveReserveRowRequestAnchor` round 3's own dialog
  // used for the identical question.
  const answeredRequestRowFor = useCallback(
    (targetRowId: string) => {
      const candidates = (reserveRequestsQuery.data ?? [])
        .flatMap((r) =>
          r.rows
            .filter((row) => row.row_id === targetRowId && row.qty_reserved != null)
            .map((row) => ({
              id: r.id,
              ordinal: r.ordinal,
              rowQtyReserved: row.qty_reserved,
              qtyRequested: row.qty_requested,
              location: row.location,
            })),
        );
      if (candidates.length === 0) return null;
      const anchorId = resolveReserveRowRequestAnchor(candidates);
      return candidates.find((c) => c.id === anchorId) ?? null;
    },
    [reserveRequestsQuery.data],
  );

  // AC-RS-84: the tick - stages the FULL requested qty at the default pool the
  // request itself already named, no dialog, nothing posted.
  const handleTickReserve = useCallback(
    (row: OrderInquiryWorklistRow) => {
      const open = openRequestForRow(row.id);
      if (!open || !open.warehouseId) return;
      setStagedByRowId((prev) => ({
        ...prev,
        [row.id]: {
          kind: 'reserve',
          qty: Number(open.qtyRequested || '0'),
          warehouseId: open.warehouseId,
          locationLabel: open.location,
          reason: null,
        },
      }));
    },
    [openRequestForRow],
  );

  const handleEditReserve = useCallback((row: OrderInquiryWorklistRow) => {
    setEditingRow({ row, mode: 'reserve' });
  }, []);

  const handleAmendReserve = useCallback((row: OrderInquiryWorklistRow) => {
    setEditingRow({ row, mode: 'amend' });
  }, []);

  const handleHistoryClick = useCallback((row: OrderInquiryWorklistRow) => {
    setHistoryRow(row);
  }, []);

  const handleUndoStaged = useCallback((rowId: string) => {
    setStagedByRowId((prev) => {
      if (!(rowId in prev)) return prev;
      const next = { ...prev };
      delete next[rowId];
      return next;
    });
  }, []);

  // AC-RS-85/86: `ReserveLineForm`'s own pool options - resolved only while it is
  // open, for that ONE row (the same lazy-per-row pattern `useReserveRowOptions`
  // already gives the purchasing-side dialog above).
  const editingRowOptionsEntries = useMemo(
    () =>
      editingRow
        ? [
            {
              key: editingRow.row.id,
              productId: editingRow.row.product_id ?? null,
              location: editingRow.row.location ?? null,
            },
          ]
        : [],
    [editingRow],
  );
  const editingRowOptionsResolved = useReserveRowOptions(editingRowOptionsEntries);
  const editingRowOptions = editingRow ? editingRowOptionsResolved[editingRow.row.id] : undefined;
  const editingOpenRequest = editingRow ? openRequestForRow(editingRow.row.id) : null;
  const editingAnsweredRow = editingRow ? answeredRequestRowFor(editingRow.row.id) : null;

  function handleStage(payload: { warehouse_id?: string; qty_reserved: number; reason: string | null }) {
    if (!editingRow) return;
    const rowId = editingRow.row.id;
    if (editingRow.mode === 'reserve') {
      const locationOption = (editingRowOptions?.options ?? []).find(
        (option) => option.value === payload.warehouse_id,
      );
      setStagedByRowId((prev) => ({
        ...prev,
        [rowId]: {
          kind: 'reserve',
          qty: payload.qty_reserved,
          warehouseId: payload.warehouse_id ?? null,
          locationLabel: locationOption ? bareLocationCode(locationOption.label) : null,
          reason: payload.reason,
        },
      }));
    } else {
      setStagedByRowId((prev) => ({
        ...prev,
        [rowId]: { kind: 'amend', qty: payload.qty_reserved, reason: payload.reason },
      }));
    }
    setEditingRow(null);
  }

  const historyAnchorRequestId =
    (historyRow ? openRequestForRow(historyRow.id)?.requestId : null) ??
    (historyRow ? answeredRequestRowFor(historyRow.id)?.id : null) ??
    null;
  const historyQuery = useOrderInquiryRowHistory(historyAnchorRequestId, historyRow?.id ?? null);

  // AC-RS-87: the header's own `Reserve (N)` CTA - ONE commit call for every staged
  // decision at once. Simplifying assumption (captain, named per CLAUDE.md "say so"):
  // every staged row commits against the SAME request id, `openReserveRequest`'s own -
  // correct for every case this round's own UAC exercises (a batch worked from the
  // `?reserve=`/State-filter flow); a reader amending a line whose own answering
  // request has ALREADY moved past `requested` (no open request left on the whole OI)
  // falls back to that row's own answered request instead, so a lone Amend still has
  // somewhere to commit against.
  const stagedCount = Object.keys(stagedByRowId).length;
  function commitStaged() {
    const entries = Object.entries(stagedByRowId);
    if (entries.length === 0) return;
    const requestId =
      openReserveRequest?.id ?? answeredRequestRowFor(entries[0][0])?.id ?? null;
    if (!requestId) return;
    const reserves: { row_id: string; warehouse_id: string; qty_reserved: number; reason?: string | null }[] = [];
    const amendments: { row_id: string; qty_reserved: number; reason?: string | null }[] = [];
    for (const [rowId, entry] of entries) {
      if (entry.kind === 'reserve' && entry.warehouseId) {
        reserves.push({
          row_id: rowId,
          warehouse_id: entry.warehouseId,
          qty_reserved: entry.qty,
          reason: entry.reason,
        });
      } else if (entry.kind === 'amend') {
        amendments.push({ row_id: rowId, qty_reserved: entry.qty, reason: entry.reason });
      }
    }
    commitReserveMutation.mutate(
      {
        requestId,
        payload: { reserves, amendments },
        requesterName: openReserveRequest?.requested_by_name ?? null,
      },
      { onSuccess: () => setStagedByRowId({}) },
    );
  }

  // AC-RS-89: "Cancel request" moves into the Actions menu (deferred countdown, same
  // shape round 1-3 already used) - no per-dialog header any more.
  const reserveRequestCancelAction = useDeferredAction({
    actionKey: 'order_inquiry_reserve_request.cancel',
    entityType: 'order_inquiry_reserve_request',
    entityId: openReserveRequest?.id ?? null,
    verb: 'Cancelling',
    subject: openReserveRequest ? `Request #${openReserveRequest.ordinal}` : '',
    surface: 'inline',
    watchFromMount: Boolean(openReserveRequest),
    successMessage: 'Reserve request cancelled',
    invalidateKeys: [
      [ORDER_INQUIRY_HEADER_LINES_KEY, id],
      [ORDER_INQUIRY_RESERVE_REQUESTS_KEY, id],
    ],
  });
  const canCancelOpenRequest =
    Boolean(openReserveRequest) &&
    canCancelReserveRequest(currentUserId, openReserveRequest?.requested_by, canReserve);


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
                  {canCancelOpenRequest ? (
                    <DropdownMenuItem
                      onSelect={(e) => {
                        e.preventDefault();
                        reserveRequestCancelAction.start();
                      }}
                    >
                      <Undo2 className="size-4" aria-hidden />
                      Cancel request
                    </DropdownMenuItem>
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
                canAcknowledge || (canReserve && (Boolean(openReserveRequest) || stagedCount > 0)) ? (
                  <div className="flex items-center gap-2">
                    {canAcknowledge ? (
                      <Button
                        size="sm"
                        onClick={runConfirm}
                        disabled={confirmDisabled || acknowledge.isPending}
                      >
                        {confirmLabel}
                      </Button>
                    ) : null}
                    {/* AC-RS-87: visible with the reserve permission while a request is
                        open or anything is staged; enabled only once something is
                        staged. */}
                    {canReserve && (openReserveRequest || stagedCount > 0) ? (
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid="reserve-cta"
                        onClick={commitStaged}
                        disabled={stagedCount === 0 || commitReserveMutation.isPending}
                      >
                        {stagedCount > 0 ? `Reserve (${stagedCount})` : 'Reserve'}
                      </Button>
                    ) : null}
                  </div>
                ) : undefined
              }
            />
          </div>
          {unlinkSelectedAction.countdown ? (
            <div className="mt-3">{unlinkSelectedAction.countdown}</div>
          ) : null}
          {reserveRequestCancelAction.countdown ? (
            <div className="mt-3">{reserveRequestCancelAction.countdown}</div>
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
            canReserve={canReserve}
            stagedByRowId={stagedByRowId}
            onTickReserve={handleTickReserve}
            onEditReserve={handleEditReserve}
            onAmendReserve={handleAmendReserve}
            onHistoryClick={handleHistoryClick}
            onUndoStaged={handleUndoStaged}
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

      {editingRow ? (
        <ReserveLineForm
          open
          onOpenChange={(next) => {
            if (!next) setEditingRow(null);
          }}
          itemCode={editingRow.row.item_code ?? null}
          mode={editingRow.mode}
          requestedQty={
            editingRow.mode === 'reserve'
              ? (editingOpenRequest?.qtyRequested ?? '0')
              : (editingAnsweredRow?.qtyRequested ?? editingRow.row.reserved_qty ?? '0')
          }
          locationOptions={editingRowOptions?.options ?? []}
          availableQtyByLocation={editingRowOptions?.availableQtyByWarehouseId ?? {}}
          defaultLocationId={
            editingOpenRequest?.warehouseId ?? editingRowOptions?.defaultWarehouseId ?? null
          }
          lockedLocationLabel={editingAnsweredRow?.location ?? editingRow.row.location ?? ''}
          initialQty={editingRow.row.reserved_qty ?? '0'}
          onStage={handleStage}
        />
      ) : null}

      {historyRow ? (
        <ReserveLineHistoryDialog
          open
          onOpenChange={(next) => {
            if (!next) setHistoryRow(null);
          }}
          itemCode={historyRow.item_code ?? null}
          entries={historyQuery.data ?? []}
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
