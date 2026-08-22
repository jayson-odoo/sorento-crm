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
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
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
import RecordNavigation from '@/components/common/RecordNavigation';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useAcknowledgeScheduleFinding,
  useProjectSalesOrder,
  useProjectSalesOrderNeighbours,
  useScheduleFindings,
  useSalesOrderDelete,
  useSalesOrderImportFile,
  useSalesOrderMutations,
} from '../../../../_shared/hooks/useProjectSalesOrders';
import { SalesOrderStockLocationBulkApply } from './SalesOrderStockLocationBulkApply';
import { useProject } from '../../../../_shared/hooks/useProjects';
import { useOpenDivergenceForOrder } from '../../../../_shared/hooks/useSoDivergence';
import type { ProjectSalesOrderFinding } from '../../../../_shared/types/projectSalesOrder.types';
import { SalesOrderAcknowledgeDialog } from '../../../components/SalesOrderAcknowledgeDialog';
import { SalesOrderFindingsSection } from '../../../components/SalesOrderFindingsSection';
import { SalesOrderLinesTable } from '../../../components/SalesOrderLinesTable';
import { ScheduleFindingsSection } from '../../../components/ScheduleFindingsSection';
import { formatMoney, sumMoney } from '../../../components/SalesOrderMoney';
import { SalesOrderPublishDialog } from '../../../components/SalesOrderPublishDialog';
import { SalesOrderRegroupDialog } from '../../../components/SalesOrderRegroupDialog';
import {
  GROUPING_ORIGIN_LABEL,
  SalesOrderStatusPill,
} from '../../../components/SalesOrderStatusPill';
import { ReviewStatePill } from '../../../../_shared/components/ReviewStatePill';
import { AllocationPanel } from './AllocationPanel';
import { useSalesOrderEditSession } from './useSalesOrderEditSession';

/**
 * One draft, reviewed rather than authored - and, once Edit is pressed, corrected.
 *
 * Order on the page follows what a reviewer has to decide: what this order is, what stops it
 * publishing, what merely needs a reason, then the 99 lines. Every section renders even when
 * it has nothing in it, because "no warnings" is information and a missing card is not.
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
  const neighbours = useProjectSalesOrderNeighbours(projectId, psoId);
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

  const [acknowledging, setAcknowledging] = React.useState<ProjectSalesOrderFinding | null>(null);
  const [regrouping, setRegrouping] = React.useState(false);
  const [publishing, setPublishing] = React.useState(false);
  const [focusLineId, setFocusLineId] = React.useState<string | null>(null);
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

  // Acknowledged is `acknowledged_at`, which is what the backend's own gate reads. The
  // name beside it is a display field and is absent whenever the acknowledger no longer
  // resolves, which would silently turn a cleared finding back into a blocking one.
  const blocking = findings.filter(
    (finding) => finding.severity === 'hard' && !finding.acknowledged_at,
  );
  const unacknowledgedWarnings = findings.filter(
    (finding) => finding.severity === 'warn' && !finding.acknowledged_at,
  );
  const isPublished = so.status === 'published' || so.status === 'amended';
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
            <h1 className="text-xl font-semibold break-words">{reference}</h1>
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
          <p className="mt-1 text-sm text-muted-foreground break-words">
            {[
              shown.area_group || 'No area group',
              GROUPING_ORIGIN_LABEL[so.grouping_origin] ?? so.grouping_origin,
              so.po_number ? `Customer PO ${so.po_number}` : 'No customer PO recorded',
            ].join(' · ')}
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
              {isSaving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        ) : (
        <div className="flex flex-wrap items-center gap-2">
          {/* Reviewing a project's orders one after another is the normal case, so the pager
              comes first, the way it does on the user record. */}
          <RecordNavigation
            basePath={`/project-sales/${projectId}/sales-orders`}
            prevId={neighbours.prevId}
            nextId={neighbours.nextId}
            currentIndex={neighbours.index != null ? neighbours.index - 1 : undefined}
            totalCount={neighbours.total}
            isLoading={neighbours.isLoading}
            ariaLabel="sales order"
          />
          {/* ONE call to action stands in this header, and everything else is behind the
              gear. The row of buttons this replaced competed with each other, so the thing
              the reader actually came to do was the hardest to find. The gear always has
              at least the revision review in it, so it is never an empty menu. */}
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
          {/* The one thing this status is waiting for: publish a draft somebody may edit,
              answer AutoCount on a published order, and - for a reader who can do neither -
              read the order as AutoCount will. */}
          {canEdit && !isPublished ? (
            <Button type="button" size="sm" onClick={() => setPublishing(true)}>
              <Send className="size-4" aria-hidden />
              Publish
            </Button>
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
        </div>
        )}
      </div>

      {/* Above the summary, because it changes what the reviewer is allowed to do with
          everything below it. */}
      {divergence && (
        <div
          className="rounded-lg border border-amber-500/50 bg-amber-500/5 px-4 py-3 text-sm"
          role="status"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <span className="font-semibold text-amber-700 dark:text-amber-400">
                {`AutoCount disagrees on ${divergence.differing_count} row${divergence.differing_count === 1 ? '' : 's'}.`}
              </span>{' '}
              <span className="text-muted-foreground break-words">
                Our values are unchanged, and amendments are blocked until each row is
                answered.
                {divergence.age_days > 0
                  ? ` Waiting ${divergence.age_days} day${divergence.age_days === 1 ? '' : 's'}.`
                  : ''}
              </span>
            </div>
            <Button asChild size="sm" className="shrink-0">
              <Link href={`/project-sales/${projectId}/sales-orders/${psoId}/divergence`}>
                Reconcile
              </Link>
            </Button>
          </div>
        </div>
      )}

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
            value={shown.area_group || 'No area group'}
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
            value={lines.length > 0 ? formatMoney(lineSum) : 'No lines loaded'}
          />
          <Field
            label="Drafted"
            value={so.created_at ? formatDateInMalaysia(so.created_at) : 'Unknown'}
          />
          <Field
            label="Published"
            value={so.published_at ? formatDateInMalaysia(so.published_at) : 'Not published yet'}
          />
          <Field
            label="AutoCount document"
            value={so.autocount_doc_no || 'Not adopted yet'}
          />
          <Field label="Reference we raised" value={so.provisional_ref} />
        </CardContent>
      </Card>

      {blocking.length > 0 && !isPublished && (
        <div
          className="rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm"
          role="status"
        >
          <span className="font-semibold text-destructive">
            {`Publishing is refused: ${blocking.length} finding${
              blocking.length === 1 ? '' : 's'
            } must be fixed or overridden.`}
          </span>
        </div>
      )}

      <SalesOrderFindingsSection
        findings={findings}
        canEdit={canEdit && !isPublished}
        onAcknowledge={setAcknowledging}
        onFocusLine={setFocusLineId}
      />

      <ScheduleFindingsSection
        findings={scheduleFindings.data ?? []}
        canEdit={canEdit}
        onAcknowledge={(findingId, reason) =>
          acknowledgeScheduleFinding.mutateAsync({ findingId, reason })
        }
      />

      {/* Standalone, like "Move lines" beside it: writes immediately on the stored order, so
          it is offered whether or not an edit session happens to be open. Only while the
          order may still be corrected - the same rule the lines' own Stock location cell
          follows. */}
      {canEdit && !isPublished && !edit.isEditing && (
        <SalesOrderStockLocationBulkApply
          projectId={projectId}
          psoId={psoId}
          lines={lines}
          reference={reference}
        />
      )}

      <SalesOrderLinesTable
        lines={lines}
        findings={findings}
        focusLineId={focusLineId}
        onClearFocus={() => setFocusLineId(null)}
        reference={reference}
        // The same section either way. With a session open the card keeps its heading and its
        // counts and the table inside becomes a spreadsheet; the columns are the same eleven
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
        // Standalone, like Move lines and the stock-location bulk apply beside it: writes
        // immediately on the stored order, so it is only offered while there is no
        // in-progress edit session for it to race (a staged, unsaved new row has no id the
        // reorder route could place).
        reorder={
          canEdit && isReorderableStatus && !edit.isEditing
            ? { enabled: true, onReorder: (lineIds) => reorderLines.mutate(lineIds) }
            : undefined
        }
      />

      {/* Re-mounted 19 Aug 2026 evening (PLAN-demo-followups-19aug-ladder-v2 D1): the captain
          now wants to review plans, and this is the per-order half of that - the Plans page
          is the cross-order list. */}
      <AllocationPanel psoId={psoId} />

      {acknowledging && (
        <SalesOrderAcknowledgeDialog
          finding={acknowledging}
          submitting={acknowledge.isPending}
          onDone={() => setAcknowledging(null)}
          onConfirm={(reason) =>
            acknowledge.mutateAsync({ findingId: acknowledging.id, reason })
          }
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
          onDone={() => setPublishing(false)}
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
