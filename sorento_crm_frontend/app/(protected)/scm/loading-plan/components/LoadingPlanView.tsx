'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { ArrowLeft, LoaderCircle, Save } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DetailActions from '@/components/common/DetailActions';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { EM_DASH, fmtDate } from '../../lib/format';
import {
  loadingPlanPagerQuery,
  useContainerRequestBuild,
  useDownloadContainerRequestDocument,
  useSaveLoadingPlanEdits,
  useSendContainerRequest,
  useSupplierNotices,
  useSupplierStockListFile,
  useUpdateLoadingPlanCutOff,
} from '../../hooks/useFulfilment';
import {
  useRematchSupplierCodes,
  useUnmatchedSupplierCodes,
} from '../../hooks/useSupplierCodeAliases';
import {
  type CodedError,
  type ContainerRequestRow,
  type ContainerRequestSendOptions,
  type LoadingPlanStatus,
} from '../../services/fulfilmentService';
import { useLoadingPlanActions } from '../actions';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { SupplierCodesTab } from './SupplierCodesTab';
import { ContainerRequestSection } from './ContainerRequestSection';
import { SendRequestDialog } from './SendRequestDialog';
import { SentRequestsPanel } from './SentRequestsPanel';
import { requestLinesFrom } from './containerRequestSummary';
import { copyPublicLink } from './copyPublicLink';
import { PageHeader } from '@/components/common/PageHeader';

/** The record's three tabs (S2): Lines (default), Supplier codes, Sent. */
type LoadingPlanTab = 'lines' | 'codes' | 'sent';
const LOADING_PLAN_TABS: LoadingPlanTab[] = ['lines', 'codes', 'sent'];

/**
 * One loading plan, as a record (R5).
 *
 * What used to be a single page holding its supplier and cut-off in React state is now a row
 * anyone can reopen, so this screen is shaped like every other detail page: a `Toolbar`
 * carrying who and when, prev/next across the list, and one right-hand cluster of actions.
 *
 * The cluster reads [pager] [gear] [Save] [Back] (S1, captain's markup 2 Sep): Send to
 * supplier is no longer a standalone button, it is a gear item (and a row menu item), one
 * `useLoadingPlanActions(plan)` hook feeding both surfaces (D15) so Cancel and Delete cannot
 * drift between them. The old header card (Supplier / Plan until / Upload / gear) is gone
 * with the ephemeral page it described, and the "What to ask" card keeps its heading only.
 *
 * Typed quantities are held HERE, not in the grid, because Save and Send both act on them and
 * both live up here. What the grid shows is `suggested_qty` with the plan's saved edits
 * already applied by the backend, plus whatever has been typed since; `engine_qty` is the
 * engine's own answer, and the map that goes to the server is every row where the two differ.
 * `Save (N)` counts something narrower: the rows that differ from what the SERVER holds
 * (`plan.line_edits`), so a cell typed back to the engine figure still counts as a change to
 * write - it clears a saved override, and against the engine figure it looked like nothing.
 */

const STATUS_LABEL: Record<LoadingPlanStatus, string> = {
  planning: 'Planning',
  sent: 'Sent',
  cancelled: 'Cancelled',
};

const STATUS_VARIANT: Record<LoadingPlanStatus, 'warning' | 'primary' | 'secondary'> = {
  planning: 'warning',
  sent: 'primary',
  cancelled: 'secondary',
};

/**
 * The three DATA-LOSS prompts below (Refresh suggestion, a new cut-off, leaving with typed
 * quantities) are `ConfirmActionDialog`, the shared non-destructive confirmation - the D7
 * carve-out AC-A6 names. They ask because something TYPED would vanish, not because the
 * record itself is on its way out: Cancel and Delete are deferred countdowns and reach for
 * no dialog at all. A local copy of the shared component briefly stood here to keep the
 * AC-I1 guard quiet; a second copy of a dialog is a second place for its behaviour to
 * drift, so the guard bans the destructive vehicles instead (SF-2).
 */

export function LoadingPlanView({ planId }: { planId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const build = useContainerRequestBuild(planId);
  const plan = build.data?.plan ?? null;
  const supplierId = plan?.supplier_id ?? '';
  const supplierName = plan?.supplier_name ?? 'this supplier';

  // Typed since the last Save. Saved edits ride back on `suggested_qty`, so this map holds
  // ONLY what has not been written yet - which is exactly what the leave-the-page prompt and
  // the "Send saves first" rule need to know about.
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [sendOpen, setSendOpen] = useState(false);
  const [cutOffOpen, setCutOffOpen] = useState(false);
  const [cutOffDraft, setCutOffDraft] = useState('');
  const [cutOffDropOpen, setCutOffDropOpen] = useState(false);
  const [refreshOpen, setRefreshOpen] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const save = useSaveLoadingPlanEdits(planId);
  const changeCutOff = useUpdateLoadingPlanCutOff(planId);
  const send = useSendContainerRequest();
  const download = useDownloadContainerRequestDocument(planId);
  // Scoped to THIS plan (R3/R11): the same supplier's other open plan has its own live
  // link and its own history, and neither belongs on this record.
  const notices = useSupplierNotices(supplierId || null, planId);
  // The sheet THIS plan was started from (BL-3). S6 stamps it on the plan at apply time, so
  // the record opens its own file rather than whatever the supplier last uploaded from some
  // other plan. A plan that predates the stamp has none, and for a stock-list plan the
  // supplier's latest is still the file it was started from, so the old lookup survives for
  // exactly that case - and runs at all only in it.
  const legacyStockList =
    plan?.document_kind === 'stock_list' && !plan?.source_attachment_id ? supplierId : null;
  const stockListFile = useSupplierStockListFile(legacyStockList || null);
  const uploadedListId = plan?.source_attachment_id ?? stockListFile.data?.attachment_id ?? null;
  const uploadedListName =
    (plan?.source_attachment_id
      ? plan.source_attachment_filename
      : stockListFile.data?.filename) ?? null;
  // The same action `RefreshMatchingButton` runs on the Supplier codes tab - the tab's
  // "Needs a decision" group empties out and that is exactly the state somebody is trying
  // to reach after adding the missing products (R18), so it is also reachable from up here.
  const rematch = useRematchSupplierCodes();
  // Read here too (S2), for the Supplier codes tab's own badge - same query key as
  // `SupplierCodesTab`, so React Query serves both callers from one fetch. Keyed on the
  // PLAN since S6: the badge counts what THIS plan's statement left unanswered.
  const { data: unmatchedCodes = [] } = useUnmatchedSupplierCodes(planId || null);

  // The tab lives in the URL (AC-B2), not component state: reload and the record's own
  // prev/next pager both have to land back on the tab she was reading. `?tab=` follows the
  // same shape ProductDetail uses - absent or unrecognised falls back to Lines, the default.
  const rawTab = searchParams?.get('tab');
  const activeTab: LoadingPlanTab = LOADING_PLAN_TABS.includes(rawTab as LoadingPlanTab)
    ? (rawTab as LoadingPlanTab)
    : 'lines';
  const handleTabChange = (tab: string) => {
    const params = new URLSearchParams(searchParams?.toString());
    if (tab === 'lines') params.delete('tab');
    else params.set('tab', tab);
    const qs = params.toString();
    router.replace(`/scm/loading-plan/${planId}${qs ? `?${qs}` : ''}`, { scroll: false });
  };

  const rows = useMemo(() => build.data?.rows ?? [], [build.data]);
  const readOnly = plan?.status === 'cancelled';

  const qtyFor = (row: ContainerRequestRow) => edits[row.row_key] ?? row.suggested_qty;
  const lines = requestLinesFrom(rows, qtyFor);
  const totalQty = lines.reduce((sum, l) => sum + l.qty, 0);

  /** The whole map that goes to the server: every row whose figure differs from the engine's,
   *  typed this session or saved in an earlier one. Not a patch - see the service. */
  const editedMap = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of rows) {
      const qty = edits[r.row_key] ?? r.suggested_qty;
      if (qty !== r.engine_qty) out[r.row_key] = qty;
    }
    return out;
  }, [rows, edits]);
  /** How many rows carry an edit at all, saved or not. What a Refresh or a new cut-off would
   *  throw away, which is why both of them ask with this number. */
  const editedCount = Object.keys(editedMap).length;

  /**
   * How many rows differ from what the SERVER holds - which is what Save writes and what
   * leaving would lose.
   *
   * Measured against `plan.line_edits`, not against the engine figure. Diffing against the
   * engine made a cell typed BACK to the engine figure look like no change at all: the map
   * lost the row (correctly - the PUT must not carry it), the count fell to zero and Save
   * went grey, so the saved override stayed on the plan and there was no way to undo it from
   * this screen. A key that is in the persisted map and not in this one is a cleared edit,
   * and it counts.
   */
  const persistedEdits = plan?.line_edits ?? {};
  const unsavedCount = (() => {
    let n = 0;
    for (const [key, qty] of Object.entries(editedMap)) {
      if (persistedEdits[key] !== qty) n += 1;
    }
    for (const key of Object.keys(persistedEdits)) {
      if (!(key in editedMap)) n += 1;
    }
    return n;
  })();
  const unsaved = unsavedCount > 0;

  // The browser's own guard for a hard navigation (close the tab, hit the address bar). The
  // in-app "Back to loading plans" gets the dialog below, which can say what is at stake.
  useEffect(() => {
    if (!unsaved) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [unsaved]);

  const stockListPreviewItems = useMemo<AttachmentPreviewItem[]>(() => {
    if (!uploadedListId) return [];
    return [
      {
        id: uploadedListId,
        name: uploadedListName || 'Stock list',
        url: '',
        downloadUrl: `/api/v1/resource-management/attachments/${uploadedListId}/download`,
      },
    ];
  }, [uploadedListId, uploadedListName]);

  const requestNotices = (notices.data ?? []).filter((n) => n.notice_type === 'container_request');
  // Only one of THIS PLAN's tokens is ever live (each send retires the plan's last), so the
  // first match IS the current ask - and with none, Copy link says why rather than copying
  // nothing.
  const liveLinkNotice = requestNotices.find((n) => !!n.public_url) ?? null;

  const goBack = () => router.push('/scm/loading-plan');

  // A link the row navigated here to open (LoadingPlanRowActions) - a row has no built lines
  // to hand the dialog itself, so it opens the record and asks it to open the dialog instead.
  useEffect(() => {
    if (searchParams?.get('send') !== '1') return;
    setSendOpen(true);
    // Only `send` goes: replacing the bare path threw away the tab she was on (`?tab=`) and
    // scrolled the record back to the top under the dialog it had just opened (SF-4).
    const params = new URLSearchParams(searchParams.toString());
    params.delete('send');
    const qs = params.toString();
    router.replace(`/scm/loading-plan/${planId}${qs ? `?${qs}` : ''}`, { scroll: false });
  }, [searchParams, planId, router]);

  // One action set, gear and row menu alike (S1, D15): Cancel and Delete are parked here
  // through the deferred-action engine (D7), and the record hands over every gear-only
  // extra it has - the row, which has none of them, ends up with just Send/Cancel/Delete.
  const { actions: planActions, pending: planPending } = useLoadingPlanActions(plan, {
    onDeleted: goBack,
    onCancelled: () => setEdits({}),
    send: {
      run: () => setSendOpen(true),
      disabled: readOnly || lines.length === 0 || totalQty <= 0 || send.isPending,
      disabledReason: readOnly ? 'This plan is cancelled.' : undefined,
    },
    changeCutOff: {
      disabled: readOnly,
      run: () => {
        setCutOffDraft(plan?.plan_horizon_date ?? '');
        setCutOffOpen(true);
      },
    },
    refreshSuggestion: {
      disabled: build.isFetching,
      run: () => (editedCount > 0 ? setRefreshOpen(true) : void build.refetch()),
    },
    refreshMatching: {
      disabled: rematch.isPending,
      run: () => rematch.mutate({ plan_id: planId }),
    },
    copyLink: {
      disabled: !liveLinkNotice,
      disabledReason: liveLinkNotice ? undefined : 'No link sent yet',
      run: () => copyPublicLink(liveLinkNotice?.public_url),
    },
    downloadXlsx: {
      disabled: lines.length === 0 || download.isPending,
      run: () => download.mutate({ lines, format: 'xlsx' }),
    },
    downloadPdf: {
      disabled: lines.length === 0 || download.isPending,
      run: () => download.mutate({ lines, format: 'pdf' }),
    },
    ...(uploadedListId ? { viewUploadedList: { run: () => setPreviewOpen(true) } } : {}),
  });

  /**
   * The new cut-off, with the typed quantities dropped first.
   *
   * A cut-off change rebuilds the suggestion against a new date, exactly as Refresh does, so
   * the typed quantities cannot survive it any more than they survive a Refresh: leaving them
   * in `edits` left the screen showing numbers the new build never produced. The saved ones
   * go too (`save.mutateAsync({})`), for the same reason Refresh clears them - a rebuild that
   * kept them would hand back the old figures.
   */
  const applyCutOff = async () => {
    if (editedCount > 0) {
      setEdits({});
      await save.mutateAsync({});
    }
    changeCutOff.mutate(cutOffDraft || null, {
      onSuccess: () => {
        setCutOffDropOpen(false);
        setCutOffOpen(false);
      },
    });
  };

  /** Send saves first (R6, AC-A15), so the document and the screen can never disagree. */
  const doSend = async (options: ContainerRequestSendOptions) => {
    if (unsavedCount > 0) {
      // A save that fails ABORTS the send. Unhandled, it left an unhandled rejection and the
      // request went out anyway, carrying quantities the plan does not hold - which is the
      // one disagreement between the document and the screen this rule exists to prevent.
      try {
        await save.mutateAsync(editedMap);
      } catch (e) {
        toast.error(
          `${(e as Error).message} The request was not sent.`.trim(),
        );
        return;
      }
    }
    send.mutate(
      { planId, supplierId, supplierName, lines, options },
      {
        onSuccess: () => {
          setEdits({});
          setSendOpen(false);
        },
      },
    );
  };

  if (build.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Card className="p-4">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="mt-3 h-40 w-full rounded-lg" />
        </Card>
      </div>
    );
  }

  if (build.isError || !plan) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <p className="text-sm font-medium text-destructive">
          {build.error?.message ?? 'This loading plan could not be opened.'}
        </p>
        <Button variant="outline" size="sm" onClick={goBack}>
          <ArrowLeft className="size-4" />
          Back to loading plans
        </Button>
      </Card>
    );
  }

  const subtitle = [
    `Started ${formatDateTimeInMalaysia(plan.started_at)}`,
    `SO cut-off ${plan.plan_horizon_date ? fmtDate(plan.plan_horizon_date) : 'none'}`,
    plan.document_label,
  ].join(' · ');

  return (
    <div className="space-y-4">
      <PageHeader
        title={plan.supplier_name ?? EM_DASH}
        titleClassName="max-w-full truncate"
        actions={
          <Button
            variant="outline"
            onClick={() => (unsaved ? setLeaveOpen(true) : goBack())}
            data-testid="back-to-plans"
          >
            <ArrowLeft className="size-4" />
            Back to loading plans
          </Button>
        }
      >
        {/* `w-full`, not just `min-w-0`: ToolbarHeading is a WRAPPING column flex container,
            so its lines are sized to their content and a long supplier name would push the
            header past the viewport at 375px instead of ellipsing. */}
        <div
          className="flex w-full min-w-0 flex-wrap items-center gap-2"
          title={plan.supplier_name ?? ''}
        >
            
          <Badge variant={STATUS_VARIANT[plan.status]} appearance="light" size="sm">
            {STATUS_LABEL[plan.status]}
          </Badge>
        </div>
        <p className="w-full text-xs text-muted-foreground" data-testid="plan-subtitle">
          {subtitle}
        </p>
      </PageHeader>

      {/* The plan's own actions: pager, gear, primary (D6, S1). They sit under the
          toolbar rather than on it, and wrap at 375. The gear renders `planActions` - the
          same array the row menu renders on the list - so Cancel and Delete never drift
          between the two surfaces (D15). */}
      <DetailActions
        className="mb-4"
        pager={{
          ...loadingPlanPagerQuery,
          detailPath: '/scm/loading-plan',
          currentId: planId,
          ariaLabel: 'loading plan',
        }}
        actions={planActions}
        gearLabel="Plan actions"
        pendingAction={planPending}
        primary={
          <Button
            variant="outline"
            disabled={readOnly || unsavedCount === 0 || save.isPending}
            title={readOnly ? 'This plan is cancelled.' : undefined}
            onClick={() => save.mutate(editedMap, { onSuccess: () => setEdits({}) })}
            data-testid="save-plan-edits"
          >
            {save.isPending ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            Save ({unsavedCount})
          </Button>
        }
      />

      {/* Three tabs (S2): what to ask (Lines, default), the codes her file named that our
          catalogue does not (Supplier codes), and what has already gone out (Sent). The
          toolbar above never moves between them - Save and Send both act on the Lines tab's
          edits no matter which tab is open. */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start">
          <TabsTrigger value="lines">Lines</TabsTrigger>
          <TabsTrigger value="codes">
            Supplier codes{unmatchedCodes.length ? ` (${unmatchedCodes.length})` : ''}
          </TabsTrigger>
          <TabsTrigger value="sent">
            Sent{requestNotices.length ? ` (${requestNotices.length})` : ''}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="lines">
          <ContainerRequestSection
            planId={planId}
            supplierId={supplierId}
            supplierName={supplierName}
            qtyFor={qtyFor}
            onQtyChange={(rowKey, qty) => setEdits((prev) => ({ ...prev, [rowKey]: qty }))}
            readOnly={readOnly}
          />
        </TabsContent>

        <TabsContent value="codes">
          {/* The queue of codes this supplier's file names and our catalogue does not, AND
              the supplier's memory of every ruling ever made (S3) - both always render, so
              the Remembered list is reachable even once the queue itself is answered down to
              nothing; the tab's own empty states cover each half. */}
          <SupplierCodesTab
            planId={planId}
            supplierId={supplierId}
            documentKind={plan.document_kind}
            documentLabel={plan.document_label}
            statementAsOf={plan.statement_as_of}
          />
        </TabsContent>

        <TabsContent value="sent">
          <SentRequestsPanel
            supplierName={supplierName}
            notices={requestNotices}
            onSend={() => setSendOpen(true)}
            sendDisabled={readOnly || lines.length === 0 || totalQty <= 0 || send.isPending}
            sendDisabledReason={readOnly ? 'This plan is cancelled.' : undefined}
          />
        </TabsContent>
      </Tabs>

      <SendRequestDialog
        open={sendOpen}
        onOpenChange={(next) => {
          setSendOpen(next);
          // A refusal belongs to the send that was refused: reopening the dialog must not
          // greet her with the reason the LAST attempt failed.
          if (!next) send.reset();
        }}
        supplierId={supplierId}
        supplierName={supplierName}
        supplierEmail={plan.supplier_email}
        lineCount={lines.length}
        totalQty={totalQty}
        unsavedCount={unsavedCount}
        isBusy={send.isPending || save.isPending}
        error={(send.error as CodedError | null) ?? null}
        onSend={({ channel, recipients, chatContactId, note }) =>
          void doSend({
            channel,
            recipients,
            chatContactId: chatContactId ?? undefined,
            note,
          })
        }
      />

      <ConfirmActionDialog
        open={refreshOpen}
        onOpenChange={setRefreshOpen}
        title={`Drop your ${editedCount} typed ${editedCount === 1 ? 'quantity' : 'quantities'}?`}
        description="A fresh suggestion is the system looking again, so it replaces what was typed rather than ranking around it."
        confirmLabel="Refresh suggestion"
        isBusy={save.isPending || build.isFetching}
        onConfirm={() => {
          setEdits({});
          // The saved edits go too: "refresh" that kept them would return the same numbers.
          void save.mutateAsync({}).then(() => {
            setRefreshOpen(false);
            void build.refetch();
          });
        }}
      />

      <ConfirmActionDialog
        open={cutOffDropOpen}
        onOpenChange={setCutOffDropOpen}
        title={`Drop your ${editedCount} typed ${editedCount === 1 ? 'quantity' : 'quantities'}?`}
        description="A new cut-off is worked out from scratch against the new date, so it replaces what was typed rather than ranking around it."
        confirmLabel="Change the cut-off"
        isBusy={save.isPending || changeCutOff.isPending}
        onConfirm={() => void applyCutOff()}
      />

      <ConfirmActionDialog
        open={leaveOpen}
        onOpenChange={setLeaveOpen}
        title="Leave without saving?"
        description={`${unsavedCount} changed ${unsavedCount === 1 ? 'quantity is' : 'quantities are'} not saved yet. Leaving ${unsavedCount === 1 ? 'loses it' : 'loses them'}.`}
        confirmLabel="Leave"
        isBusy={false}
        onConfirm={goBack}
      />

      <Dialog open={cutOffOpen} onOpenChange={setCutOffOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Change the sales order cut-off</DialogTitle>
            <DialogDescription>
              The suggestion is worked out again against the new date.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-2">
            <Label htmlFor="plan-cutoff" className="text-xs">
              Sales order cut-off
            </Label>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                id="plan-cutoff"
                type="date"
                className="w-44"
                value={cutOffDraft}
                onChange={(e) => setCutOffDraft(e.target.value)}
              />
              {cutOffDraft ? (
                <Button variant="ghost" size="sm" onClick={() => setCutOffDraft('')}>
                  Clear
                </Button>
              ) : null}
            </div>
            <p className="text-2xs text-muted-foreground">Empty = every open order counts.</p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCutOffOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={changeCutOff.isPending || save.isPending}
              onClick={() => (editedCount > 0 ? setCutOffDropOpen(true) : void applyCutOff())}
            >
              {changeCutOff.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Save cut-off
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={stockListPreviewItems}
      />
    </div>
  );
}

export default LoadingPlanView;
