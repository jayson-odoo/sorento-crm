'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Download, Link2, Trash2, XCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RejectOutlineButton } from '@/components/common/RejectOutlineButton';
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
import { NewProductApplicationProductCodes } from '@/components/common/NewProductApplicationProductCodes';
import { NewProductApplicationNewCodeValue } from '@/components/common/NewProductApplicationNewCode';
import { NewProductApplicationStockInquiry } from '@/components/common/NewProductApplicationStockInquiry';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useUrlTab } from '@/hooks/useUrlTab';
import NewProductApplicationAttachments from './NewProductApplicationAttachments';
import NewProductApplicationPurchasingDialog from './NewProductApplicationPurchasingDialog';
import { InquiryReadValue } from '@/app/(protected)/procurement-management/stock-inquiries/components/ProductInquiryFormLayout';
import { RejectionReasonBanner } from '@/components/common/RejectionReasonBanner';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import { useHasPermission } from '@/hooks/usePermissions';
import { useRequestScope } from '@/hooks/useRequestScope';
import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import PortalNewProductApplicationForm from '@/app/(auth)/portal/components/NewProductApplicationForm';
import { formatDateInMalaysia } from '@/lib/helpers';
import { isAwaitingReview, submitVerb } from '@/lib/submission-status';
import { stateFromDetail } from '@/lib/new-product-application-form';
import { codeWithName } from '@/lib/product-display';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import type {
  NewProductApplicationDetail as Detail,
  NewProductApplicationLine as Line,
} from '@/types/newProductApplication';
import {
  newProductApplicationsPagerQuery,
  useNewProductApplicationMutations,
  useNewProductApplicationQuery,
} from '../hooks/useNewProductApplications';
import { downloadNewProductApplicationExcel } from '../services/newProductApplicationService';

// The sheet is read-only here, so no brand or product is ever searched.
const NO_PRODUCTS = async () => [];

const DETAIL_TABS = ['details', 'stock_inquiry'] as const;

const BASE_PATH = '/procurement-management/new-product-applications';

const day = (value: string | null | undefined) =>
  value ? formatDateInMalaysia(value) : '';
const isResolved = (l: Line) => Boolean(l.opened_product_id || l.closed_reason);

function ReasonDialog({
  title,
  label,
  description,
  confirmLabel,
  destructive,
  required,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  description?: string;
  confirmLabel: string;
  /** A destructive confirm (a reject), red like the stock inquiry's. */
  destructive?: boolean;
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
            variant={destructive ? 'destructive' : undefined}
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
  | { kind: 'purchasingReject' };

/** The NEW PRODUCT CODE row, read-only: the product (with what AutoCount knows), the typed code, the reason, or the waiting line. */
function NewCodeResult({ application: r }: { application: Detail }) {
  const facts = r.new_product_facts;
  const fromAutoCount = [
    facts?.opened_category_name,
    facts?.opened_base_uom_name,
    facts?.opened_list_price == null ? null : `MYR ${facts.opened_list_price}`,
    facts?.opened_supplier_name,
  ]
    .filter(Boolean)
    .join(', ');
  const who = [r.new_code_by_name, day(r.new_code_at)]
    .filter(Boolean)
    .join(', ');

  if (r.new_product_id) {
    const label = codeWithName(r.new_product_code, r.new_product_name);
    return (
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass('completed')}`}
          >
            Opened
          </span>
          <Link
            href={`/master-data-management/products/${r.new_product_id}`}
            className="truncate font-medium text-primary hover:underline"
            title={label}
          >
            {label}
          </Link>
          {r.new_product_active === false && (
            <Badge variant="secondary">Inactive</Badge>
          )}
        </div>
        {who && <p className="text-xs text-muted-foreground">{who}</p>}
        <p className="text-xs text-muted-foreground">
          From AutoCount: {fromAutoCount || '-'}
        </p>
      </div>
    );
  }
  return (
    <NewProductApplicationNewCodeValue
      code={r.new_code_text ?? r.new_product_code}
      closedReason={r.new_code_closed_reason}
    />
  );
}

/**
 * A salesperson limited to their own applications (PORTAL-P4-REQUESTS R3, form parity) views theirs
 * in the portal's own form, read-only exactly as the portal shows it, with its own Revise, Cancel
 * and files; everyone else the staff detail, unchanged.
 */
export default function NewProductApplicationDetail({
  applicationId,
}: {
  applicationId: string;
}) {
  const { limited } = useRequestScope('new_product_application');
  if (limited) {
    return (
      <MyRequestClientProvider>
        <PortalNewProductApplicationForm applicationId={applicationId} />
      </MyRequestClientProvider>
    );
  }
  return <StaffNewProductApplicationDetail applicationId={applicationId} />;
}

function StaffNewProductApplicationDetail({
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
  const { submit, approve, reject, revise, cancel, undo, purchasingReject } =
    useNewProductApplicationMutations();
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
  const [tab, setTab] = useUrlTab({ tabs: DETAIL_TABS, defaultTab: 'details' });
  const [purchasingOpen, setPurchasingOpen] = useState(false);
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
    undo.isPending ||
    purchasingReject.isPending;

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
  const locked = isAwaitingReview(r.status) || r.status === 'approved';
  const anyResolved =
    Boolean(r.new_product_id || r.new_code_closed_reason) ||
    r.lines.some(isResolved);
  const canRevise = locked && !anyResolved && (ownerActs || canApprove);
  const canCancel =
    ownerActs && (r.status === 'draft' || locked) && !anyResolved;
  // An older application closed as Not opening reads Rejected, pill included (backend flag).
  const pillStatus = r.display_status ?? r.status;
  const stamp = r.submitted_at ?? r.created_at;
  const canAnswer =
    canOpen && (r.status === 'approved' || r.status === 'completed');
  const sheetState = savedState;

  const downloadExcel = async () => {
    try {
      await downloadNewProductApplicationExcel(r.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download');
    }
  };

  const confirmAsk = async (value: string) => {
    if (!asking) return;
    try {
      if (asking.kind === 'reject')
        await reject.mutateAsync({ id: r.id, reason: value });
      else if (asking.kind === 'revise')
        await revise.mutateAsync({ id: r.id, reason: value });
      else if (asking.kind === 'purchasingReject')
        await purchasingReject.mutateAsync({ id: r.id, reason: value });
      else await cancel.mutateAsync({ id: r.id, reason: value || undefined });
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
      case 'purchasingReject':
        return (
          <ReasonDialog
            {...common}
            title="Reject new product application"
            label="Rejection reason"
            confirmLabel="Reject"
            destructive
            required
          />
        );
      default:
        return (
          <ReasonDialog
            {...common}
            title={`Cancel ${r.application_no}`}
            label="Reason (optional)"
            confirmLabel="Cancel application"
            required={false}
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
              className={`${STATUS_PILL_BASE} ${statusPillClass(pillStatus)}`}
            >
              {r.status_label}
            </span>
            {r.lines_total > 0 && (
              <>
                {' · '}
                {r.lines_done} of {r.lines_total}{' '}
                {r.lines_total === 1 ? 'line' : 'lines'} done
              </>
            )}
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
                  {submitVerb(r.status)}
                </Button>
              )}
              {isAwaitingReview(r.status) && canApprove && (
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
              {canAnswer && (
                <Button disabled={busy} onClick={() => setPurchasingOpen(true)}>
                  Edit purchasing response
                </Button>
              )}
              {canAnswer && r.status === 'approved' && (
                <RejectOutlineButton
                  disabled={busy}
                  onClick={() => setAsking({ kind: 'purchasingReject' })}
                />
              )}
            </div>
          }
        />
      </div>

      {r.status === 'approved' && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {`Approved${r.decided_by_name ? ` by ${r.decided_by_name}` : ''}${r.decided_at ? ` on ${day(r.decided_at)}` : ''}.`}
        </div>
      )}
      {r.status === 'rejected' && (
        <RejectionReasonBanner
          reason={r.reject_reason}
          rejectedByName={r.decided_by_name}
          rejectedAt={r.decided_at}
        />
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line" className="w-full justify-start">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="stock_inquiry">Stock inquiry</TabsTrigger>
        </TabsList>
      </Tabs>

      {tab === 'stock_inquiry' ? (
        <NewProductApplicationStockInquiry
          inquiry={r.stock_inquiry}
          href={(id) => `/procurement-management/stock-inquiries/${id}`}
        />
      ) : (
        <>
          <Card className="border-2 shadow-sm">
            <CardContent className="px-5 pb-8 pt-6 sm:px-10">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Badge variant="secondary">New Product Application</Badge>
                <span
                  className={`${STATUS_PILL_BASE} ${statusPillClass(pillStatus)}`}
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
                      <span className="text-muted-foreground">
                        Cancel reason:{' '}
                      </span>
                      {r.cancel_reason}
                    </p>
                  )}
                </div>
              )}
              {sheetState && (
                <>
                  <NewProductApplicationHeader
                    value={sheetState}
                    onChange={() => {}}
                    readOnly
                    applicationNo={r.application_no}
                    createdAt={r.created_at}
                    salesPerson={r.applicant_name}
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
                    productCodesField={
                      <NewProductApplicationProductCodes
                        value={sheetState}
                        onChange={() => {}}
                        products={NO_PRODUCTS}
                        readOnly
                      />
                    }
                    newCodeField={<NewCodeResult application={r} />}
                    costField={
                      r.lines.length === 0 ? (
                        <InquiryReadValue>
                          {r.cost_price == null || r.cost_price === ''
                            ? ''
                            : `MYR ${r.cost_price}`}
                        </InquiryReadValue>
                      ) : undefined
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
                  {(!r.stock_inquiry_id || r.lines.length > 0) && (
                    <div className="mt-6">
                      <NewProductApplicationLines
                        lines={sheetState.lines}
                        onChange={() => {}}
                        readOnly
                        showCost
                        renderOpenedAs={
                          r.lines.some(isResolved)
                            ? (draftLine) => {
                                const l = r.lines.find(
                                  (x) => x.id === draftLine.id,
                                );
                                if (!l || !isResolved(l)) return null;
                                const showUndo =
                                  canOpen &&
                                  ['approved', 'completed'].includes(r.status);
                                return (
                                  <div className="min-w-0 space-y-0.5">
                                    {l.opened_product_id ? (
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        <Link
                                          href={`/master-data-management/products/${l.opened_product_id}`}
                                          className="truncate font-medium text-primary hover:underline"
                                        >
                                          {codeWithName(
                                            l.opened_product_code,
                                            l.opened_product_name,
                                          )}
                                        </Link>
                                        {l.opened_product_active === false && (
                                          <Badge variant="secondary">
                                            Inactive
                                          </Badge>
                                        )}
                                      </div>
                                    ) : (
                                      <span className="break-words">
                                        Rejected: {l.closed_reason}
                                      </span>
                                    )}
                                    {showUndo && (
                                      <button
                                        type="button"
                                        className="text-xs text-primary underline-offset-2 hover:underline disabled:opacity-50"
                                        disabled={busy}
                                        onClick={() =>
                                          undo.mutate({
                                            id: r.id,
                                            lineId: l.id,
                                          })
                                        }
                                      >
                                        Undo
                                      </button>
                                    )}
                                  </div>
                                );
                              }
                            : undefined
                        }
                      />
                    </div>
                  )}
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
        </>
      )}

      {dialog}
      {purchasingOpen && (
        <NewProductApplicationPurchasingDialog
          application={r}
          onClose={() => setPurchasingOpen(false)}
        />
      )}
    </div>
  );
}
