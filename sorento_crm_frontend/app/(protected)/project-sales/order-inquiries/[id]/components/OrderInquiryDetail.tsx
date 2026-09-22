'use client';

import { useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  Ban,
  Download,
  FileText,
  Link2,
  ListOrdered,
  ShoppingCart,
  Ship,
  Unlink,
  Undo2,
  Wand2,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import BackToList from '@/components/common/BackToList';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
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
  orderInquiryHeadersPagerQuery,
  useAutoPlaceOrderInquiryRows,
  useOrderInquiryHandshake,
  useOrderInquiryHeaderDetail,
  useOrderInquiryHeaderLines,
  useOrderInquiryHeaderRelatedDocuments,
} from '../../../_shared/hooks/useOrderInquiry';
import { ackStateOf } from '../../../_shared/lib/orderInquiryAck';
import {
  orderInquiryHeaderStatusLabel,
  orderInquiryHeaderStatusVariant,
} from '../../../_shared/lib/orderInquiryHeaderStatus';
import { saveBlobAs } from '../../../_shared/services/fileDownload';
import { downloadOrderInquiryWorklistXlsx } from '../../../_shared/services/orderInquiryService';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';
import { OrderInquiryLinesTab } from './OrderInquiryLinesTab';
import { OrderInquiryGeneralTab } from './OrderInquiryGeneralTab';
import {
  OrderInquiryRelatedPurchaseOrdersTab,
  OrderInquiryRelatedSposTab,
} from './OrderInquiryRelatedDocumentsTab';

/** Same grant the worklist gates Choose document / Link / Unlink / Reject / Unconfirm
 * on (`OrderInquiriesClient.tsx`). */
const ORDER_INQUIRY_ACTION_PERMISSION = 'projects.order_inquiry.action';
/** Same grant Confirm is gated on everywhere else in this module. */
const ORDER_INQUIRY_ACKNOWLEDGE_PERMISSION = 'projects.order_inquiries.acknowledge';

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

  const headerQuery = useOrderInquiryHeaderDetail(id);
  const linesQuery = useOrderInquiryHeaderLines(id);
  const relatedQuery = useOrderInquiryHeaderRelatedDocuments(id);
  const { acknowledge, unacknowledge } = useOrderInquiryHandshake();
  const autoPlace = useAutoPlaceOrderInquiryRows();

  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
  const [chooseDocumentOpen, setChooseDocumentOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
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

  async function handleExport() {
    if (!header) return;
    setExporting(true);
    try {
      // W: filtered by `inquiry_id`, the plan's own contract - every non-cancelled row
      // of exactly this header, the same filter the Lines tab itself reads by.
      const blob = await downloadOrderInquiryWorklistXlsx({ inquiry_id: id });
      saveBlobAs(blob, `${header.inquiry_no}.xlsx`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export the order inquiry');
    } finally {
      setExporting(false);
    }
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
                  <DropdownMenuItem disabled={exporting} onSelect={exporting ? undefined : handleExport}>
                    <Download className="size-4" aria-hidden />
                    Export Excel
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
    </div>
  );
}

export default OrderInquiryDetail;
