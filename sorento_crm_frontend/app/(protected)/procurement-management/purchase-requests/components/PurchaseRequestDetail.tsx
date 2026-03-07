'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Copy, Check, ChevronDown, Clock, MessageSquare, FileDown, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Textarea } from '@/components/ui/textarea';
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
import { usePurchaseRequest, usePurchaseRequestNeighbours, useUpdatePurchaseRequestAndReply } from '../hooks/usePurchaseRequests';
import { formatDate } from '@/lib/helpers';
import PurchaseRequestDeleteDialog from './purchase-request-delete-dialog';
import AuditTrail from '@/components/audit/AuditTrail';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import {
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { sendApprovalLink, setPendingApproval, getUsersForApproverSelect, getOrCreateViewLink } from '../services/purchaseRequestService';
import { exportPurchaseRequestOrSponsorshipToExcel } from '../lib/purchase-request-excel-export';
import { toast } from 'sonner';
import PurchaseRequestAttachmentsSection from './PurchaseRequestAttachmentsSection';

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
  const { data: request, isLoading } = usePurchaseRequest(
    isValidId ? requestId : null,
  );
  const requestTypeForNav = basePath.includes('sponsorship-forms')
    ? 'sponsorship_form'
    : 'purchase_request';
  const { data: neighbours } = usePurchaseRequestNeighbours(
    isValidId ? requestId : null,
    requestTypeForNav,
  );
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
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');
  const [exportingExcel, setExportingExcel] = useState(false);
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  const updateAndReplyMutation = useUpdatePurchaseRequestAndReply();

  const { data: usersForApprover = [] } = useQuery({
    queryKey: ['users-for-approver'],
    queryFn: getUsersForApproverSelect,
    enabled: approvalDialogOpen,
  });

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">
            {typeLabel} - {request.customer_name || request.project_title || request.id}
          </h1>
          <p className="text-sm text-muted-foreground">
            {request.request_date
              ? formatDate(new Date(request.request_date))
              : '-'}{' '}
            · {typeLabel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DetailActionsMenu ariaLabel="Request actions">
            {request.approval_status === 'pending' ? (
              <DropdownMenuItem
                onClick={() => {
                  setApprovalLink(null);
                  setApprovalError(null);
                  setApproverUserId(request.approver_user_id ?? '');
                  setApproverEmail(request.approver_email ?? '');
                  setApprovalDialogOpen(true);
                }}
              >
                <Send className="size-4" />
                Send for approval
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
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
              >
                <Clock className="size-4" />
                {settingPending ? 'Updating…' : 'Change to pending approval'}
              </DropdownMenuItem>
            )}
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
              <DropdownMenuItem
                disabled={updateAndReplyMutation.isPending}
                onClick={async () => {
                  const typeLabelVal =
                    REQUEST_TYPE_LABELS[request.request_type] ?? request.request_type;
                  let defaultReply =
                    `This is the form number ${request.request_number ?? ''} for ${typeLabelVal} for project title ${request.project_title ?? ''}.`;
                  try {
                    if (requestId) {
                      const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                      const { view_url } = await getOrCreateViewLink(requestId, baseUrl);
                      if (view_url) {
                        defaultReply += `\n\nView full details: ${view_url}`;
                      }
                    }
                  } catch {
                    toast.error('Could not generate view link. You can still send the message.');
                  }
                  setReplyMessage(defaultReply);
                  setUpdateAndReplyDialogOpen(true);
                }}
              >
                <MessageSquare className="size-4" />
                {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
              </DropdownMenuItem>
            )}
          </DetailActionsMenu>
          <RecordNavigation
            basePath={basePath}
            prevId={neighbours?.prev_id ?? null}
            nextId={neighbours?.next_id ?? null}
            currentIndex={(neighbours?.current_index ?? 1) - 1}
            totalCount={neighbours?.total_count ?? undefined}
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

      <Dialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Update & Reply</DialogTitle>
            <DialogDescription>
              This message will be sent to the conversation in Respond. You can edit it below before
              sending.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="reply_message">Message to send</Label>
              <Textarea
                id="reply_message"
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="This is the form number ... for ... for project title ..."
                rows={4}
                className="resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setUpdateAndReplyDialogOpen(false)}
              disabled={updateAndReplyMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              disabled={updateAndReplyMutation.isPending || !replyMessage.trim()}
              onClick={async () => {
                if (!requestId) return;
                try {
                  await updateAndReplyMutation.mutateAsync({
                    id: requestId,
                    data: {
                      request_number: request.request_number ?? undefined,
                      reply_message: replyMessage.trim(),
                    },
                  });
                  setUpdateAndReplyDialogOpen(false);
                  setReplyMessage('');
                } catch {
                  // toast handled by mutation
                }
              }}
            >
              {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
            </Button>
          </DialogFooter>
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
        <Card>
          <CardHeader>
            <CardTitle>Header</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Type</p>
                <Badge variant="secondary">{typeLabel}</Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge
                  variant={
                    request.approval_status === 'approved'
                      ? 'primary'
                      : request.approval_status === 'rejected'
                        ? 'destructive'
                        : 'secondary'
                  }
                >
                  {!request.approval_status || request.approval_status === ''
                    ? 'Draft'
                    : request.approval_status === 'pending'
                      ? 'Pending approval'
                      : request.approval_status === 'approved'
                        ? 'Approved'
                        : request.approval_status === 'rejected'
                          ? 'Rejected'
                          : request.approval_status}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Form number</p>
                <p className="font-medium">{request.request_number || '—'}</p>
              </div>
              {request.approved_at && (
                <div>
                  <p className="text-sm text-muted-foreground">Approved at</p>
                  <p className="font-medium">{formatDate(new Date(request.approved_at))}</p>
                </div>
              )}
              {request.approved_by && (
                <div>
                  <p className="text-sm text-muted-foreground">Approved by</p>
                  <p className="font-medium">{request.approved_by}</p>
                </div>
              )}
              {(request.approver_email || request.approver_user_id) && !request.approved_at && (
                <div>
                  <p className="text-sm text-muted-foreground">Approver</p>
                  <p className="font-medium">
                    {request.approver_display_name
                      ? `${request.approver_display_name} (${request.approver_email})`
                      : request.approver_email}
                  </p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Request Date</p>
                <p className="font-medium">
                  {request.request_date
                    ? formatDate(new Date(request.request_date))
                    : '-'}
                </p>
              </div>
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Customer</p>
                <p className="font-medium">{request.customer_name || '-'}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Project Title</p>
                <p className="font-medium">{request.project_title || '-'}</p>
              </div>
              {request.request_type !== 'sponsorship_form' && (
                <div>
                  <p className="text-sm text-muted-foreground">Purpose</p>
                  <p className="font-medium">{request.purpose || '-'}</p>
                </div>
              )}
              {request.request_type === 'sponsorship_form' && (
                <>
                  <div className="md:col-span-2">
                    <p className="text-sm text-muted-foreground">Delivery Address</p>
                    <p className="font-medium">{request.delivery_address || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Total Project Value</p>
                    <p className="font-medium">
                      {request.total_project_value != null ? Number(request.total_project_value).toLocaleString() : '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Sponsor Subject</p>
                    <p className="font-medium">{request.sponsor_subject || '-'}</p>
                  </div>
                </>
              )}
              <div>
                <p className="text-sm text-muted-foreground">
                  {request.request_type === 'sponsorship_form' ? 'Date of Delivery' : 'Expected Delivery'}
                </p>
                <p className="font-medium">
                  {request.expected_delivery_date
                    ? formatDate(new Date(request.expected_delivery_date))
                    : '-'}
                </p>
              </div>
              {request.request_type !== 'sponsorship_form' && (
                <div>
                  <p className="text-sm text-muted-foreground">Expected PO Date</p>
                  <p className="font-medium">
                    {request.expected_po_date_text ??
                      (request.expected_po_date
                        ? formatDate(new Date(request.expected_po_date))
                        : '-')}
                  </p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Requested By</p>
                <p className="font-medium">{request.requested_by || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Requested At</p>
                <p className="font-medium">
                  {request.requested_at
                    ? formatDate(new Date(request.requested_at))
                    : '-'}
                </p>
              </div>
              {request.respond_inbox_url && (
                <div className="md:col-span-2">
                  <p className="text-sm text-muted-foreground">Respond conversation</p>
                  <a
                    href={request.respond_inbox_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline text-sm break-all font-medium"
                  >
                    {request.respond_inbox_url}
                  </a>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Line Items</CardTitle>
          </CardHeader>
          <CardContent>
            {request.lines && request.lines.length > 0 ? (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Item Code</TableHead>
                      <TableHead>Quantity</TableHead>
                      {request.request_type === 'sponsorship_form' && (
                        <>
                          <TableHead>Unit Price</TableHead>
                          <TableHead>Total</TableHead>
                        </>
                      )}
                      {request.request_type !== 'sponsorship_form' && <TableHead>Remark</TableHead>}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {request.lines.map((line, idx) => (
                      <TableRow key={line.id}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{line.item_code ?? '-'}</TableCell>
                        <TableCell>{line.quantity ?? '-'}</TableCell>
                        {request.request_type === 'sponsorship_form' && (
                          <>
                            <TableCell>
                              {line.unit_price != null ? Number(line.unit_price).toLocaleString() : '-'}
                            </TableCell>
                            <TableCell>
                              {line.total != null ? Number(line.total).toLocaleString() : '-'}
                            </TableCell>
                          </>
                        )}
                        {request.request_type !== 'sponsorship_form' && (
                          <TableCell>{line.remark ?? '-'}</TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {request.request_type === 'sponsorship_form' && request.grand_total != null && (
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
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
          <PurchaseRequestAttachmentsSection
            requestId={requestId}
            attachments={request.attachments}
          />
        </div>

        <AuditTrail entityType="purchase_request" entityId={requestId} title="Audit Trail" />
      </div>
    </div>
  );
}
