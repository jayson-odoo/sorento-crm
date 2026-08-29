'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Ban,
  CalendarDays,
  Download,
  Eye,
  FileText,
  Link2,
  LoaderCircle,
  RefreshCw,
  Save,
  Send,
  Settings,
  Trash2,
} from 'lucide-react';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import ListPager from '@/components/common/ListPager';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { EM_DASH, fmtDate } from '../../lib/format';
import {
  loadingPlanPagerQuery,
  useCancelLoadingPlan,
  useContainerRequestBuild,
  useDownloadContainerRequestDocument,
  useSaveLoadingPlanEdits,
  useSendContainerRequest,
  useSupplierNotices,
  useSupplierStockListFile,
  useUpdateLoadingPlanCutOff,
} from '../../hooks/useFulfilment';
import { useRematchSupplierCodes } from '../../hooks/useSupplierCodeAliases';
import {
  deleteLoadingPlan,
  type CodedError,
  type ContainerRequestRow,
  type ContainerRequestSendOptions,
  type LoadingPlanStatus,
} from '../../services/fulfilmentService';
import { UnmatchedSupplierCodesPanel } from './UnmatchedSupplierCodesPanel';
import { ContainerRequestSection } from './ContainerRequestSection';
import { SendRequestDialog } from './SendRequestDialog';
import { requestLinesFrom } from './containerRequestSummary';
import { copyPublicLink } from './copyPublicLink';

/**
 * One loading plan, as a record (R5).
 *
 * What used to be a single page holding its supplier and cut-off in React state is now a row
 * anyone can reopen, so this screen is shaped like every other detail page: a `Toolbar`
 * carrying who and when, prev/next across the list, and one right-hand cluster of actions.
 *
 * The cluster reads [gear] [Save] [Send to supplier] [Back], gear FIRST. Send is the errand;
 * the gear holds the things done occasionally, and putting it on the left keeps the errand at
 * the end of the row where the eye stops. The old header card (Supplier / Plan until / Upload
 * / gear) is gone with the ephemeral page it described, and the "What to ask" card keeps its
 * heading only.
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

export function LoadingPlanView({ planId }: { planId: string }) {
  const router = useRouter();
  const build = useContainerRequestBuild(planId);
  const plan = build.data?.plan ?? null;
  const supplierId = plan?.supplier_id ?? '';
  const supplierName = plan?.supplier_name ?? 'this supplier';

  // Typed since the last Save. Saved edits ride back on `suggested_qty`, so this map holds
  // ONLY what has not been written yet - which is exactly what the leave-the-page prompt and
  // the "Send saves first" rule need to know about.
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [cancelOpen, setCancelOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
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
  const cancel = useCancelLoadingPlan();
  const download = useDownloadContainerRequestDocument(planId);
  // Scoped to THIS plan (R3/R11): the same supplier's other open plan has its own live
  // link and its own history, and neither belongs on this record.
  const notices = useSupplierNotices(supplierId || null, planId);
  const stockListFile = useSupplierStockListFile(
    plan?.document_kind === 'stock_list' ? supplierId : null,
  );
  // The same action `RefreshMatchingButton` runs on the queue panel - the panel hides itself
  // when every code binds, and that is exactly the state somebody is trying to reach after
  // adding the missing products (R18), so it is also reachable from up here.
  const rematch = useRematchSupplierCodes();


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
    const id = stockListFile.data?.attachment_id;
    if (!id) return [];
    return [
      {
        id,
        name: stockListFile.data?.filename || 'Stock list',
        url: '',
        downloadUrl: `/api/v1/resource-management/attachments/${id}/download`,
      },
    ];
  }, [stockListFile.data]);

  const requestNotices = (notices.data ?? []).filter((n) => n.notice_type === 'container_request');
  // Only one of THIS PLAN's tokens is ever live (each send retires the plan's last), so the
  // first match IS the current ask - and with none, Copy link says why rather than copying
  // nothing.
  const liveLinkNotice = requestNotices.find((n) => !!n.public_url) ?? null;

  const goBack = () => router.push('/scm/loading-plan');

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
      <Toolbar>
        <ToolbarHeading className="min-w-0">
          {/* `w-full`, not just `min-w-0`: ToolbarHeading is a WRAPPING column flex container,
              so its lines are sized to their content and a long supplier name would push the
              header past the viewport at 375px instead of ellipsing. */}
          <div
            className="flex w-full min-w-0 flex-wrap items-center gap-2"
            title={plan.supplier_name ?? ''}
          >
            <ToolbarTitle className="min-w-0 max-w-full truncate">
              {plan.supplier_name ?? EM_DASH}
            </ToolbarTitle>
            <Badge variant={STATUS_VARIANT[plan.status]} appearance="light" size="sm">
              {STATUS_LABEL[plan.status]}
            </Badge>
          </div>
          <p className="w-full text-xs text-muted-foreground" data-testid="plan-subtitle">
            {subtitle}
          </p>
        </ToolbarHeading>
        <ToolbarActions>
          <Button
            variant="outline"
            onClick={() => (unsaved ? setLeaveOpen(true) : goBack())}
            data-testid="back-to-plans"
          >
            <ArrowLeft className="size-4" />
            Back to loading plans
          </Button>
        </ToolbarActions>
      </Toolbar>

      {/* The plan's own actions: pager, gear, primary (D6). They sit under the
          toolbar rather than on it, and wrap at 375. */}
      <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
          <ListPager
            {...loadingPlanPagerQuery}
            detailPath="/scm/loading-plan"
            currentId={planId}
            ariaLabel="loading plan"
          />

          {/* Everything that is not the errand. ONE gear on this screen (R5): the card below
              used to carry a second one, which made "the plan's actions" two menus deep. */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                aria-label="Plan actions"
                data-testid="plan-actions"
              >
                <Settings className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {stockListFile.data?.attachment_id ? (
                <DropdownMenuItem onSelect={() => setPreviewOpen(true)}>
                  <Eye className="size-4" />
                  View uploaded list
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem
                disabled={rematch.isPending}
                onSelect={() => rematch.mutate({ supplier_id: supplierId })}
                data-testid="refresh-matching-item"
              >
                <RefreshCw className="size-4" />
                Refresh matching
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={build.isFetching}
                onSelect={() => (editedCount > 0 ? setRefreshOpen(true) : void build.refetch())}
              >
                <RefreshCw className="size-4" />
                Refresh suggestion
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={!liveLinkNotice}
                title={liveLinkNotice ? undefined : 'No link sent yet'}
                onSelect={() => void copyPublicLink(liveLinkNotice?.public_url)}
              >
                <Link2 className="size-4" />
                Copy link
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={lines.length === 0 || download.isPending}
                onSelect={() => download.mutate({ lines, format: 'xlsx' })}
              >
                <Download className="size-4" />
                Download XLSX
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={lines.length === 0 || download.isPending}
                onSelect={() => download.mutate({ lines, format: 'pdf' })}
              >
                <FileText className="size-4" />
                Download PDF
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={readOnly}
                onSelect={() => {
                  setCutOffDraft(plan.plan_horizon_date ?? '');
                  setCutOffOpen(true);
                }}
              >
                <CalendarDays className="size-4" />
                Change cut-off
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                disabled={readOnly}
                onSelect={() => setCancelOpen(true)}
              >
                <Ban className="size-4" />
                Cancel plan
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                disabled={!!plan.sent_at}
                title={plan.sent_at ? 'Sent plans are cancelled, not deleted' : undefined}
                onSelect={() => setDeleteOpen(true)}
              >
                <Trash2 className="size-4" />
                Delete plan
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

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

          <Button
            disabled={readOnly || lines.length === 0 || totalQty <= 0 || send.isPending}
            title={readOnly ? 'This plan is cancelled.' : undefined}
            onClick={() => setSendOpen(true)}
            data-testid="send-to-supplier"
          >
            {send.isPending ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
            Send to supplier
          </Button>

      </div>

      {/* The queue of codes this supplier's file names and our catalogue does not - the stock
          behind them is invisible to the plan below until somebody answers them. */}
      <UnmatchedSupplierCodesPanel supplierId={supplierId} />

      <ContainerRequestSection
        planId={planId}
        supplierId={supplierId}
        supplierName={supplierName}
        qtyFor={qtyFor}
        onQtyChange={(rowKey, qty) => setEdits((prev) => ({ ...prev, [rowKey]: qty }))}
        readOnly={readOnly}
      />

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
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel this plan?"
        description="The supplier link stops working. The plan stays on the list under the Cancelled filter."
        confirmLabel="Cancel plan"
        isBusy={cancel.isPending}
        onConfirm={() =>
          cancel.mutate(planId, {
            onSuccess: () => {
              setCancelOpen(false);
              setEdits({});
            },
          })
        }
      />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this plan?"
        description={
          <>
            {plan.supplier_name ?? 'This plan'}, started{' '}
            {formatDateTimeInMalaysia(plan.started_at)}. The plan and the quantities typed on it
            are removed. This cannot be undone.
          </>
        }
        successMessage="Plan deleted"
        onDelete={() => deleteLoadingPlan(planId)}
        onSuccess={goBack}
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
              Save
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
