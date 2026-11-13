'use client';

/**
 * The Order Change Notice detail page (OCN-ORDER-CHANGE-NOTICE G4): the record header (number and
 * status pill, the pager, one main button per status and permission), the read-only metadata,
 * and the tabs Details / Conversation / SLA / History (Revisions comes with slice 2). The
 * Details tab reads like the form, field for field, then the linked amendment's change, the
 * files, the Customer Service comment and the sign-off.
 *
 * Pattern: NewProductApplicationDetail (the same lifecycle template).
 */

import { useState } from 'react';
import Link from 'next/link';
import { Ban, Link2, RotateCcw, Undo2 } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import AuditTrail from '@/components/audit/AuditTrail';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { DocField, ReadValue } from '@/components/common/DocField';
import { EntityAttachmentsSection } from '@/components/common/EntityAttachmentsSection';
import { OrderChangeNoticeLines, type OcnDraftLine } from '@/components/common/OrderChangeNoticeLines';
import { RecordHeaderCard } from '@/components/common/RecordHeaderCard';
import { PurchaseRequestSignoffFooter } from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestSignoffFooter';
import { AmendmentDeltaSummary } from '@/app/(protected)/project-sales/[projectId]/components/AmendmentDeltaSummary';
import { AmendmentDeltaTable } from '@/app/(protected)/project-sales/[projectId]/components/AmendmentDeltaTable';
import type { AmendmentDeltaRow } from '@/app/(protected)/project-sales/_shared/types/projectSalesOrder.types';
import { FormComments } from '@/components/common/comments/FormComments';
import FormSLATrackingTab from '@/app/(protected)/sla-management/_shared/FormSLATrackingTab';
import { useHandlingLock } from '@/app/(protected)/sla-management/_shared/useHandlingLock';
import { HandlingLockBanner } from '@/app/(protected)/sla-management/_shared/HandlingLockBanner';
import { HandlingLockReleaseMenuItem } from '@/app/(protected)/sla-management/_shared/HandlingLockActions';
import { useFormAction } from '@/app/(protected)/sla-management/_shared/useFormAction';
import { FormActionBanner } from '@/app/(protected)/sla-management/_shared/FormActionBanner';
import { UndoActionDialog } from '@/app/(protected)/sla-management/_shared/UndoActionDialog';
import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import { useHasPermission } from '@/hooks/usePermissions';
import { useUrlTab } from '@/hooks/useUrlTab';
import { formatDateInMalaysia } from '@/lib/helpers';
import { codeWithName } from '@/lib/product-display';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  OCN_SOURCE_WORDS,
  mayEditNotice,
  ocnStatusPillKey,
  ocnStatusWord,
  type OcnDetail,
} from '@/types/orderChangeNotice';
import {
  linkOrderChangeNoticeAttachment,
  uploadOrderChangeNoticeAttachment,
} from '../services/orderChangeNoticeService';
import {
  orderChangeNoticesPagerQuery,
  useOrderChangeNoticeMutations,
  useOrderChangeNoticeQuery,
} from '../hooks/useOrderChangeNotices';
import { OCN_APPROVE, OCN_BASE_PATH, OCN_CREATE, OCN_EDIT, OCN_PROCESS } from '../constants';

// Revisions joins with slice 2 (lead ruling m9): there is no revision snapshot to show yet.
const DETAIL_TABS = ['details', 'conversation', 'sla', 'history'] as const;
const TAB_LABELS: ReadonlyArray<readonly [(typeof DETAIL_TABS)[number], string]> = [
  ['details', 'Details'],
  ['conversation', 'Conversation'],
  ['sla', 'SLA'],
  ['history', 'History'],
];

const day = (value: string | null | undefined) => (value ? formatDateInMalaysia(value) : '');

type Asking =
  | { kind: 'send_back' }
  | { kind: 'reject' }
  | { kind: 'done' }
  | { kind: 'void' }
  | { kind: 'revise' };

const ASK: Record<
  Asking['kind'],
  { title: string; label: string; confirm: string; required: boolean; destructive?: boolean; minLength?: number }
> = {
  send_back: { title: 'Send back to the raiser', label: 'Reason', confirm: 'Send back', required: true },
  reject: { title: 'Reject this notice', label: 'Remarks', confirm: 'Reject', required: true, destructive: true },
  done: { title: 'Mark done', label: 'Customer Service comment (optional)', confirm: 'Mark done', required: false },
  void: { title: 'Void this notice', label: 'Reason', confirm: 'Void', required: true, destructive: true, minLength: 3 },
  revise: { title: 'Revise this notice', label: 'What changed, and why?', confirm: 'Revise', required: true },
};

function ReasonDialog({
  asking,
  busy,
  onCancel,
  onConfirm,
}: {
  asking: Asking;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const spec = ASK[asking.kind];
  const [value, setValue] = useState('');
  // The backend's own rule for each reason: a void needs at least 3 characters.
  const ready = !spec.required || value.trim().length >= (spec.minLength ?? 1);
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{spec.title}</DialogTitle>
          <DialogDescription className="sr-only">{spec.label}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-1.5">
          <Label htmlFor="ocn-reason">{spec.required ? `${spec.label} *` : spec.label}</Label>
          <Textarea id="ocn-reason" rows={3} value={value} onChange={(e) => setValue(e.target.value)} />
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            variant={spec.destructive ? 'destructive' : undefined}
            disabled={!ready || busy}
            onClick={() => onConfirm(value.trim())}
          >
            {spec.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetailsCard({ r }: { r: OcnDetail }) {
  return (
    <Card className="border-2 shadow-sm">
      <CardContent className="px-5 pb-8 pt-6 sm:px-10">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Order Change Notice</Badge>
        </div>
        <div className="grid grid-cols-1 gap-x-10 gap-y-5 sm:grid-cols-2">
          <DocField label="Date">
            <ReadValue>{day(r.ocn_date)}</ReadValue>
          </DocField>
          <DocField label="Customer">
            <ReadValue>{r.customer_name}</ReadValue>
          </DocField>
          <DocField label="Customer PO no.">
            <ReadValue>{r.customer_po_no}</ReadValue>
          </DocField>
          <DocField label="SO no.">
            <ReadValue>{r.so_no_text}</ReadValue>
          </DocField>
          <DocField label="Project" className="sm:col-span-2">
            <ReadValue>
              {r.project_id && r.project_title ? (
                <Link href={`/project-sales/${r.project_id}`} className="text-primary hover:underline">
                  {r.project_title}
                </Link>
              ) : (
                r.project_title
              )}
            </ReadValue>
          </DocField>
          <DocField label="C.S. in charge">
            <ReadValue>{r.cs_in_charge_name}</ReadValue>
          </DocField>
          <DocField label="Sales in charge">
            <ReadValue>{r.sales_in_charge_name}</ReadValue>
          </DocField>
          <DocField label="Type of change" className="sm:col-span-2">
            <div className="py-2 text-sm">
              <p className="font-medium">{r.change_type_name || '-'}</p>
              {r.risk_level && (
                <p>
                  <span className="text-muted-foreground">Risk: </span>
                  <span>{r.risk_level}</span>
                </p>
              )}
              {r.guide_text && <p className="mt-1 text-muted-foreground">{r.guide_text}</p>}
            </div>
          </DocField>
          <DocField label="Description" className="sm:col-span-2">
            <p className="min-h-9 whitespace-pre-wrap break-words py-2 text-sm">{r.description || '-'}</p>
          </DocField>
        </div>

        <h3 className="mb-3 mt-8 text-base font-semibold">Line items</h3>
        <OrderChangeNoticeLines lines={draftLines(r)} readOnly />

        <section className="mt-8 rounded-md border px-4 py-3">
          <h3 className="text-sm font-semibold">Customer Service comment</h3>
          {r.cs_comment ? (
            <p className="mt-1 whitespace-pre-wrap break-words text-sm">{r.cs_comment}</p>
          ) : (
            <div className="mt-1 text-sm">
              <p className="font-medium">No comment yet</p>
              <p className="text-muted-foreground">Nothing from Customer Service so far.</p>
            </div>
          )}
        </section>

        <Signoff r={r} />
      </CardContent>
    </Card>
  );
}

/** The detail's read-only table: the notice's lines in the shared line table. */
function draftLines(r: OcnDetail): OcnDraftLine[] {
  return r.lines.map((l, index) => ({
    key: l.id ?? `line-${index}`,
    product_id: l.product_id,
    label: codeWithName(l.product_code ?? '', l.product_name ?? ''),
    qty_before: l.qty_before ?? '',
    qty_after: l.qty_after ?? '',
    date_before: l.date_before ?? null,
    date_after: l.date_after ?? null,
    delivered_qty: l.delivered_qty ?? '',
    remark: l.remark ?? '',
  }));
}

/** The shared sign-off (Decision, Name, Date, Remarks); Pending until a decision. */
function Signoff({ r }: { r: OcnDetail }) {
  const name =
    r.approval_status === 'rejected' ? (r.rejected_by_name ?? r.approved_by) : (r.approver_name ?? r.approved_by);
  return (
    <PurchaseRequestSignoffFooter
      variant="decision"
      request={{
        approval_status: r.approval_status,
        approved_by: name,
        approved_at: r.approved_at,
        approval_comments: r.approval_comments,
      }}
    />
  );
}

/** UAC E4 / review B1: the change an amendment put on the notice, read-only, with its sales
 *  order and PO by number (links, never an id on screen). */
function LinkedAmendment({ r }: { r: OcnDetail }) {
  const table = r.change_table_json;
  if (!r.amendment_id && !(table?.rows?.length ?? 0)) return null;
  const rows = (table?.rows ?? []) as AmendmentDeltaRow[];
  const projectPath = r.project_id ? `/project-sales/${r.project_id}` : null;
  const soId = r.project_sales_order_id ?? r.amendment_sales_order_id;
  return (
    <Card>
      <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="text-sm">Linked amendment</CardTitle>
        {r.amendment_status && (
          <Badge variant="secondary" appearance="light">
            {r.amendment_status.replace(/_/g, ' ')}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-x-10 gap-y-3 sm:grid-cols-2">
          <DocField label="Sales order">
            <ReadValue>
              {r.so_ref && projectPath && soId ? (
                <Link
                  // Opens this amendment, not an empty compare (`?amendment=`, the review page's param).
                  href={`${projectPath}/sales-orders/${soId}/revisions${r.amendment_id ? `?amendment=${r.amendment_id}` : ''}`}
                  className="text-primary hover:underline"
                >
                  {r.so_ref}
                </Link>
              ) : (
                r.so_ref
              )}
            </ReadValue>
          </DocField>
          <DocField label="Customer PO">
            <ReadValue>
              {r.po_number && projectPath && r.purchase_order_id ? (
                <Link href={`${projectPath}/pos/${r.purchase_order_id}`} className="text-primary hover:underline">
                  {r.po_number}
                </Link>
              ) : (
                r.po_number
              )}
            </ReadValue>
          </DocField>
        </div>
        {rows.length > 0 && (
          <>
            <AmendmentDeltaSummary
              rows={rows}
              verbSummary={table?.verb_summary ?? {}}
              unmatchedCount={(table?.unmatched ?? []).length}
              fromLabel="Published order"
              toLabel="Revised document"
            />
            <AmendmentDeltaTable rows={rows} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function OrderChangeNoticeDetail({ ocnId }: { ocnId: string }) {
  const { data, isLoading, isError, error, refetch } = useOrderChangeNoticeQuery(ocnId);
  // Form-action deferral, as on the purchase request (PLAN-form-sla-undo.md): a stage move held
  // for its grace window shows the shared countdown with Undo, and every workflow button waits.
  const formAction = useFormAction({
    sourceEntityType: 'order_change_notice',
    sourceEntityId: ocnId,
    entityKey: data ? `${data.status}:${data.approval_status ?? ''}:${data.revision_no ?? 0}` : null,
  });
  const { submit, send, back, decide, done, voidIt, revise } = useOrderChangeNoticeMutations({
    onDeferred: formAction.refresh,
  });
  const canCreate = useHasPermission(OCN_CREATE);
  const canEdit = useHasPermission(OCN_EDIT);
  const canApprove = useHasPermission(OCN_APPROVE);
  const canProcess = useHasPermission(OCN_PROCESS);
  const userId = useEffectiveUserId();
  const handlingLock = useHandlingLock({
    sourceEntityType: 'order_change_notice',
    sourceEntityId: ocnId,
    entityKey: data ? `${data.status}:${data.approval_status ?? ''}:${data.revision_no ?? 0}` : undefined,
    enabled: true,
  });
  const [tab, setTab] = useUrlTab({ tabs: DETAIL_TABS, defaultTab: 'details' });
  const [asking, setAsking] = useState<Asking | null>(null);
  const [undoOpen, setUndoOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center text-sm">
        <p>{error instanceof Error ? error.message : 'This order change notice could not be loaded.'}</p>
        <Button className="mt-4" variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const r = data;
  const rev = { id: r.id, revisionNo: r.revision_no ?? 0 };
  const status = String(r.status);
  const mine = Boolean(userId) && r.created_by === userId;
  const editable = status === 'draft' || status === 'rejected';
  const awaiting = status === 'submitted' || status === 'resubmitted';
  const pendingApproval = awaiting && r.approval_status === 'pending';
  const open = !['rejected', 'processed_by_cs', 'voided'].includes(status);
  const busy =
    submit.isPending || send.isPending || back.isPending || decide.isPending ||
    done.isPending || voidIt.isPending || revise.isPending;
  // The stage work is gated by the handling lock, like the purchase request's.
  const stageLocked = !handlingLock.businessCtasEnabled;
  const workBusy = busy || stageLocked;
  // While a held action counts down, no other move may be queued on the old state (AC-D-10).
  const held = formAction.ctasDisabled;
  const lockedTitle = stageLocked
    ? `Being handled by ${handlingLock.tracker?.handled_by_name ?? 'someone else'}. Take over to act.`
    : undefined;

  const canSubmit = !held && editable && canCreate && (mine || canEdit);
  const canSend = !held && awaiting && !pendingApproval && canEdit;
  const canDecide = !held && pendingApproval && canApprove;
  const canDone = !held && status === 'approved' && canProcess;
  const canRevise = !held && (status === 'approved' || status === 'rejected') && (canEdit || canApprove);
  const mayEdit = mayEditNotice({ mine, canCreate, canEdit });
  const canVoid = !held && open && mayEdit;
  const canEditForm = editable && mayEdit;

  const confirmAsk = async (value: string) => {
    if (!asking) return;
    try {
      if (asking.kind === 'send_back') await back.mutateAsync({ ...rev, reason: value });
      else if (asking.kind === 'reject')
        await decide.mutateAsync({ ...rev, action: 'rejected', comments: value });
      else if (asking.kind === 'done') await done.mutateAsync({ ...rev, csComment: value || null });
      else if (asking.kind === 'void') await voidIt.mutateAsync({ ...rev, reason: value });
      else await revise.mutateAsync({ ...rev, reason: value });
      setAsking(null);
    } catch {
      // the mutation's own toast names the refusal
    }
  };

  const pill = (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(ocnStatusPillKey(r))}`}>
      {ocnStatusWord(r)}
    </span>
  );

  return (
    <div className="space-y-6">
      <RecordHeaderCard
        // The pill sits in the heading with the number, as the record header reads it.
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span>{r.ocn_number}</span>
            {pill}
          </span>
        }
        subtitle={[r.customer_name, r.customer_po_no ? `PO ${r.customer_po_no}` : null]
          .filter(Boolean)
          .join(', ')}
        actions={
        <DetailActions
          pager={{
            ...orderChangeNoticesPagerQuery,
            detailPath: OCN_BASE_PATH,
            currentId: ocnId,
            ariaLabel: 'order change notice',
          }}
          gearLabel="Notice actions"
          gear={
            <DetailActionsMenu ariaLabel="Notice actions">
              <DropdownMenuItem
                onSelect={() => {
                  void navigator.clipboard
                    .writeText(window.location.href)
                    .then(() => toast.success('Link copied'))
                    .catch(() => toast.error('Could not copy the link'));
                }}
              >
                <Link2 className="size-4" />
                Copy link
              </DropdownMenuItem>
              {canRevise && (
                <DropdownMenuItem disabled={busy} onSelect={() => setAsking({ kind: 'revise' })}>
                  <RotateCcw className="size-4" />
                  Revise
                </DropdownMenuItem>
              )}
              {canVoid && (
                <DropdownMenuItem
                  variant="destructive"
                  disabled={busy}
                  onSelect={() => setAsking({ kind: 'void' })}
                >
                  <Ban className="size-4" />
                  Void
                </DropdownMenuItem>
              )}
              {/* Post-grace Undo: shown only when the server says the last action can be reversed. */}
              {formAction.view.kind === 'undoable' && (
                <DropdownMenuItem onSelect={() => setUndoOpen(true)} data-testid="undo-action-menu-item">
                  <Undo2 className="size-4" />
                  Undo last action
                </DropdownMenuItem>
              )}
              <HandlingLockReleaseMenuItem state={handlingLock.state} onRelease={handlingLock.release} />
            </DetailActionsMenu>
          }
          primary={
            <div className="flex flex-wrap items-center gap-2">
              {canEditForm && (
                <Button variant="outline" asChild>
                  <Link href={`${OCN_BASE_PATH}/${r.id}/edit`}>Edit</Link>
                </Button>
              )}
              {canSubmit && (
                <Button disabled={busy} onClick={() => submit.mutate(rev)}>
                  Submit
                </Button>
              )}
              {canSend && (
                <>
                  <Button
                    variant="outline"
                    disabled={workBusy}
                    title={lockedTitle}
                    onClick={() => setAsking({ kind: 'send_back' })}
                  >
                    Send back
                  </Button>
                  <Button disabled={workBusy} title={lockedTitle} onClick={() => send.mutate(rev)}>
                    Send for approval
                  </Button>
                </>
              )}
              {canDecide && (
                <>
                  <Button
                    variant="outline"
                    className="border-destructive text-destructive hover:bg-destructive/10"
                    disabled={workBusy}
                    title={lockedTitle}
                    onClick={() => setAsking({ kind: 'reject' })}
                  >
                    Reject
                  </Button>
                  <Button
                    disabled={workBusy}
                    title={lockedTitle}
                    onClick={() => decide.mutate({ ...rev, action: 'approved', comments: null })}
                  >
                    Approve
                  </Button>
                </>
              )}
              {canDone && (
                <Button disabled={workBusy} title={lockedTitle} onClick={() => setAsking({ kind: 'done' })}>
                  Mark done
                </Button>
              )}
            </div>
          }
        />
        }
      >
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Created by</dt>
            <dd>{r.created_by_name || '-'}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Revision</dt>
            <dd className="tabular-nums">{r.revision_no ?? 0}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Source</dt>
            <dd>{OCN_SOURCE_WORDS[r.source ?? ''] ?? (r.source || '-')}</dd>
          </div>
        </dl>
      </RecordHeaderCard>

      <HandlingLockBanner
        state={handlingLock.state}
        tracker={handlingLock.tracker}
        onClaim={handlingLock.claim}
        onTakeOver={handlingLock.takeOver}
      />

      <FormActionBanner
        view={formAction.view}
        onCancel={formAction.cancel}
        onExpire={formAction.refresh}
        onDismissOutcome={formAction.refresh}
        isCancelling={formAction.isMutating}
      />

      {formAction.view.kind === 'undoable' && (
        <UndoActionDialog
          open={undoOpen}
          onOpenChange={setUndoOpen}
          eligibility={formAction.view.eligibility}
          entityLabel={r.ocn_number}
          onConfirm={(reason) => {
            formAction.undo(reason);
            setUndoOpen(false);
          }}
          isSubmitting={formAction.isMutating}
        />
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line" className="w-full justify-start">
          {TAB_LABELS.map(([value, label]) => (
            // A plain click switches too (the SalesTeamDetail pattern), not only Radix's pointer down.
            <TabsTrigger key={value} value={value} onClick={() => setTab(value)}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="details" className="mt-6 space-y-6">
          <DetailsCard r={r} />
          <LinkedAmendment r={r} />
          <EntityAttachmentsSection
            entityId={r.id}
            attachments={r.attachments ?? []}
            editable={canEditForm}
            linkAttachment={linkOrderChangeNoticeAttachment}
            unlinkActionKey="order_change_notice_attachment.unlink"
            unlinkEntityType="order_change_notice_attachment"
            uploadFile={uploadOrderChangeNoticeAttachment}
            invalidateKeys={[['order-change-notice', r.id], ['order-change-notices']]}
            entityLabel="notice"
          />
        </TabsContent>
        <TabsContent value="conversation" className="mt-6">
          <FormComments kind="order_change_notice" entityId={r.id} />
        </TabsContent>
        <TabsContent value="sla" className="mt-6">
          <FormSLATrackingTab sourceEntityType="order_change_notice" sourceEntityId={r.id} />
        </TabsContent>
        <TabsContent value="history" className="mt-6">
          <AuditTrail entityType="order_change_notice" entityId={r.id} title="History" />
        </TabsContent>
      </Tabs>

      {asking && (
        <ReasonDialog
          asking={asking}
          busy={busy}
          onCancel={() => setAsking(null)}
          onConfirm={(v) => void confirmAsk(v)}
        />
      )}
    </div>
  );
}
