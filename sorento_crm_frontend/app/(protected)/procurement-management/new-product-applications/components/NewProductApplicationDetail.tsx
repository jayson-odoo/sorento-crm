'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Download, Link2, Trash2, XCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
import { Textarea } from '@/components/ui/textarea';
import AuditTrail from '@/components/audit/AuditTrail';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { NewProductApplicationHeader } from '@/components/common/NewProductApplicationHeader';
import { NewProductApplicationLines } from '@/components/common/NewProductApplicationLines';
import NewProductApplicationAttachments from './NewProductApplicationAttachments';
import { RejectionReasonBanner } from '@/components/common/RejectionReasonBanner';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia } from '@/lib/helpers';
import { numberFieldError } from '@/lib/number-field';
import { stateFromDetail } from '@/lib/new-product-application-form';
import { codeWithName } from '@/lib/product-display';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import type {
  NewProductApplicationDetail as Detail,
  NewProductApplicationLine as Line,
  NewProductApplicationProductHit,
} from '@/types/newProductApplication';
import {
  newProductApplicationsPagerQuery,
  useNewProductApplicationMutations,
  useNewProductApplicationQuery,
} from '../hooks/useNewProductApplications';
import {
  downloadNewProductApplicationExcel,
  searchNewProductApplicationProducts,
} from '../services/newProductApplicationService';

// The sheet is read-only here, so no brand is ever searched.
const NO_BRANDS = async () => [];

const BASE_PATH = '/procurement-management/new-product-applications';

const LOCK_SENTENCE =
  'Locked: Revise to change it; it goes back to Draft and needs approval again.';

const day = (value: string | null | undefined) =>
  value ? formatDateInMalaysia(value) : '';
const isResolved = (l: Line) => Boolean(l.opened_product_id || l.closed_reason);

function ReasonDialog({
  title,
  label,
  description,
  confirmLabel,
  required,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  description?: string;
  confirmLabel: string;
  required: boolean;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const [value, setValue] = useState('');
  const ready = !required || value.trim().length > 0;
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className={description ? undefined : 'sr-only'}>
            {description ?? label}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-1.5">
          <Label htmlFor="npa-reason">{required ? `${label} *` : label}</Label>
          <Textarea
            id="npa-reason"
            rows={3}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            disabled={!ready || busy}
            onClick={() => onConfirm(value.trim())}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type Asking =
  | { kind: 'reject' }
  | { kind: 'revise' }
  | { kind: 'cancel' }
  | { kind: 'close'; lineId: string };

/** The "Opened as" cell: the outcome of a line, or the two purchasing buttons. */
function OpenedAs({
  line,
  applicationStatus,
  canOpen,
  busy,
  onLink,
  onClose,
  onUndo,
}: {
  line: Line;
  applicationStatus: Detail['status'];
  canOpen: boolean;
  busy: boolean;
  onLink: (lineId: string, productId: string) => void;
  onClose: (lineId: string) => void;
  onUndo: (lineId: string) => void;
}) {
  const [searching, setSearching] = useState(false);
  // The search text the server last answered with nothing for; the empty message names it.
  const [missed, setMissed] = useState('');

  const fetchProducts = async (q: string) => {
    if (!q.trim()) return [];
    const hits = await searchNewProductApplicationProducts(q);
    setMissed(hits.length === 0 ? q.trim() : '');
    return hits;
  };

  const undo = canOpen &&
    ['approved', 'completed'].includes(applicationStatus) && (
      <button
        type="button"
        className="text-primary underline-offset-2 hover:underline disabled:opacity-50"
        disabled={busy}
        onClick={() => onUndo(line.id)}
      >
        Undo
      </button>
    );

  if (line.opened_product_id) {
    const who = [line.resolved_by_name, day(line.resolved_at)]
      .filter(Boolean)
      .join(', ');
    return (
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass('completed')}`}
          >
            Opened
          </span>
          <Link
            href={`/master-data-management/products/${line.opened_product_id}`}
            className="truncate font-medium text-primary hover:underline"
            title={codeWithName(
              line.opened_product_code,
              line.opened_product_name,
            )}
          >
            {codeWithName(line.opened_product_code, line.opened_product_name)}
          </Link>
          {line.opened_product_active === false && (
            <Badge variant="secondary">Inactive</Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {who} {undo}
        </p>
      </div>
    );
  }

  if (line.closed_reason) {
    const who = [line.resolved_by_name, day(line.resolved_at)]
      .filter(Boolean)
      .join(', ');
    return (
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass('cancelled')}`}
          >
            Not opening
          </span>
          <span className="truncate" title={line.closed_reason}>
            {line.closed_reason}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          {who} {undo}
        </p>
      </div>
    );
  }

  if (!canOpen || applicationStatus !== 'approved') {
    return <span className="text-muted-foreground">-</span>;
  }

  return (
    <div className="min-w-0 space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <Button
          size="sm"
          variant={searching ? 'outline' : 'primary'}
          disabled={busy}
          onClick={() => setSearching((on) => !on)}
        >
          Link product
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onClose(line.id)}
        >
          Not opening
        </Button>
      </div>
      {searching && (
        <>
          <AsyncCombobox<NewProductApplicationProductHit>
            ariaLabel={`Product for line ${line.line_no}`}
            value=""
            allowFreeText={false}
            fetchOptions={fetchProducts}
            optionValue={(o) => o.id}
            optionLabel={(o) => codeWithName(o.product_code, o.product_name)}
            optionMeta={(o) => o.brand_name ?? ''}
            placeholder="Search product code"
            onChange={(v, item) => {
              if (!item) return;
              setMissed('');
              setSearching(false);
              onLink(line.id, v);
            }}
          />
          {missed && (
            <p className="text-sm text-muted-foreground">
              {missed} is not in the product list yet. It appears after
              AutoCount sends it.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default function NewProductApplicationDetail({
  applicationId,
}: {
  applicationId: string;
}) {
  const router = useRouter();
  const {
    data: application,
    isLoading,
    isError,
    error,
  } = useNewProductApplicationQuery(applicationId);
  const {
    submit,
    approve,
    reject,
    revise,
    cancel,
    link,
    close,
    undo,
    feedback,
  } = useNewProductApplicationMutations();
  const canCreate = useHasPermission(
    'procurement.new_product_applications.create',
  );
  const canApprove = useHasPermission(
    'procurement.new_product_applications.approve',
  );
  const canOpen = useHasPermission(
    'procurement.new_product_applications.open_code',
  );
  // The history endpoint answers only admins and `view` holders.
  const canViewRecord = useHasPermission(
    'procurement.new_product_applications.view',
  );
  const userId = useEffectiveUserId();
  const [asking, setAsking] = useState<Asking | null>(null);
  // Purchasing's edits to LEADTIME and COST before Save feedback; null shows the saved values.
  const [draft, setDraft] = useState<{
    lead_time: string;
    costs: Record<string, string>;
  } | null>(null);
  const savedState = useMemo(
    () => (application ? stateFromDetail(application) : null),
    [application],
  );

  // Delete draft asks nothing (D7): a countdown takes the primary area, Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'new_product_application.delete',
    entityType: 'new_product_application',
    entityId: applicationId,
    verb: 'Deleting',
    subject: application?.application_no ?? 'this draft',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Draft deleted',
    invalidateKeys: [['new-product-applications']],
    onCommitted: () => router.push(BASE_PATH),
  });

  const busy =
    submit.isPending ||
    approve.isPending ||
    reject.isPending ||
    revise.isPending ||
    cancel.isPending ||
    link.isPending ||
    close.isPending ||
    undo.isPending;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError || !application) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center text-sm">
        {error instanceof Error
          ? error.message
          : 'This application could not be loaded.'}
      </div>
    );
  }

  const r: Detail = application;
  const isOwner = Boolean(userId) && r.applicant_id === userId;
  const ownerActs = isOwner && canCreate;
  const editable = r.status === 'draft' || r.status === 'rejected';
  const locked = r.status === 'submitted' || r.status === 'approved';
  const anyResolved = r.lines.some(isResolved);
  const canRevise = locked && !anyResolved && (ownerActs || canApprove);
  const canCancel =
    ownerActs && (r.status === 'draft' || locked) && !anyResolved;
  const stamp = r.submitted_at ?? r.created_at;
  const canFeedback =
    canOpen && (r.status === 'approved' || r.status === 'completed');
  const sheetState = savedState && {
    ...savedState,
    ...(draft
      ? {
          lead_time: draft.lead_time,
          lines: savedState.lines.map((l) => ({
            ...l,
            cost_price: draft.costs[l.id ?? ''] ?? l.cost_price,
          })),
        }
      : {}),
  };

  const saveFeedback = async () => {
    if (!sheetState) return;
    if (
      sheetState.lines.some((l) =>
        numberFieldError(l.cost_price, { min: 0, optional: true }),
      )
    ) {
      toast.error('Cost must be 0 or more.');
      return;
    }
    try {
      await feedback.mutateAsync({
        id: r.id,
        data: {
          lead_time: sheetState.lead_time.trim() || null,
          lines: sheetState.lines.map((l) => ({
            id: l.id as string,
            cost_price: l.cost_price.trim() || null,
          })),
        },
      });
      setDraft(null);
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  const downloadExcel = async () => {
    try {
      await downloadNewProductApplicationExcel(r.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download');
    }
  };

  const fromAutoCount = (l: Line) =>
    [
      l.opened_category_name,
      l.opened_base_uom_name,
      l.opened_list_price == null ? null : `MYR ${l.opened_list_price}`,
      l.opened_supplier_name,
    ]
      .filter(Boolean)
      .join(', ');

  const confirmAsk = async (value: string) => {
    if (!asking) return;
    try {
      if (asking.kind === 'reject')
        await reject.mutateAsync({ id: r.id, reason: value });
      else if (asking.kind === 'revise')
        await revise.mutateAsync({ id: r.id, reason: value });
      else if (asking.kind === 'cancel')
        await cancel.mutateAsync({ id: r.id, reason: value || undefined });
      else
        await close.mutateAsync({
          id: r.id,
          lineId: asking.lineId,
          reason: value,
        });
      setAsking(null);
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  const dialog = (() => {
    if (!asking) return null;
    const common = {
      busy,
      onCancel: () => setAsking(null),
      onConfirm: (v: string) => void confirmAsk(v),
    };
    switch (asking.kind) {
      case 'reject':
        return (
          <ReasonDialog
            {...common}
            title={`Reject ${r.application_no}`}
            label="Reason"
            confirmLabel="Reject"
            required
          />
        );
      case 'revise':
        return (
          <ReasonDialog
            {...common}
            title={`Revise ${r.application_no}?`}
            description="It goes back to Draft and needs approval again."
            label="What changed, and why?"
            confirmLabel="Revise"
            required
          />
        );
      case 'cancel':
        return (
          <ReasonDialog
            {...common}
            title={`Cancel ${r.application_no}`}
            label="Reason (optional)"
            confirmLabel="Cancel application"
            required={false}
          />
        );
      default:
        return (
          <ReasonDialog
            {...common}
            title="Not opening"
            label="Reason"
            confirmLabel="Not opening"
            required
          />
        );
    }
  })();

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 className="break-words text-2xl font-bold">
            New Product Application - {r.application_no}
          </h2>
          <p className="text-sm text-muted-foreground">
            {r.submitted_at ? 'Submitted' : 'Created'}:{' '}
            {stamp ? formatDateInMalaysia(stamp) : '-'}
            {' · '}
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(r.status)}`}
            >
              {r.status_label}
            </span>
            {' · '}
            {r.lines_done} of {r.lines_total}{' '}
            {r.lines_total === 1 ? 'line' : 'lines'} done
          </p>
        </div>
        <DetailActions
          pager={{
            ...newProductApplicationsPagerQuery,
            detailPath: BASE_PATH,
            currentId: applicationId,
            ariaLabel: 'new product application',
          }}
          gearLabel="Application actions"
          pendingAction={deletion.countdown}
          gear={
            <DetailActionsMenu ariaLabel="Application actions">
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
              <DropdownMenuItem onSelect={() => void downloadExcel()}>
                <Download className="size-4" />
                Download Excel
              </DropdownMenuItem>
              {canCancel && (
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => setAsking({ kind: 'cancel' })}
                >
                  <XCircle className="size-4" />
                  Cancel application
                </DropdownMenuItem>
              )}
              {r.status === 'draft' && ownerActs && (
                <DropdownMenuItem
                  variant="destructive"
                  disabled={deletion.isBlocked}
                  onSelect={() => deletion.start()}
                >
                  <Trash2 className="size-4" />
                  Delete draft
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          }
          primary={
            <div className="flex flex-wrap items-center gap-2">
              {editable && ownerActs && (
                <Button disabled={busy} onClick={() => submit.mutate(r.id)}>
                  Submit
                </Button>
              )}
              {r.status === 'submitted' && canApprove && (
                <>
                  <Button disabled={busy} onClick={() => approve.mutate(r.id)}>
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    className="border-destructive text-destructive hover:bg-destructive/10"
                    disabled={busy}
                    onClick={() => setAsking({ kind: 'reject' })}
                  >
                    Reject
                  </Button>
                </>
              )}
              {canRevise && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setAsking({ kind: 'revise' })}
                >
                  Revise
                </Button>
              )}
              {editable && ownerActs && r.source !== 'portal' && (
                <Button variant="outline" asChild>
                  <Link href={`${BASE_PATH}/${r.id}/edit`}>Edit</Link>
                </Button>
              )}
            </div>
          }
        />
      </div>

      {locked && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {r.status === 'approved'
            ? `Approved${r.decided_by_name ? ` by ${r.decided_by_name}` : ''}${r.decided_at ? ` on ${day(r.decided_at)}` : ''}. `
            : 'Waiting for approval. '}
          {LOCK_SENTENCE}
        </div>
      )}
      {r.status === 'rejected' && (
        <RejectionReasonBanner
          reason={r.reject_reason}
          rejectedByName={r.decided_by_name}
          rejectedAt={r.decided_at}
        />
      )}

      <Card className="border-2 shadow-sm">
        <CardContent className="px-5 pb-8 pt-6 sm:px-10">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">New Product Application</Badge>
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(r.status)}`}
            >
              {r.status_label}
            </span>
          </div>
          {(r.revise_reason || r.cancel_reason) && (
            <div className="mb-4 space-y-1 text-sm [&_p]:break-words">
              {r.revise_reason && (
                <p>
                  <span className="text-muted-foreground">
                    Revised because:{' '}
                  </span>
                  {r.revise_reason}
                </p>
              )}
              {r.cancel_reason && (
                <p>
                  <span className="text-muted-foreground">Cancel reason: </span>
                  {r.cancel_reason}
                </p>
              )}
            </div>
          )}
          {sheetState && (
            <>
              <NewProductApplicationHeader
                value={sheetState}
                onChange={(next) =>
                  setDraft((prev) => ({
                    lead_time: next.lead_time,
                    costs: prev?.costs ?? {},
                  }))
                }
                readOnly
                applicationNo={r.application_no}
                createdAt={r.created_at}
                salesPerson={r.applicant_name}
                feedback={{
                  editable: canFeedback,
                  onSave: () => void saveFeedback(),
                  saving: feedback.isPending,
                }}
                stockInquiryField={
                  r.stock_inquiry_id && r.stock_inquiry_number ? (
                    <Link
                      href={`/procurement-management/stock-inquiries/${r.stock_inquiry_id}`}
                      className="text-primary hover:underline"
                    >
                      {r.stock_inquiry_number}
                    </Link>
                  ) : (
                    'None'
                  )
                }
                customerField={
                  <span className="flex flex-wrap items-center gap-2">
                    {[r.customer_code, r.customer_name]
                      .filter(Boolean)
                      .join(' - ') || 'None'}
                    {!r.customer_code && r.customer_name && (
                      <Badge variant="secondary">No debtor code</Badge>
                    )}
                  </span>
                }
              />
              <div className="mt-6">
                <NewProductApplicationLines
                  lines={sheetState.lines}
                  onChange={(next) =>
                    setDraft((prev) => ({
                      lead_time: prev?.lead_time ?? sheetState.lead_time,
                      costs: Object.fromEntries(
                        next.map((l) => [l.id ?? '', l.cost_price]),
                      ),
                    }))
                  }
                  brands={NO_BRANDS}
                  readOnly
                  showCost
                  costEditable={canFeedback}
                  renderOpenedAs={(draftLine) => {
                    const l = r.lines.find((x) => x.id === draftLine.id);
                    if (!l) return null;
                    return (
                      <div className="min-w-0 space-y-1.5">
                        <OpenedAs
                          line={l}
                          applicationStatus={r.status}
                          canOpen={canOpen}
                          busy={busy}
                          onLink={(lineId, productId) =>
                            link.mutate({ id: r.id, lineId, productId })
                          }
                          onClose={(lineId) =>
                            setAsking({ kind: 'close', lineId })
                          }
                          onUndo={(lineId) => undo.mutate({ id: r.id, lineId })}
                        />
                        {l.opened_product_id && (
                          <p className="text-xs text-muted-foreground">
                            From AutoCount: {fromAutoCount(l) || '-'}
                          </p>
                        )}
                      </div>
                    );
                  }}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <NewProductApplicationAttachments
        applicationId={r.id}
        attachments={r.attachments ?? []}
        editable={ownerActs && editable && r.source !== 'portal'}
      />

      {canViewRecord && (
        <AuditTrail
          entityType="new_product_application"
          entityId={applicationId}
          title="Audit Trail"
        />
      )}

      {dialog}
    </div>
  );
}
