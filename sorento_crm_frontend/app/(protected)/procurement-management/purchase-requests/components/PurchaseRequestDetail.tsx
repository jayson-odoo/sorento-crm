'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Copy, Check, ChevronDown, Clock, MessageSquare, FileDown, Link2, ScrollText, BadgeCheck, XCircle, ArrowUpCircle } from 'lucide-react';
import { useSlaEscalateAction } from '@/app/(protected)/sla-management/_shared/useSlaEscalateAction';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Command,
  CommandCheck,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usePurchaseRequest, usePurchaseRequests } from '../hooks/usePurchaseRequests';
import { formatDate } from '@/lib/helpers';
import PurchaseRequestDeleteDialog from './purchase-request-delete-dialog';
import AuditTrail from '@/components/audit/AuditTrail';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import {
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { sendApprovalLink, setPendingApproval, getUsersForApproverSelect, getOrCreateViewLink, rejectSubmittedPurchaseRequest, processPurchaseRequestByCs, closePurchaseRequestByCs } from '../services/purchaseRequestService';
import { useHasPermission } from '@/hooks/usePermissions';
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
import { Textarea } from '@/components/ui/textarea';
import { exportPurchaseRequestOrSponsorshipToExcel } from '../lib/purchase-request-excel-export';
import { toast } from 'sonner';
import PurchaseRequestAttachmentsSection from './PurchaseRequestAttachmentsSection';
import PurchaseRequestConversationPanel from './PurchaseRequestConversationPanel';
import { PurchaseRequestSignoffFooter } from './PurchaseRequestSignoffFooter';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { usePublicViewLinksEnabled } from '@/hooks/usePublicViewLinksEnabled';
import { purchaseRequestNumberReplyPhrase } from '../lib/purchase-request-field-labels';

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

const DEFAULT_BASE_PATH = '/procurement-management/purchase-requests';
const SPONSORSHIP_FORMS_PATH = '/procurement-management/sponsorship-forms';
const PURCHASE_REQUESTS_PATH = '/procurement-management/purchase-requests';

interface PurchaseRequestDetailProps {
  requestId: string;
  /** Base path for list and edit links (e.g. /procurement-management/sponsorship-forms). */
  basePath?: string;
}

export default function PurchaseRequestDetail({
  requestId,
  basePath = DEFAULT_BASE_PATH,
}: PurchaseRequestDetailProps) {
  const router = useRouter();
  const isValidId = requestId && requestId !== 'new' && requestId !== 'edit';
  const queryClient = useQueryClient();
  const canSendForApproval = useHasPermission(
    'procurement.purchase_requests.send_for_approval',
  );
  const canProcess = useHasPermission('procurement.purchase_requests.process');
  const canClose = useHasPermission('procurement.purchase_requests.close');
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [processDialogOpen, setProcessDialogOpen] = useState(false);
  const [closeCsDialogOpen, setCloseCsDialogOpen] = useState(false);
  const [finalizeNote, setFinalizeNote] = useState('');
  const [finalizing, setFinalizing] = useState(false);
  const { data: request, isLoading } = usePurchaseRequest(
    isValidId ? requestId : null,
  );
  const requestTypeForNav = basePath.includes('sponsorship-forms')
    ? 'sponsorship_form'
    : 'purchase_request';
  // Same SLA source type for both purchase requests and sponsorship forms.
  const slaEscalate = useSlaEscalateAction(requestTypeForNav, requestId);
  const navParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 50,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      requestType: requestTypeForNav,
      approvalStatus: undefined,
    }),
    [requestTypeForNav],
  );
  const { data: requestListData } = usePurchaseRequests(navParams);
  const requestListItems = requestListData?.data ?? [];
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [approvalDialogOpen, setApprovalDialogOpen] = useState(false);
  const [approverUserId, setApproverUserId] = useState<string>('');
  const [approverEmail, setApproverEmail] = useState('');
  const [approvalLink, setApprovalLink] = useState<string | null>(null);
  const [approvalSending, setApprovalSending] = useState(false);
  const [approvalAction, setApprovalAction] = useState<'create' | 'send' | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [approverComboboxOpen, setApproverComboboxOpen] = useState(false);
  const [settingPending, setSettingPending] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  const [approvalLinkCopying, setApprovalLinkCopying] = useState(false);
  const [conversationSheetOpen, setConversationSheetOpen] = useState(false);
  const [replyComposePrefill, setReplyComposePrefill] = useState<{
    key: number;
    text: string;
  } | null>(null);
  const [openingReplySheet, setOpeningReplySheet] = useState(false);
  const [autoSendingApproval, setAutoSendingApproval] = useState(false);
  const publicViewLinksEnabled = usePublicViewLinksEnabled();

  const { data: systemSettingsPayload } = useQuery({
    queryKey: ['system-settings'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/settings');
      if (!r.ok) throw new Error('Failed to load settings');
      return r.json() as Promise<{ settings?: Record<string, unknown> }>;
    },
    staleTime: 60_000,
  });

  const openUpdateAndReplyInChat = useCallback(async () => {
    if (!request || !requestId || !isValidId) return;
    let viewUrl = '';
    if (publicViewLinksEnabled) {
      try {
        const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
        const { view_url } = await getOrCreateViewLink(requestId, baseUrl);
        viewUrl = view_url ?? '';
      } catch {
        toast.error('Could not generate view link. You can still edit the message in chat.');
      }
    }
    const typeLabelVal = REQUEST_TYPE_LABELS[request.request_type] ?? request.request_type;
    const idPhrase = purchaseRequestNumberReplyPhrase(
      request.request_type,
      request.request_number,
    );
    let fullMessage = `This is the ${idPhrase} for ${typeLabelVal} for project title ${request.project_title ?? ''}.`;
    if (viewUrl) {
      fullMessage += `\n\nView full details: ${viewUrl}`;
    }
    setReplyComposePrefill((p) => ({
      key: (p?.key ?? 0) + 1,
      text: fullMessage,
    }));
    setConversationSheetOpen(true);
  }, [request, requestId, isValidId, publicViewLinksEnabled, request?.request_type]);

  const { data: usersForApprover = [] } = useQuery({
    queryKey: ['users-for-approver'],
    queryFn: getUsersForApproverSelect,
    enabled: approvalDialogOpen,
  });

  const configuredDefaultApproverUserId = useMemo(() => {
    const s = systemSettingsPayload?.settings;
    if (!s || !request?.request_type) return null;
    if (request.request_type === 'purchase_request') {
      const id = s.purchase_request_default_approver_user_id;
      return typeof id === 'string' && id.length > 0 ? id : null;
    }
    const id = s.sponsorship_form_default_approver_user_id;
    return typeof id === 'string' && id.length > 0 ? id : null;
  }, [systemSettingsPayload?.settings, request?.request_type]);

  const configuredDefaultApproverEmail = useMemo(() => {
    const s = systemSettingsPayload?.settings;
    if (!s || !request?.request_type) return null;
    if (request.request_type === 'purchase_request') {
      const e = s.purchase_request_default_approver_email;
      return typeof e === 'string' && e.length > 0 ? e : null;
    }
    const e = s.sponsorship_form_default_approver_email;
    return typeof e === 'string' && e.length > 0 ? e : null;
  }, [systemSettingsPayload?.settings, request?.request_type]);

  const listLabel =
    basePath.includes('sponsorship-forms') ? 'Sponsorship Forms' : 'Purchase Requests';

  // Redirect to the correct section if record type doesn't match (e.g. opened purchase-requests/123 but record is sponsorship_form)
  useEffect(() => {
    if (!requestId || !request?.request_type) return;
    const onSponsorshipForms = basePath.includes('sponsorship-forms');
    if (onSponsorshipForms && request.request_type === 'purchase_request') {
      router.replace(`${PURCHASE_REQUESTS_PATH}/${requestId}`);
    } else if (!onSponsorshipForms && request.request_type === 'sponsorship_form') {
      router.replace(`${SPONSORSHIP_FORMS_PATH}/${requestId}`);
    }
  }, [requestId, request?.request_type, basePath, router]);

  if (!isValidId) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Invalid ID</p>
        <Button
          variant="outline"
          onClick={() => router.push(basePath)}
          className="mt-4"
        >
          Back to {listLabel}
        </Button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!request) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Request not found</p>
        <Button
          variant="outline"
          onClick={() => router.push(basePath)}
          className="mt-4"
        >
          Back to {listLabel}
        </Button>
      </div>
    );
  }

  const typeLabel =
    REQUEST_TYPE_LABELS[request.request_type] ?? request.request_type;
  const isPurchaseRequest = request.request_type === 'purchase_request';
  const expectedPoDisplay =
    request.expected_po_date_text?.trim() ||
    (request.expected_po_date
      ? formatDate(new Date(request.expected_po_date))
      : null);
  const sponsorshipTotalDisplay =
    request.total_project_value_text?.trim() ||
    (request.total_project_value != null
      ? Number(request.total_project_value).toLocaleString()
      : null);

  const approvalStatusNorm = (request.approval_status ?? '').trim();
  const lifecycleStatusNorm = (request.status ?? '').trim().toLowerCase();
  const isDraftLifecycle = lifecycleStatusNorm === 'draft';
  const isSubmittedLifecycle = lifecycleStatusNorm === 'submitted';
  const isDraftLike =
    approvalStatusNorm === '' || approvalStatusNorm === 'draft';
  const isRejected = approvalStatusNorm === 'rejected';
  const isPendingApproval = approvalStatusNorm === 'pending';
  const isApprovedStatus = approvalStatusNorm === 'approved';
  // "Change to pending approval" + "Reject" only when the salesperson has
  // submitted from the portal (status='submitted') AND no approval decision has
  // been recorded yet. Once rejected, only the salesperson re-submits via the
  // portal — reviewer cannot bypass that loop by moving straight to pending.
  const showPrimaryChangeToPending =
    isSubmittedLifecycle &&
    !isApprovedStatus &&
    !isPendingApproval &&
    !isRejected &&
    isDraftLike;
  const showPrimarySendForApproval =
    isPendingApproval && !isApprovedStatus;
  const showRejectSubmitted =
    canSendForApproval && isSubmittedLifecycle && isDraftLike && !isRejected;
  // Customer-service handoff: an approved request enters the CS stage. CS marks it
  // processed or closed; both finalize the customer-service form-SLA stage.
  const isProcessedByCs = lifecycleStatusNorm === 'processed_by_cs';
  const isClosedByCs = lifecycleStatusNorm === 'closed';
  const isCsFinalized = isProcessedByCs || isClosedByCs;
  const showCsActions = isApprovedStatus && !isCsFinalized;
  const csFinalizeLabel = isProcessedByCs
    ? 'Processed by CS'
    : isClosedByCs
      ? 'Closed'
      : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">
            {typeLabel}
            {request.request_number
              ? ` - ${request.request_number}`
              : request.customer_name
                ? ` - ${request.customer_name}`
                : request.project_title
                  ? ` - ${request.project_title}`
                  : ''}
          </h1>
          <p className="text-sm text-muted-foreground">
            {request.request_date
              ? formatDate(new Date(request.request_date))
              : '-'}{' '}
            · {typeLabel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {showPrimaryChangeToPending && (
            <Button
              disabled={settingPending}
              onClick={async () => {
                if (!requestId) return;
                setSettingPending(true);
                try {
                  await setPendingApproval(requestId);
                  queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                  queryClient.invalidateQueries({ queryKey: ['purchase-request-neighbours'] });
                  toast.success('Status set to Pending approval');
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : 'Failed to set pending approval');
                } finally {
                  setSettingPending(false);
                }
              }}
              data-guide-target="procurement.approvals.change-to-pending-approval-button"
            >
              <Clock className="size-4" />
              {settingPending ? 'Updating…' : 'Change to pending approval'}
            </Button>
          )}
          {showRejectSubmitted && (
            <Button
              variant="outline"
              className="border-destructive text-destructive hover:bg-destructive/10"
              disabled={rejecting}
              onClick={() => {
                setRejectReason('');
                setRejectDialogOpen(true);
              }}
            >
              <Trash2 className="size-4" />
              Reject
            </Button>
          )}
          {showPrimarySendForApproval && (
            <Button
              disabled={autoSendingApproval}
              data-guide-target="procurement.approvals.send-for-approval-button"
              onClick={async () => {
                setApprovalLink(null);
                setApprovalError(null);
                if (configuredDefaultApproverUserId) {
                  setAutoSendingApproval(true);
                  try {
                    const baseUrl =
                      typeof window !== 'undefined' ? window.location.origin : undefined;
                    const res = await sendApprovalLink(requestId, {
                      approver_email: configuredDefaultApproverEmail ?? undefined,
                      approver_user_id: configuredDefaultApproverUserId,
                      expires_hours: 24,
                      send_email: true,
                      base_url: baseUrl,
                    });
                    void queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                    if (res.email_sent) {
                      toast.success(
                        `Approval link sent to ${configuredDefaultApproverEmail ?? 'approver'}`,
                      );
                    } else if (res.email_error) {
                      toast.warning(
                        `Link created but email could not be sent: ${res.email_error}`,
                      );
                    } else {
                      toast.success('Approval link created.');
                    }
                  } catch (e) {
                    toast.error(
                      e instanceof Error ? e.message : 'Failed to send approval link',
                    );
                  } finally {
                    setAutoSendingApproval(false);
                  }
                  return;
                }
                setApproverUserId(request.approver_user_id ?? '');
                setApproverEmail(request.approver_email ?? '');
                setApprovalDialogOpen(true);
              }}
            >
              <Send className="size-4" />
              {autoSendingApproval ? 'Sending…' : 'Send for approval'}
            </Button>
          )}
          {showCsActions && canProcess && (
            <Button
              disabled={finalizing}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
              onClick={() => {
                setFinalizeNote('');
                setProcessDialogOpen(true);
              }}
            >
              <BadgeCheck className="size-4" />
              Processed by CS
            </Button>
          )}
          <DetailActionsMenu ariaLabel="Request actions">
            {showCsActions && canClose && (
              <DropdownMenuItem
                disabled={finalizing}
                onClick={() => {
                  setFinalizeNote('');
                  setCloseCsDialogOpen(true);
                }}
              >
                <XCircle className="size-4" />
                Mark as closed
              </DropdownMenuItem>
            )}
            {showPrimarySendForApproval && (
              <DropdownMenuItem
                disabled={approvalLinkCopying}
                onClick={async (e) => {
                  e.preventDefault();
                  if (!requestId) return;
                  const approverUserId =
                    request.approver_user_id ?? configuredDefaultApproverUserId ?? undefined;
                  const approverEmail =
                    request.approver_email ?? configuredDefaultApproverEmail ?? undefined;
                  setApprovalLinkCopying(true);
                  try {
                    const baseUrl =
                      typeof window !== 'undefined' ? window.location.origin : undefined;
                    const res = await sendApprovalLink(requestId, {
                      approver_email: approverEmail,
                      approver_user_id: approverUserId,
                      expires_hours: 24,
                      send_email: false,
                      base_url: baseUrl,
                    });
                    if (res.approval_url) {
                      await navigator.clipboard.writeText(res.approval_url);
                      toast.success('Approval link copied to clipboard');
                    } else {
                      toast.error('Could not generate approval link');
                    }
                  } catch (err) {
                    toast.error(
                      err instanceof Error ? err.message : 'Could not generate approval link',
                    );
                  } finally {
                    setApprovalLinkCopying(false);
                  }
                }}
              >
                <Link2 className="size-4" />
                {approvalLinkCopying ? 'Generating…' : 'Copy approval link'}
              </DropdownMenuItem>
            )}
            {publicViewLinksEnabled && (
              <DropdownMenuItem
                disabled={viewLinkCopying}
                onClick={async (e) => {
                  e.preventDefault();
                  if (!requestId) return;
                  setViewLinkCopying(true);
                  try {
                    const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                    const { view_url } = await getOrCreateViewLink(requestId, baseUrl);
                    if (view_url) {
                      await navigator.clipboard.writeText(view_url);
                      toast.success('View link copied to clipboard');
                    } else {
                      toast.error('Could not generate view link');
                    }
                  } catch {
                    toast.error('Could not generate view link');
                  } finally {
                    setViewLinkCopying(false);
                  }
                }}
              >
                <Link2 className="size-4" />
                {viewLinkCopying ? 'Generating…' : 'Copy view link'}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              disabled={exportingExcel}
              onClick={async (e) => {
                e.preventDefault();
                if (!request) return;
                setExportingExcel(true);
                try {
                  await exportPurchaseRequestOrSponsorshipToExcel(request);
                  toast.success(
                    request.request_type === 'sponsorship_form'
                      ? 'Sponsorship form exported to Excel'
                      : 'Purchase request exported to Excel',
                  );
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : 'Export failed');
                } finally {
                  setExportingExcel(false);
                }
              }}
            >
              <FileDown className="size-4" />
              {exportingExcel ? 'Exporting…' : 'Export to Excel'}
            </DropdownMenuItem>
            {request.respond_inbox_url && (
              <>
                <DropdownMenuItem onClick={() => setConversationSheetOpen(true)}>
                  <ScrollText className="size-4" />
                  Chat records
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={openingReplySheet}
                  onClick={async (e) => {
                    e.preventDefault();
                    setOpeningReplySheet(true);
                    try {
                      await openUpdateAndReplyInChat();
                    } finally {
                      setOpeningReplySheet(false);
                    }
                  }}
                >
                  <Send className="size-4" />
                  {openingReplySheet ? 'Opening…' : 'Update & Reply'}
                </DropdownMenuItem>
              </>
            )}
            <DropdownMenuItem
              disabled={slaEscalate.resolving}
              onClick={slaEscalate.openEscalate}
            >
              <ArrowUpCircle className="size-4" />
              {slaEscalate.resolving ? 'Loading SLA…' : 'Escalate SLA'}
            </DropdownMenuItem>
          </DetailActionsMenu>
          {slaEscalate.dialog}
          <RecordNavigation
            basePath={basePath}
            currentId={requestId}
            items={requestListItems}
            ariaLabel="purchase request"
          />
          <Button
            variant="outline"
            onClick={() => router.push(`${basePath}/${requestId}/edit`)}
          >
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      <Dialog open={approvalDialogOpen} onOpenChange={setApprovalDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Send for approval</DialogTitle>
            <DialogDescription>
              Choose a user to pull their email, or enter an email if the approver is not in the system. Create a one-time approval link only, or create and send it by email to the approver.
            </DialogDescription>
          </DialogHeader>
          {!approvalLink ? (
            <>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Choose approver (optional)</Label>
                  <Popover open={approverComboboxOpen} onOpenChange={setApproverComboboxOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        className="w-full justify-between font-normal"
                      >
                        <span className="truncate">
                          {approverUserId
                            ? (() => {
                                const u = usersForApprover.find((x) => x.id === approverUserId);
                                return u ? `${u.name?.trim() || u.email} (${u.email})` : 'Select approver';
                              })()
                            : 'Select approver'}
                        </span>
                        <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
                      <Command>
                        <CommandInput placeholder="Search approver..." />
                        <CommandList>
                          <CommandEmpty>No approver found.</CommandEmpty>
                          <CommandGroup>
                            <CommandItem
                              value="Enter email only not in system"
                              onSelect={() => {
                                setApproverUserId('');
                                setApproverComboboxOpen(false);
                              }}
                            >
                              Enter email only (not in system)
                              {!approverUserId && <CommandCheck />}
                            </CommandItem>
                            {usersForApprover.map((u) => {
                              const label = `${u.name?.trim() || u.email} ${u.email}`.trim();
                              return (
                                <CommandItem
                                  key={u.id}
                                  value={label}
                                  onSelect={() => {
                                    setApproverUserId(u.id);
                                    setApproverEmail(u.email ?? '');
                                    setApproverComboboxOpen(false);
                                  }}
                                >
                                  <span className="truncate">
                                    {u.name?.trim() || u.email} ({u.email})
                                  </span>
                                  {approverUserId === u.id && <CommandCheck />}
                                </CommandItem>
                              );
                            })}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="approver_email">Approver email</Label>
                  <Input
                    id="approver_email"
                    type="email"
                    value={approverEmail}
                    onChange={(e) => setApproverEmail(e.target.value)}
                    placeholder="approver@example.com"
                  />
                </div>
              </div>
              {approvalError && (
                <p className="text-sm text-destructive">{approvalError}</p>
              )}
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setApprovalDialogOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="outline"
                  data-guide-target="procurement.approvals.create-link-only-button"
                  disabled={!approverEmail.trim() || approvalSending}
                  onClick={async () => {
                    setApprovalError(null);
                    setApprovalSending(true);
                    setApprovalAction('create');
                    try {
                      const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                      const res = await sendApprovalLink(requestId, {
                        approver_email: approverEmail.trim(),
                        approver_user_id: approverUserId || undefined,
                        expires_hours: 24,
                        send_email: false,
                        base_url: baseUrl,
                      });
                      const url = res.approval_url.startsWith('http')
                        ? res.approval_url
                        : typeof window !== 'undefined'
                          ? `${window.location.origin}${res.approval_url.startsWith('/') ? res.approval_url : `/${res.approval_url}`}`
                          : res.approval_url;
                      setApprovalLink(url);
                      void queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                      toast.success('Approval link created. Copy the link below to share.');
                    } catch (e) {
                      setApprovalError(e instanceof Error ? e.message : 'Failed to create link');
                    } finally {
                      setApprovalSending(false);
                      setApprovalAction(null);
                    }
                  }}
                >
                  {approvalSending && approvalAction === 'create' ? 'Creating…' : 'Create link only'}
                </Button>
                <Button
                  data-guide-target="procurement.approvals.create-link-and-send-button"
                  disabled={!approverEmail.trim() || approvalSending}
                  onClick={async () => {
                    setApprovalError(null);
                    setApprovalSending(true);
                    setApprovalAction('send');
                    try {
                      const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                      const res = await sendApprovalLink(requestId, {
                        approver_email: approverEmail.trim(),
                        approver_user_id: approverUserId || undefined,
                        expires_hours: 24,
                        send_email: true,
                        base_url: baseUrl,
                      });
                      const url = res.approval_url.startsWith('http')
                        ? res.approval_url
                        : typeof window !== 'undefined'
                          ? `${window.location.origin}${res.approval_url.startsWith('/') ? res.approval_url : `/${res.approval_url}`}`
                          : res.approval_url;
                      setApprovalLink(url);
                      void queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                      if (res.email_sent) {
                        toast.success(`Approval link created and sent to ${approverEmail.trim()}`);
                      } else if (res.email_error) {
                        toast.warning(`Link created but email could not be sent: ${res.email_error}. You can copy the link below.`);
                      }
                    } catch (e) {
                      setApprovalError(e instanceof Error ? e.message : 'Failed to create link');
                    } finally {
                      setApprovalSending(false);
                      setApprovalAction(null);
                    }
                  }}
                >
                  {approvalSending && approvalAction === 'send' ? 'Creating & sending…' : 'Create link & send email'}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <div className="space-y-2">
                <Label>Approval link (one-time use)</Label>
                <div className="flex gap-2">
                  <Input readOnly value={approvalLink} className="font-mono text-sm" />
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={() => {
                      void navigator.clipboard.writeText(approvalLink);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }}
                  >
                    {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={() => { setApprovalDialogOpen(false); setApprovalLink(null); }}>
                  Done
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <PurchaseRequestDeleteDialog
        open={deleteDialogOpen}
        closeDialog={() => setDeleteDialogOpen(false)}
        request={request}
        entityLabel={typeLabel}
        onSuccess={() => router.push(basePath)}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {isPurchaseRequest ? (
          <div className="lg:col-span-2 max-w-5xl mx-auto w-full">
            <Card className="border-2 shadow-sm">
              <CardContent className="pt-6 pb-8 px-5 sm:px-10">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{typeLabel}</Badge>
                    <Badge
                      variant={
                        request.approval_status === 'approved'
                          ? 'primary'
                          : request.approval_status === 'rejected'
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      {request.approval_status === 'pending'
                        ? 'Pending approval'
                        : request.approval_status === 'approved'
                          ? (csFinalizeLabel ?? 'Approved')
                          : request.approval_status === 'rejected'
                            ? 'Rejected'
                            : isSubmittedLifecycle
                              ? 'Submitted'
                              : isDraftLifecycle
                                ? 'Draft'
                                : (request.approval_status || request.status || 'Draft')}
                    </Badge>
                  </div>
                </div>
                <h2 className="text-center text-xl font-semibold tracking-tight border-b border-border pb-4 mb-6">
                  Purchase Request
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-5">
                  <div>
                    <p className="text-sm text-muted-foreground">Purchase request number</p>
                    <p className="font-medium tabular-nums">{request.request_number || '—'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Date</p>
                    <p className="font-medium">
                      {request.request_date
                        ? formatDate(new Date(request.request_date))
                        : '—'}
                    </p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Customer Name</p>
                    <p className="font-medium">{request.customer_name || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Project Title</p>
                    <p className="font-medium">{request.project_title || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Purpose</p>
                    <p className="font-medium">{request.purpose || '—'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Expected date of delivery</p>
                    <p className="font-medium">
                      {request.expected_delivery_date
                        ? formatDate(new Date(request.expected_delivery_date))
                        : '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Expected date to receive PO</p>
                    <p className="font-medium">{expectedPoDisplay || '—'}</p>
                  </div>
                  {(request.approver_email || request.approver_user_id) && !request.approved_at && (
                    <div className="sm:col-span-2">
                      <p className="text-sm text-muted-foreground">Approver</p>
                      <p className="font-medium">
                        {request.approver_display_name
                          ? `${request.approver_display_name} (${request.approver_email})`
                          : request.approver_email}
                      </p>
                    </div>
                  )}
                  {request.respond_inbox_url && (
                    <div className="sm:col-span-2">
                      <p className="text-sm text-muted-foreground">Respond conversation</p>
                      <div className="flex flex-col sm:flex-row sm:items-center gap-2 py-0.5">
                        <a
                          href={request.respond_inbox_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline text-sm break-all font-medium"
                        >
                          {request.respond_inbox_url}
                        </a>
                        <Button
                          variant="outline"
                          size="sm"
                          className="shrink-0 w-fit"
                          onClick={() => setConversationSheetOpen(true)}
                          aria-label="Open chat records"
                        >
                          <MessageSquare className="size-4 mr-1" />
                          Chat
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-8">
                  <p className="text-sm font-medium mb-3">Line items</p>
                  {request.lines && request.lines.length > 0 ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-12">#</TableHead>
                          <TableHead>Item Code</TableHead>
                          <TableHead className="w-28">Qty</TableHead>
                          <TableHead>Remark</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {request.lines.map((line, idx) => (
                          <TableRow key={line.id}>
                            <TableCell>{idx + 1}</TableCell>
                            <TableCell>{line.item_code ?? '—'}</TableCell>
                            <TableCell>{line.quantity ?? '—'}</TableCell>
                            <TableCell>{line.remark ?? '—'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <p className="text-sm text-muted-foreground">No line items.</p>
                  )}
                </div>

                <PurchaseRequestSignoffFooter request={request} variant="detailCard" />
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="lg:col-span-2 max-w-5xl mx-auto w-full">
            <Card className="border-2 shadow-sm">
              <CardContent className="pt-6 pb-8 px-5 sm:px-10">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{typeLabel}</Badge>
                    <Badge
                      variant={
                        request.approval_status === 'approved'
                          ? 'primary'
                          : request.approval_status === 'rejected'
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      {request.approval_status === 'pending'
                        ? 'Pending approval'
                        : request.approval_status === 'approved'
                          ? (csFinalizeLabel ?? 'Approved')
                          : request.approval_status === 'rejected'
                            ? 'Rejected'
                            : isSubmittedLifecycle
                              ? 'Submitted'
                              : isDraftLifecycle
                                ? 'Draft'
                                : (request.approval_status || request.status || 'Draft')}
                    </Badge>
                  </div>
                </div>
                <h2 className="text-center text-xl font-semibold tracking-tight border-b border-border pb-4 mb-6">
                  Project Sales Sponsorship Form
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-5">
                  <div>
                    <p className="text-sm text-muted-foreground">Sponsorship form number</p>
                    <p className="font-medium tabular-nums">{request.request_number || '—'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Date</p>
                    <p className="font-medium">
                      {request.request_date
                        ? formatDate(new Date(request.request_date))
                        : '—'}
                    </p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Customer Name</p>
                    <p className="font-medium">{request.customer_name || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Delivery Address</p>
                    <p className="font-medium whitespace-pre-wrap">{request.delivery_address || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Project Title</p>
                    <p className="font-medium">{request.project_title || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Total Project Value</p>
                    <p className="font-medium">{sponsorshipTotalDisplay || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Sponsor Subject</p>
                    <p className="font-medium">{request.sponsor_subject || '—'}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-sm text-muted-foreground">Date of Delivery</p>
                    <p className="font-medium">
                      {request.expected_delivery_date
                        ? formatDate(new Date(request.expected_delivery_date))
                        : '—'}
                    </p>
                  </div>
                  {(request.approver_email || request.approver_user_id) && !request.approved_at && (
                    <div className="sm:col-span-2">
                      <p className="text-sm text-muted-foreground">Approver</p>
                      <p className="font-medium">
                        {request.approver_display_name
                          ? `${request.approver_display_name} (${request.approver_email})`
                          : request.approver_email}
                      </p>
                    </div>
                  )}
                  {request.respond_inbox_url && (
                    <div className="sm:col-span-2">
                      <p className="text-sm text-muted-foreground">Respond conversation</p>
                      <div className="flex flex-col sm:flex-row sm:items-center gap-2 py-0.5">
                        <a
                          href={request.respond_inbox_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline text-sm break-all font-medium"
                        >
                          {request.respond_inbox_url}
                        </a>
                        <Button
                          variant="outline"
                          size="sm"
                          className="shrink-0 w-fit"
                          onClick={() => setConversationSheetOpen(true)}
                          aria-label="Open chat records"
                        >
                          <MessageSquare className="size-4 mr-1" />
                          Chat
                        </Button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-8">
                  <p className="text-sm font-medium mb-3">Line items</p>
                  {request.lines && request.lines.length > 0 ? (
                    <>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-12">NO.</TableHead>
                            <TableHead>Item Code</TableHead>
                            <TableHead className="w-24">Qty</TableHead>
                            <TableHead className="w-28">U/P</TableHead>
                            <TableHead className="w-28">Total</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {request.lines.map((line, idx) => (
                            <TableRow key={line.id}>
                              <TableCell>{idx + 1}</TableCell>
                              <TableCell>{line.item_code ?? '—'}</TableCell>
                              <TableCell>{line.quantity ?? '—'}</TableCell>
                              <TableCell>
                                {line.unit_price != null ? Number(line.unit_price).toLocaleString() : '—'}
                              </TableCell>
                              <TableCell>
                                {line.total != null ? Number(line.total).toLocaleString() : '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      {request.grand_total != null && (
                        <div className="mt-4 flex justify-end">
                          <p className="text-sm font-semibold">
                            Grand Total: {Number(request.grand_total).toLocaleString()}
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">No line items.</p>
                  )}
                </div>

                <PurchaseRequestSignoffFooter request={request} variant="detailCard" />
              </CardContent>
            </Card>
          </div>
        )}

        <div className="lg:col-span-2">
          <PurchaseRequestAttachmentsSection
            requestId={requestId}
            attachments={request.attachments}
          />
        </div>

        {request?.respond_inbox_url && (
          <Sheet
            open={conversationSheetOpen}
            onOpenChange={(open) => {
              setConversationSheetOpen(open);
              if (!open) {
                setReplyComposePrefill(null);
              }
            }}
          >
            <SheetContent side="right" className="flex flex-col w-full sm:max-w-lg overflow-y-auto">
              <SheetHeader className="sr-only">
                <SheetTitle>Chat Records</SheetTitle>
              </SheetHeader>
              <div className="flex-1 min-h-0 pt-2">
                <PurchaseRequestConversationPanel
                  requestId={requestId}
                  requestNumber={request.request_number ?? undefined}
                  canReply
                  respondInboxUrl={request.respond_inbox_url}
                  showAsPopup
                  replyComposePrefill={replyComposePrefill}
                  onGetViewLink={
                    publicViewLinksEnabled
                      ? async () => {
                          const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                          const res = await getOrCreateViewLink(requestId, baseUrl);
                          return res.view_url ?? '';
                        }
                      : undefined
                  }
                />
              </div>
            </SheetContent>
          </Sheet>
        )}

        <AuditTrail entityType="purchase_request" entityId={requestId} title="Audit Trail" />

        <AlertDialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Reject this submission</AlertDialogTitle>
              <AlertDialogDescription>
                Provide a reason. This will mark the request as rejected and send an
                update message to the contact via Respond.io. This action cannot be
                undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-2 py-2">
              <Label htmlFor="reject-reason">Reason</Label>
              <Textarea
                id="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Why is this submission being rejected?"
                rows={4}
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={rejecting}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                data-guide-target="procurement.approvals.reject-confirm-button"
                disabled={rejecting || !rejectReason.trim()}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                onClick={async (e) => {
                  e.preventDefault();
                  if (!rejectReason.trim()) {
                    toast.error('Reason is required');
                    return;
                  }
                  setRejecting(true);
                  try {
                    await rejectSubmittedPurchaseRequest(requestId, rejectReason.trim());
                    queryClient.invalidateQueries({
                      queryKey: ['purchase-request', requestId],
                    });
                    queryClient.invalidateQueries({
                      queryKey: ['purchase-request-neighbours'],
                    });
                    toast.success('Submission rejected; contact has been notified.');
                    setRejectDialogOpen(false);
                  } catch (err) {
                    toast.error(
                      err instanceof Error ? err.message : 'Failed to reject',
                    );
                  } finally {
                    setRejecting(false);
                  }
                }}
              >
                {rejecting ? 'Rejecting…' : 'Confirm reject'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog open={processDialogOpen} onOpenChange={setProcessDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Mark as processed by CS?</AlertDialogTitle>
              <AlertDialogDescription>
                This closes the customer-service stage and sets the status to{' '}
                <span className="font-medium">processed by CS</span>. A status update
                is sent to the contact. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-1 py-2">
              <Label htmlFor="process-note">Message to contact (optional)</Label>
              <Textarea
                id="process-note"
                value={finalizeNote}
                onChange={(e) => setFinalizeNote(e.target.value)}
                placeholder="Add an optional note for the customer…"
                rows={3}
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={finalizing}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                disabled={finalizing}
                className="bg-emerald-600 text-white hover:bg-emerald-700"
                onClick={async (e) => {
                  e.preventDefault();
                  setFinalizing(true);
                  try {
                    await processPurchaseRequestByCs(requestId, finalizeNote);
                    queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                    queryClient.invalidateQueries({ queryKey: ['purchase-request-neighbours'] });
                    toast.success('Marked as processed by CS.');
                    setProcessDialogOpen(false);
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : 'Failed to mark processed by CS');
                  } finally {
                    setFinalizing(false);
                  }
                }}
              >
                {finalizing ? 'Saving…' : 'Processed by CS'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog open={closeCsDialogOpen} onOpenChange={setCloseCsDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Mark as closed?</AlertDialogTitle>
              <AlertDialogDescription>
                Closes the customer-service stage and sets the status to{' '}
                <span className="font-medium">closed</span> (could not be fulfilled).
                A status update is sent to the contact. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-1 py-2">
              <Label htmlFor="close-note">Message to contact (optional)</Label>
              <Textarea
                id="close-note"
                value={finalizeNote}
                onChange={(e) => setFinalizeNote(e.target.value)}
                placeholder="Add an optional note for the customer…"
                rows={3}
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={finalizing}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                disabled={finalizing}
                onClick={async (e) => {
                  e.preventDefault();
                  setFinalizing(true);
                  try {
                    await closePurchaseRequestByCs(requestId, finalizeNote);
                    queryClient.invalidateQueries({ queryKey: ['purchase-request', requestId] });
                    queryClient.invalidateQueries({ queryKey: ['purchase-request-neighbours'] });
                    toast.success('Marked as closed.');
                    setCloseCsDialogOpen(false);
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : 'Failed to close request');
                  } finally {
                    setFinalizing(false);
                  }
                }}
              >
                {finalizing ? 'Saving…' : 'Confirm close'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
