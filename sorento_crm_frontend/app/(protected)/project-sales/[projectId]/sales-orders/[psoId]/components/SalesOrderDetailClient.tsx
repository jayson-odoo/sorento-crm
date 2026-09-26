'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ClipboardList,
  Download,
  FileDiff,
  GitCompareArrows,
  RotateCcw,
  Send,
  Shuffle,
  SquarePen,
  Table2,
  Trash2,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
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
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import DetailActions from '@/components/common/DetailActions';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useAcknowledgeScheduleFinding,
  useProjectSalesOrder,
  useScheduleFindings,
  useScheduleVersions,
  useSalesOrderDelete,
  useSalesOrderImportFile,
  useSalesOrderMutations,
  projectSalesOrdersPagerQuery,
} from '../../../../_shared/hooks/useProjectSalesOrders';
import { useProject } from '../../../../_shared/hooks/useProjects';
import { useReviewOriginHref } from '../../../../_shared/hooks/useReviewOrigin';
import { useOpenDivergenceForOrder } from '../../../../_shared/hooks/useSoDivergence';
import {
  buildFlagItems,
  needsAttention,
  publishBlockers,
  type FlagItem,
} from '../../../../_shared/lib/findings';
import { DismissReasonDialog } from '../../../components/DismissReasonDialog';
import { SalesOrderLinesTable } from '../../../components/SalesOrderLinesTable';
import { formatMoney, sumMoney } from '../../../components/SalesOrderMoney';
import { SalesOrderPublishDialog } from '../../../components/SalesOrderPublishDialog';
import { SalesOrderRegroupDialog } from '../../../components/SalesOrderRegroupDialog';
import { SalesOrderStatusPill } from '../../../components/SalesOrderStatusPill';
import { ReviewStatePill } from '../../../../_shared/components/ReviewStatePill';
import { AllocationPanel } from './AllocationPanel';
import { useSalesOrderEditSession } from './useSalesOrderEditSession';

/**
 * One draft, reviewed rather than authored - and, once Edit is pressed, corrected.
 *
 * S7 (`mockups/sales-order-review.html`): the header says where the order came from and, under
 * Publish, how many findings block it; then two tabs, Lines and AutoCount differences. Lines
 * is ONE table: a finding is a Flag on the row it concerns, from this order or from the
 * schedule it was split from, cleared with one Dismiss (R16, R20). No findings cards, no
 * refusal banner, no Findings tab.
 *
 * READ AND EDIT ARE THE SAME SCREEN. Pressing Edit changes no section, moves no field and
 * hides nothing: the header keeps its identity block, "This sales order" keeps all nine
 * facts with the one editable field swapped for an input where it already stood, and the
 * lines keep their card, their heading and their eleven columns in the same order. Nothing is
 * written until Save, which is one request for the header and every line together - the same
 * arrangement the quotation document uses, and for the same reason the client gave for it:
 * "every addition of line doesn't trigger a save ... very annoying".
 */
export function SalesOrderDetailClient({
  projectId,
  psoId,
}: {
  projectId: string;
  psoId: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  // S4: Publish returns the user to where they came from. With no origin (a deep link or a
  // bookmark) it stays on the page, as before this slice. Routed through the shared hook (S1)
  // so a crafted external `from` is rejected the same way every other review page rejects it.
  const originHref = useReviewOriginHref();
  const project = useProject(projectId);
  const salesOrder = useProjectSalesOrder(psoId);
  const { acknowledge, save, regroup, publish, unpublish, reorderLines } = useSalesOrderMutations(
    projectId,
    psoId,
  );
  const removeOrder = useSalesOrderDelete(projectId);
  const importFile = useSalesOrderImportFile(psoId);
  const edit = useSalesOrderEditSession(
    salesOrder.data ? { area_group: salesOrder.data.area_group } : undefined,
  );
  // The pager's set is the project's own sales orders, in the order the tab lists them.
  // Called above the early returns, as every hook must be. Keyed on the order's
  // `updated_at` so an ingest or a publish refetches it: this is what disables the amend
  // button, and a stale answer either blocks a clean order or lets a wrong amendment past.
  const { divergence } = useOpenDivergenceForOrder(psoId, salesOrder.data?.updated_at);
  // The (PO, schedule) pair's OWN findings, not this order's: see `ScheduleFindingsSection`
  // for why a finding naming no PO line cannot be shown as if it belonged to one order.
  const scheduleFindings = useScheduleFindings(
    salesOrder.data?.purchase_order_id,
    salesOrder.data?.schedule_version_id,
  );
  const acknowledgeScheduleFinding = useAcknowledgeScheduleFinding(
    salesOrder.data?.purchase_order_id,
    salesOrder.data?.schedule_version_id,
  );
  // Only for the PO version the header names: the schedule version this order was split from
  // records which PO version it was reconciled against.
  const scheduleVersions = useScheduleVersions(salesOrder.data?.purchase_order_id ?? undefined);

  const [dismissing, setDismissing] = React.useState<FlagItem | null>(null);
  const [tab, setTab] = React.useState<'lines' | 'autocount' | null>(null);
  const [regrouping, setRegrouping] = React.useState(false);
  const [publishing, setPublishing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [confirmUnpublish, setConfirmUnpublish] = React.useState(false);
  const [confirmRemovals, setConfirmRemovals] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);

  /**
   * `?edit=1` opens the session on arrival, so the list's Edit lands the user in the same one
   * screen rather than in a second form that collects the same fields. Fired once: re-running
   * it after Cancel would put the user straight back into the session they just left.
   *
   * The same entry the customer PO list uses, so the two records behave identically.
   */
  const wantsEdit = searchParams.get('edit') === '1';
  const canEditProject = project.data?.can_edit ?? false;
  // A published order is refused by the server, so a link carrying `?edit=1` must not open a
  // session on one: the user would type into a screen that cannot save. Read off the loaded
  // row, so the check waits for the answer rather than guessing before it arrives.
  const loadedStatus = salesOrder.data?.status;
  const isDraftStatus =
    Boolean(loadedStatus) && loadedStatus !== 'published' && loadedStatus !== 'amended';
  const opened = React.useRef(false);
  const begin = edit.begin;
  React.useEffect(() => {
    if (!wantsEdit || opened.current || !canEditProject || !isDraftStatus) return;
    opened.current = true;
    begin();
  }, [begin, canEditProject, isDraftStatus, wantsEdit]);

  /**
   * Warn before the browser throws the staged work away.
   *
   * Only covers leaving the SITE (a refresh, a closed tab, an external link): there is nowhere
   * else on this screen to go, and the session lives above the line table so a findings filter
   * or a refetch does not touch it.
   */
  const isDirty = edit.isDirty;
  React.useEffect(() => {
    if (!isDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isDirty]);

  if (salesOrder.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (salesOrder.isError || !salesOrder.data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This sales order could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {salesOrder.error instanceof Error
            ? salesOrder.error.message
            : 'It may have been rebuilt or deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href={`/project-sales/${projectId}?tab=sales-orders`}>Back to sales orders</Link>
        </Button>
      </div>
    );
  }

  const so = salesOrder.data;
  /**
   * The order as the SCREEN currently stands: the server's row with whatever header edit is
   * staged merged over it.
   *
   * Merged here, once, rather than per field, because two places read the area group - the
   * line under the title and the field in the card - and a session that only reached one of
   * them would have the card naming one group while the heading above it named another.
   */
  const shown = { ...so, ...edit.headerDraft };
  const reference = so.autocount_doc_no || so.provisional_ref;
  const canEdit = project.data?.can_edit ?? false;
  const findings = so.findings ?? [];
  const lines = so.lines ?? [];

  // The one rule the server's own gate applies (owner lesson (e)): the count under Publish,
  // the dialog's refusal and the Need attention rows are all read off this.
  const blocking = publishBlockers(findings);
  const unacknowledgedWarnings = findings.filter(
    (finding) => finding.severity === 'warn' && !finding.acknowledged_at,
  );
  const isPublished = so.status === 'published' || so.status === 'amended';
  const flagItems = buildFlagItems(findings, scheduleFindings.data ?? []);
  const anythingOpen = flagItems.some(needsAttention);
  // S7-2: Lines while anything is open or the order is not in AutoCount yet; otherwise the
  // AutoCount comparison is the work left, until the reader picks a tab themselves.
  const activeTab = tab ?? (anythingOpen || !isPublished ? 'lines' : 'autocount');
  const poVersionNo = scheduleVersions.data?.find(
    (version) => version.id === so.schedule_version_id,
  )?.po_version_no;
  const canDismiss =
    canEdit && !edit.isEditing
      ? (item: FlagItem) =>
          // A published order's own findings are the server's to refuse; a schedule's are not
          // any one order's, so they stay dismissable from here.
          !isPublished || item.members.every((member) => member.source === 'schedule')
      : null;

  /**
   * One reason, every open finding the item stands for, each through its own endpoint. Calls run
   * one after another, so a failed second call leaves the first acknowledged: the refetch then
   * shows the rest as an open item of its own, dismissable again, and nothing is lost.
   */
  async function dismissItem(item: FlagItem, reason: string) {
    for (const member of item.members) {
      if (member.finding.acknowledged_at) continue;
      if (member.source === 'schedule') {
        await acknowledgeScheduleFinding.mutateAsync({ findingId: member.finding.id, reason });
      } else {
        await acknowledge.mutateAsync({ findingId: member.finding.id, reason });
      }
    }
  }
  // The route's own gate: draft, blocked (on a finding) or ready to publish. Narrower than
  // `!isPublished` alone, because `awaiting_costing` (sponsorship) is neither published nor
  // reorderable - the server 409s it, so the handle is not offered for it either.
  const isReorderableStatus =
    so.status === 'draft' || so.status === 'blocked' || so.status === 'ready';
  /**
   * A draft nobody here may edit has no publish and no AutoCount answer to give, so the one
   * thing left to do with it is read it - and the worksheet then leaves the gear, because an
   * action cannot be the call to action AND a menu item.
   */
  const worksheetIsPrimary = !isPublished && !canEdit;
  // The server owns the export gate. `can_export` is optional so a row cached from before
  // it shipped still offers the download it used to.
  const canExport = so.can_export ?? Boolean(so.import_file_url);

  // Summed from the line amounts as decimal strings so the figure can be read straight off
  // the printed order. `total_amount` is shown beside it and disagreement is worth seeing.
  const lineSum = sumMoney(lines.map((line) => line.amount));

  /**
   * The whole order in ONE write.
   *
   * The session only ever puts a key in the body for something somebody actually changed, so
   * an untouched header field cannot be blanked and untouched lines are not rewritten.
   */
  async function runSave() {
    setIsSaving(true);
    try {
      await save.mutateAsync(edit.body);
      edit.cancel();
      toast.success('Sales order saved');
    } catch {
      // The mutation toasted the reason, and the session is deliberately left open: what was
      // typed is still on screen and still saveable.
    } finally {
      setIsSaving(false);
    }
  }

  function requestSave() {
    // A line the server would refuse is caught here rather than after a write has landed. The
    // cell is already marked; this says how many are outstanding.
    if (edit.unfinishedCount > 0) {
      toast.error(
        edit.unfinishedCount === 1
          ? 'One line still needs a quantity, and a product or a description.'
          : `${edit.unfinishedCount} lines still need a quantity, and a product or a description.`,
      );
      return;
    }
    // The edit view's ONE destructive confirmation. Staging a removal destroyed nothing, so it
    // asked nothing; this is the moment lines actually leave the order.
    if (edit.removedCount > 0) {
      setConfirmRemovals(true);
      return;
    }
    void runSave();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold break-words">{reference}</h2>
            <SalesOrderStatusPill status={so.status} />
            {/* Beside the status rather than folded into it: an order can be published AND
                still awaiting reconciliation, and the header has to be able to say both.
                Renders nothing until the backend derives the state. */}
            <ReviewStatePill state={so.review_state} exceptionCount={so.exception_count} />
            {so.is_pre_order && (
              <Badge variant="secondary" appearance="light">
                Pre-order
              </Badge>
            )}
            {so.is_sponsorship && (
              <Badge variant="secondary" appearance="light">
                Sponsorship
              </Badge>
            )}
          </div>
          {/* S7-1: where the order came from, and Activity as a plain link rather than a tab. */}
          <p className="mt-1 text-sm text-muted-foreground break-words">
            {[
              project.data?.title
                ? project.data.project_code
                  ? `${project.data.title} (${project.data.project_code})`
                  : project.data.title
                : null,
              `Area group ${shown.area_group || '-'}`,
              `Customer PO ${so.po_number || '-'}${poVersionNo ? ` v${poVersionNo}` : ''}`,
              so.stock_location ? `Stock location ${so.stock_location}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
            {/* PR #1264 note 3: derived from the sales agent's location group, never picked.
                When a link in that chain is missing it is a flag naming the link, not a
                picker. */}
            {!so.stock_location && so.stock_location_gap && (
              <>
                {' · '}
                <Badge
                  variant="warning"
                  appearance="light"
                  size="sm"
                  title={so.stock_location_gap}
                >
                  No stock location
                </Badge>
              </>
            )}
            {' · '}
            <Link
              href={`/project-sales/${projectId}?tab=activity`}
              className="text-primary hover:underline"
            >
              View activity
            </Link>
          </p>
          {edit.isEditing && (
            <p className="mt-1 text-xs text-muted-foreground">
              Nothing is written until you press Save.
            </p>
          )}
        </div>

        {/* In an edit session the header states ONE intent, and it is Save or Cancel: the
            worksheet, the revision, the publish and the export all act on the order as it is
            STORED, and offering them over a screen full of unsaved changes is offering to act
            on a document nobody is looking at. */}
        {edit.isEditing ? (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isSaving}
              onClick={() => edit.cancel()}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={isSaving || !edit.isDirty}
              title={edit.isDirty ? undefined : 'Nothing has changed yet'}
              onClick={requestSave}
            >
              {isSaving ? 'Saving...' : 'Save sales order'}
            </Button>
          </div>
        ) : (
        /* Pager, gear, primary (D6), through the shared group rather than a
           hand-rolled row: the order is the same rule on all 39 detail pages, and
           a copy of it here is a copy that can drift. */
        <DetailActions
          pager={{
            ...projectSalesOrdersPagerQuery(projectId),
            detailPath: `/project-sales/${projectId}/sales-orders`,
            currentId: psoId,
            ariaLabel: 'sales order',
          }}
          gear={
            /* ONE call to action stands in this header, and everything else is behind the
                gear. The row of buttons this replaced competed with each other, so the thing
                the reader actually came to do was the hardest to find. The gear always has
                at least the revision review in it, so it is never an empty menu. */
            <DetailActionsMenu ariaLabel="Sales order actions">
              {!worksheetIsPrimary && (
                <DropdownMenuItem asChild>
                  <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/worksheet`}>
                    <Table2 className="size-4" aria-hidden />
                    Worksheet
                  </Link>
                </DropdownMenuItem>
              )}
              {/* Disabled rather than hidden while a difference is open: the reviewer has to
                  learn WHY they cannot amend, and an item that vanished teaches nothing.
                  The server refuses it too (AC-N5) - this only saves the round trip. */}
              {divergence ? (
                <DropdownMenuItem disabled>
                  <GitCompareArrows className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Review a revision
                    <span className="block text-xs text-muted-foreground">
                      Reconcile the AutoCount differences first
                    </span>
                  </span>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem asChild>
                  <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/revisions`}>
                    <GitCompareArrows className="size-4" aria-hidden />
                    Review a revision
                  </Link>
                </DropdownMenuItem>
              )}
              {isPublished && (
                <DropdownMenuItem asChild>
                  <Link href={`/project-sales/${projectId}/order-inquiries`}>
                    <ClipboardList className="size-4" aria-hidden />
                    Order inquiry
                  </Link>
                </DropdownMenuItem>
              )}
              {/* Experimental at this stage (captain, 19 Aug 2026): a published or amended
                  order may go back to draft. The server refuses it 409 once anything has
                  already acted on the published state - the confirm names what that is. */}
              {canEdit && isPublished && (
                <DropdownMenuItem onSelect={() => setConfirmUnpublish(true)}>
                  <RotateCcw className="size-4" aria-hidden />
                  Unpublish
                </DropdownMenuItem>
              )}
              {canEdit && !isPublished && (
                <DropdownMenuItem
                  disabled={lines.length === 0}
                  onSelect={() => setRegrouping(true)}
                >
                  <Shuffle className="size-4" aria-hidden />
                  Move lines
                </DropdownMenuItem>
              )}
              {/* Offered while the order has a file, disabled while the server refuses it: the
                  route 422s an export the gate has not cleared, and an item that vanished
                  would not say that a blocking finding is what took it away. */}
              {so.import_file_url && (
                <DropdownMenuItem
                  disabled={!canExport || importFile.isPending}
                  onSelect={() => importFile.mutate(so.provisional_ref)}
                >
                  <Download className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Import file
                    {!canExport && (
                      <span className="block text-xs text-muted-foreground">
                        Clear the blocking findings first
                      </span>
                    )}
                  </span>
                </DropdownMenuItem>
              )}
              {/* Edit's ENTRY POINT. Only the way IN is here: once a session is open, Cancel
                  and Save are the header's controls, up above. */}
              {canEdit && (
                <DropdownMenuItem
                  disabled={isPublished}
                  onSelect={() => edit.begin()}
                >
                  <SquarePen className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Edit this sales order
                    {isPublished && (
                      <span className="block text-xs text-muted-foreground">
                        Published, so raise a revision instead
                      </span>
                    )}
                  </span>
                </DropdownMenuItem>
              )}
              {/* Destructive last, and behind a separator. Disabled rather than absent on a
                  published order: the reviewer has to learn WHY it cannot be deleted, and a
                  menu that simply lacks the item reads as "this system cannot do it". The
                  server refuses it too. */}
              {canEdit && <DropdownMenuSeparator />}
              {canEdit && (
                <DropdownMenuItem
                  variant="destructive"
                  disabled={isPublished}
                  onSelect={() => setConfirmDelete(true)}
                >
                  <Trash2 className="size-4" aria-hidden />
                  <span className="min-w-0">
                    Delete this sales order
                    {isPublished && (
                      <span className="block text-xs text-muted-foreground">
                        In AutoCount, so amend it instead
                      </span>
                    )}
                  </span>
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          }
          primary={
            <>
              {/* The one thing this status is waiting for: publish a draft somebody may edit,
                  answer AutoCount on a published order, and - for a reader who can do neither -
                  read the order as AutoCount will. */}
              {canEdit && !isPublished ? (
                <span className="inline-flex flex-col items-end gap-1">
                  <Button type="button" size="sm" onClick={() => setPublishing(true)}>
                    <Send className="size-4" aria-hidden />
                    Publish
                  </Button>
                  {/* S7-1: the gate, stated once, where the refusal banner used to stand. */}
                  {blocking.length > 0 && (
                    <span className="text-xs text-destructive">
                      {`${blocking.length} block${blocking.length === 1 ? 's' : ''} publish`}
                    </span>
                  )}
                </span>
              ) : isPublished ? (
                <Button asChild size="sm">
                  <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/divergence`}>
                    <FileDiff className="size-4" aria-hidden />
                    {divergence ? 'Reconcile AutoCount' : 'Compare with AutoCount'}
                  </Link>
                </Button>
              ) : (
                <Button asChild size="sm">
                  <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/worksheet`}>
                    <Table2 className="size-4" aria-hidden />
                    Worksheet
                  </Link>
                </Button>
              )}
            </>
          }
        />
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">This sales order</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* The one header field a person may change, so it renders in BOTH views and the
              input takes the value's place where it already stood. Everything beside it is
              read-only metadata - refs, counts, the two timestamps - which has no edit
              counterpart and is why it belongs in this strip rather than in a form. */}
          <Field
            label="Area group"
            value={shown.area_group || '-'}
            editing={edit.isEditing}
            editValue={shown.area_group ?? ''}
            placeholder="e.g. TOWER"
            maxLength={80}
            onChange={(next) => edit.stageHeader({ area_group: next })}
          />
          <Field label="Billed to" value={so.customer_name || '-'} />
          <Field label="Lines" value={so.line_count.toLocaleString()} />
          <Field label="Value" value={formatMoney(so.total_amount)} />
          <Field
            label="Sum of the lines"
            value={lines.length > 0 ? formatMoney(lineSum) : '-'}
          />
          <Field
            label="Drafted"
            value={so.created_at ? formatDateInMalaysia(so.created_at) : '-'}
          />
          <Field
            label="Published"
            value={so.published_at ? formatDateInMalaysia(so.published_at) : '-'}
          />
          <Field
            label="AutoCount document"
            value={so.autocount_doc_no || '-'}
          />
          <Field label="Reference we raised" value={so.provisional_ref || '-'} />
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={(value) => setTab(value as 'lines' | 'autocount')}>
        <TabsList aria-label="Sales order sections">
          <TabsTrigger value="lines">Lines</TabsTrigger>
          <TabsTrigger value="autocount">
            {divergence
              ? `AutoCount differences (${divergence.differing_count})`
              : 'AutoCount differences'}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="lines" className="min-w-0 space-y-3">
          <SalesOrderLinesTable
            lines={lines}
            findings={findings}
            flagItems={flagItems}
            canDismiss={canDismiss}
            onDismiss={setDismissing}
            defaultNeedsAttention={!isPublished}
            reference={reference}
            // The same section either way. With a session open the card keeps its heading and
            // its counts and the table inside becomes a spreadsheet; the columns are the same
            // in the same order.
            editing={
              edit.isEditing
                ? {
                    staged: edit.staged,
                    seed: edit.seed,
                    stage: edit.stage,
                    toggleRemoved: edit.toggleRemoved,
                  }
                : null
            }
            // A drop writes immediately on the stored order (PR #1264 note 2: no toggle), so the
            // handles are only drawn while there is no edit session for it to race (a staged,
            // unsaved new row has no id the reorder route could place).
            reorder={
              canEdit && isReorderableStatus && !edit.isEditing
                ? { enabled: true, onReorder: (lineIds) => reorderLines.mutate(lineIds) }
                : undefined
            }
          />

          {/* Where each line's stock comes from: a question only once the order is published,
              so a draft's Lines tab stays one table (R16). */}
          {isPublished && <AllocationPanel psoId={psoId} />}
        </TabsContent>

        <TabsContent value="autocount" className="min-w-0">
          <AutoCountDifferencesSummary
            isPublished={isPublished}
            differingCount={divergence?.differing_count ?? 0}
            ageDays={divergence?.age_days ?? 0}
            reconcileHref={
              divergence ? `/project-sales/${projectId}/sales-orders/${psoId}/divergence` : null
            }
          />
        </TabsContent>
      </Tabs>

      {dismissing && (
        <DismissReasonDialog
          severity={dismissing.severity}
          detail={Array.from(new Set(dismissing.members.map((m) => m.finding.detail))).join(' ')}
          ids={dismissing.members
            .filter((member) => !member.finding.acknowledged_at)
            .map((member) => member.finding.id)}
          submitting={acknowledge.isPending || acknowledgeScheduleFinding.isPending}
          onDone={() => setDismissing(null)}
          onDismiss={(_ids, reason) => dismissItem(dismissing, reason)}
        />
      )}

      {regrouping && (
        <SalesOrderRegroupDialog
          lines={lines}
          currentAreaGroup={so.area_group || 'UNGROUPED'}
          submitting={regroup.isPending}
          onDone={() => setRegrouping(false)}
          onConfirm={(groups) => regroup.mutateAsync(groups)}
        />
      )}

      {publishing && (
        <SalesOrderPublishDialog
          reference={reference}
          blocking={blocking}
          unacknowledgedWarnings={unacknowledgedWarnings}
          submitting={publish.isPending}
          downloading={importFile.isPending}
          onDone={(published) => {
            setPublishing(false);
            if (published && originHref) router.push(originHref);
          }}
          onPublish={(body) => publish.mutateAsync(body)}
          onDownloadImportFile={() => importFile.mutate(so.provisional_ref)}
        />
      )}

      {/* The edit view's ONE destructive confirmation. Staging a removal destroys nothing and
          so asks nothing; this is the moment the lines actually leave, and it names how many. */}
      <AlertDialog open={confirmRemovals} onOpenChange={setConfirmRemovals}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              {`Saving removes ${edit.removedCount} ${
                edit.removedCount === 1 ? 'line' : 'lines'
              } from ${reference}. This action cannot be undone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSaving}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={isSaving}
              onClick={(event) => {
                // Held open by hand: the dialog closes itself on the click, and the save that
                // follows would then have nowhere to report a failure back to.
                event.preventDefault();
                void runSave().then(() => setConfirmRemovals(false));
              }}
            >
              {`Save and remove ${edit.removedCount} ${
                edit.removedCount === 1 ? 'line' : 'lines'
              }`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Experimental at this stage: goes back to draft, not a delete. The server names what
          already acted on the published state when it refuses. */}
      <AlertDialog open={confirmUnpublish} onOpenChange={setConfirmUnpublish}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{`Unpublish ${reference}?`}</AlertDialogTitle>
            <AlertDialogDescription>
              {`${reference} goes back to draft; nothing that already acted on it exists.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unpublish.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={unpublish.isPending}
              onClick={(event) => {
                // Held open by hand: the dialog closes itself on click, and a refusal would
                // then have nowhere to report back to.
                event.preventDefault();
                unpublish
                  .mutateAsync()
                  .then(() => setConfirmUnpublish(false))
                  .catch(() => {
                    // The mutation already toasted the reason.
                  });
              }}
            >
              {unpublish.isPending ? 'Unpublishing...' : 'Unpublish'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Hard delete, so a draft that was built wrong can simply be built again. It names the
          line count because that is what is actually being thrown away. */}
      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete ${reference} and its ${so.line_count} line${
          so.line_count === 1 ? '' : 's'
        }? This action cannot be undone. The purchase order and its delivery schedule are untouched, so the drafts can be built again.`}
        onDelete={async () => {
          await removeOrder.mutateAsync(psoId);
        }}
        onSuccess={() => router.push(`/project-sales/${projectId}?tab=sales-orders`)}
        successMessage="Sales order deleted"
      />
    </div>
  );
}

/**
 * The AutoCount differences tab (S7-2): how many rows AutoCount disagrees on and the way to
 * answer them. The row-by-row comparison stays its own page; this tab is where it is reached.
 */
function AutoCountDifferencesSummary({
  isPublished,
  differingCount,
  ageDays,
  reconcileHref,
}: {
  isPublished: boolean;
  differingCount: number;
  ageDays: number;
  reconcileHref: string | null;
}) {
  if (!reconcileHref) {
    return (
      <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
        <h3 className="text-sm font-semibold">
          {isPublished ? 'No AutoCount differences' : 'Not in AutoCount yet'}
        </h3>
      </div>
    );
  }
  return (
    <div
      className="flex flex-col gap-2 rounded-lg border border-amber-500/50 bg-amber-500/5 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <span className="min-w-0 break-words">
        <span className="font-semibold text-amber-700 dark:text-amber-400">
          {`AutoCount disagrees on ${differingCount} row${differingCount === 1 ? '' : 's'}.`}
        </span>
        {ageDays > 0 ? ` Waiting ${ageDays} day${ageDays === 1 ? '' : 's'}.` : ''}
      </span>
      <Button asChild size="sm" className="shrink-0">
        <Link href={reconcileHref}>Reconcile</Link>
      </Button>
    </div>
  );
}

/**
 * One fact about this order, and - for the one that can be changed - the input that replaces
 * it IN PLACE while a session is open.
 *
 * The swap happens inside this component rather than at the call site so the label, the
 * position and the grid cell are identical in both views. Everything else in the strip is
 * read-only metadata and simply never takes an `onChange`.
 */
function Field({
  label,
  value,
  editing = false,
  editValue,
  placeholder,
  maxLength,
  onChange,
}: {
  label: string;
  value: string;
  editing?: boolean;
  /** The RAW stored value the input holds, which is not the display text: an empty area group
   *  reads "No area group" and must not be typed back into the field as those words. */
  editValue?: string;
  placeholder?: string;
  maxLength?: number;
  onChange?: (value: string) => void;
}) {
  const inputId = `so-field-${label.toLowerCase().replace(/\W+/g, '-')}`;

  if (editing && onChange) {
    return (
      <div className="min-w-0">
        <label className="text-xs text-muted-foreground" htmlFor={inputId}>
          {label}
        </label>
        <Input
          id={inputId}
          className="mt-0.5 h-8"
          value={editValue ?? ''}
          placeholder={placeholder}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words text-sm font-medium" title={value}>
        {value}
      </p>
    </div>
  );
}
