'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Link2, ExternalLink, MessageSquare, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import {
  useComplaint,
  useUpdateComplaint,
  useUpdateComplaintAndReply,
  useApproveComplaint,
  useRejectComplaint,
  useNotifyComplaintRootCause,
  useNotifyComplaintResolution,
} from '../hooks/useComplaints';
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
import {
  getOrCreateComplaintViewLink,
  displayComplaintTechnicalResponse,
} from '../services/complaintService';
import { toast } from 'sonner';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import ComplaintDeleteDialog from './ComplaintDeleteDialog';
import ComplaintNavigation from './ComplaintNavigation';
import ComplaintManualAttachmentsSection from './ComplaintManualAttachmentsSection';
import ComplaintConversationPanel from './ComplaintConversationPanel';
import AuditTrail from '@/components/audit/AuditTrail';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { usePublicViewLinksEnabled } from '@/hooks/usePublicViewLinksEnabled';

interface ComplaintDetailProps {
  complaintId: string;
}

export default function ComplaintDetail({ complaintId }: ComplaintDetailProps) {
  const router = useRouter();

  // Don't fetch if it's "new" or invalid
  const isValidId = complaintId && complaintId !== 'new' && complaintId !== 'edit';
  const { data: complaint, isLoading } = useComplaint(isValidId ? complaintId : null);
  const updateComplaintMutation = useUpdateComplaint();
  const updateComplaintAndReplyMutation = useUpdateComplaintAndReply();
  const approveComplaintMutation = useApproveComplaint();
  const rejectComplaintMutation = useRejectComplaint();
  const notifyRootCauseMutation = useNotifyComplaintRootCause();
  const notifyResolutionMutation = useNotifyComplaintResolution();
  const canApprove = useHasPermission('complaint_management.complaints.approve');
  const canReject = useHasPermission('complaint_management.complaints.reject');
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [notifyRootCauseOpen, setNotifyRootCauseOpen] = useState(false);
  const [notifyResolutionOpen, setNotifyResolutionOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  const publicViewLinksEnabled = usePublicViewLinksEnabled();
  const [editTechnicalResponseOpen, setEditTechnicalResponseOpen] = useState(false);
  const [editTechnicalResponseValue, setEditTechnicalResponseValue] = useState('');
  const [replyComposePrefill, setReplyComposePrefill] = useState<{
    key: number;
    text: string;
  } | null>(null);
  const [conversationSheetOpen, setConversationSheetOpen] = useState(false);
  const [openingReplySheet, setOpeningReplySheet] = useState(false);

  const sendComplaintUpdateAndReplyViaRespond = useCallback(
    async (technicalTeamResponseText: string) => {
      const technicalResponse = displayComplaintTechnicalResponse(
        (technicalTeamResponseText ?? '').trim(),
      ).trim();
      if (!technicalResponse) {
        toast.error('Enter a technical team response before sending.');
        return;
      }
      await updateComplaintAndReplyMutation.mutateAsync({
        id: complaintId,
        data: { technical_team_response: technicalResponse },
      });
    },
    [complaintId, updateComplaintAndReplyMutation],
  );

  const sendComplaintUpdateAndReplyFromSavedRecord = useCallback(async () => {
    if (!complaint) return;
    await sendComplaintUpdateAndReplyViaRespond(complaint.technical_team_response ?? '');
  }, [complaint, sendComplaintUpdateAndReplyViaRespond]);

  if (!isValidId) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Invalid complaint ID</p>
        <Button
          variant="outline"
          onClick={() => router.push('/complaint-management/complaints')}
          className="mt-4"
        >
          Back to Complaints
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

  if (!complaint) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Complaint not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/complaint-management/complaints')}
          className="mt-4"
        >
          Back to Complaints
        </Button>
      </div>
    );
  }

  const canUseRespondChat = !!complaint.respond_inbox_url;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">
            {complaint.complaint_number || 'None'}
          </h1>
          <p className="text-sm text-muted-foreground">
            Complaint Date:{' '}
            {complaint.complaint_date
              ? formatDate(new Date(complaint.complaint_date))
              : '-'}
            {complaint.status && (
              <>
                {' · '}
                <span className="capitalize font-medium">{complaint.status}</span>
              </>
            )}
          </p>
          {complaint.last_responded_at && (
            <p className="text-sm text-muted-foreground">
              Last responded: {formatDate(new Date(complaint.last_responded_at))}
              {(complaint.last_responded_by_name ?? complaint.last_responded_by) &&
                ` by ${complaint.last_responded_by_name ?? complaint.last_responded_by}`}
            </p>
          )}
        </div>
        <div className="flex gap-2 flex-wrap items-center justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditTechnicalResponseValue(
                displayComplaintTechnicalResponse(complaint.technical_team_response ?? ''),
              );
              setEditTechnicalResponseOpen(true);
            }}
          >
            <Edit className="size-4 mr-1" />
            Edit technical team response
          </Button>
          {complaint.status === 'responded' && canApprove && (
            <Button
              size="sm"
              disabled={approveComplaintMutation.isPending}
              onClick={() => setApproveDialogOpen(true)}
            >
              <CheckCircle2 className="size-4 mr-1" />
              Approve
            </Button>
          )}
          {complaint.status === 'responded' && canReject && (
            <Button
              variant="outline"
              size="sm"
              disabled={rejectComplaintMutation.isPending}
              onClick={() => {
                setRejectReason('');
                setRejectDialogOpen(true);
              }}
              className="text-destructive border-destructive/40 hover:bg-destructive/10"
            >
              <XCircle className="size-4 mr-1" />
              Reject
            </Button>
          )}
          <DetailActionsMenu ariaLabel="Complaint actions">
            <DropdownMenuItem
              onClick={() =>
                router.push(`/complaint-management/complaints/${complaintId}/edit`)
              }
            >
              <Edit className="size-4" />
              Edit
            </DropdownMenuItem>
            {canUseRespondChat && (
              <DropdownMenuItem onClick={() => setConversationSheetOpen(true)}>
                <MessageSquare className="size-4" />
                Chat records
              </DropdownMenuItem>
            )}
            {publicViewLinksEnabled && (
              <DropdownMenuItem
                disabled={viewLinkCopying}
                onClick={async () => {
                  try {
                    setViewLinkCopying(true);
                    const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                    const { view_url } = await getOrCreateComplaintViewLink(complaintId, baseUrl);
                    await navigator.clipboard.writeText(view_url);
                    toast.success('View link copied to clipboard');
                  } catch {
                    toast.error('Failed to copy view link');
                  } finally {
                    setViewLinkCopying(false);
                  }
                }}
              >
                <Link2 className="size-4" />
                {viewLinkCopying ? 'Copying…' : 'Copy view link'}
              </DropdownMenuItem>
            )}
            {publicViewLinksEnabled && (
              <DropdownMenuItem
                onClick={async () => {
                  try {
                    const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                    const { view_url } = await getOrCreateComplaintViewLink(complaintId, baseUrl);
                    window.open(view_url, '_blank');
                  } catch {
                    toast.error('Failed to open view link');
                  }
                }}
              >
                <ExternalLink className="size-4" />
                View in system
              </DropdownMenuItem>
            )}
            {canUseRespondChat && (
              <DropdownMenuItem
                disabled={openingReplySheet || updateComplaintAndReplyMutation.isPending}
                onClick={async () => {
                  setOpeningReplySheet(true);
                  try {
                    await sendComplaintUpdateAndReplyFromSavedRecord();
                  } finally {
                    setOpeningReplySheet(false);
                  }
                }}
              >
                <Send className="size-4" />
                {openingReplySheet || updateComplaintAndReplyMutation.isPending
                  ? 'Sending…'
                  : 'Update & Reply'}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => setDeleteDialogOpen(true)}
            >
              <Trash2 className="size-4" />
              Delete
            </DropdownMenuItem>
          </DetailActionsMenu>
          <ComplaintNavigation complaintId={complaintId} />
        </div>
      </div>

      {complaint && (
        <ComplaintDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          complaint={complaint}
          onSuccess={() => {
            router.push('/complaint-management/complaints');
          }}
        />
      )}

      <AlertDialog open={notifyRootCauseOpen} onOpenChange={setNotifyRootCauseOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Notify salesperson on root cause?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to update the salesperson on{' '}
              <span className="font-medium">{complaint.root_cause_name ?? '—'}</span>? A
              Respond.io message will be sent to the customer&apos;s conversation.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={notifyRootCauseMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={notifyRootCauseMutation.isPending}
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await notifyRootCauseMutation.mutateAsync(complaintId);
                  setNotifyRootCauseOpen(false);
                } catch {
                  /* toast in hook */
                }
              }}
            >
              Notify
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={notifyResolutionOpen} onOpenChange={setNotifyResolutionOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Notify salesperson on resolution?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to update the salesperson on{' '}
              <span className="font-medium">{complaint.resolution_name ?? '—'}</span>? A
              Respond.io message will be sent to the customer&apos;s conversation.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={notifyResolutionMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={notifyResolutionMutation.isPending}
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await notifyResolutionMutation.mutateAsync(complaintId);
                  setNotifyResolutionOpen(false);
                } catch {
                  /* toast in hook */
                }
              }}
            >
              Notify
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Approve complaint?</AlertDialogTitle>
            <AlertDialogDescription>
              The contact will be notified via Respond.io that the complaint status changed to{' '}
              <span className="font-medium">approved</span>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={approveComplaintMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={approveComplaintMutation.isPending}
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await approveComplaintMutation.mutateAsync(complaintId);
                  setApproveDialogOpen(false);
                } catch {
                  // toast handled in hook
                }
              }}
            >
              Approve
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reject complaint?</DialogTitle>
            <DialogDescription>
              Provide a reason. The contact will be notified via Respond.io that the complaint
              status changed to <span className="font-medium">rejected</span>, including the reason
              you enter.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="complaint-reject-reason">Rejection reason</Label>
            <Textarea
              id="complaint-reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Why is this complaint being rejected?"
              rows={4}
              className="resize-none"
            />
          </div>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              onClick={() => setRejectDialogOpen(false)}
              disabled={rejectComplaintMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={rejectComplaintMutation.isPending || !rejectReason.trim()}
              onClick={async () => {
                const reason = rejectReason.trim();
                if (!reason) {
                  toast.error('Enter a rejection reason.');
                  return;
                }
                try {
                  await rejectComplaintMutation.mutateAsync({
                    id: complaintId,
                    rejection_reason: reason,
                  });
                  setRejectDialogOpen(false);
                } catch {
                  // toast handled in hook
                }
              }}
            >
              {rejectComplaintMutation.isPending ? 'Rejecting…' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editTechnicalResponseOpen} onOpenChange={setEditTechnicalResponseOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit technical team response</DialogTitle>
            <DialogDescription>
              Save updates the record only. Update &amp; Reply saves your text and sends it to the contact.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="edit-technical-response">Technical team response</Label>
            <Textarea
              id="edit-technical-response"
              value={editTechnicalResponseValue}
              onChange={(e) => setEditTechnicalResponseValue(e.target.value)}
              placeholder="Response text..."
              rows={5}
              className="resize-none"
            />
          </div>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setEditTechnicalResponseOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="outline"
              disabled={updateComplaintMutation.isPending}
              onClick={async () => {
                try {
                  await updateComplaintMutation.mutateAsync({
                    id: complaintId,
                    data: { technical_team_response: editTechnicalResponseValue.trim() },
                  });
                  setEditTechnicalResponseOpen(false);
                } catch {
                  // toast from mutation
                }
              }}
            >
              {updateComplaintMutation.isPending ? 'Saving…' : 'Save only'}
            </Button>
            {canUseRespondChat && (
              <Button
                variant="primary"
                disabled={
                  updateComplaintMutation.isPending ||
                  openingReplySheet ||
                  updateComplaintAndReplyMutation.isPending
                }
                onClick={async () => {
                  setOpeningReplySheet(true);
                  try {
                    await sendComplaintUpdateAndReplyViaRespond(editTechnicalResponseValue);
                    setEditTechnicalResponseOpen(false);
                  } catch {
                    // toast from mutation
                  } finally {
                    setOpeningReplySheet(false);
                  }
                }}
              >
                <Send className="size-4 mr-1" />
                {openingReplySheet || updateComplaintAndReplyMutation.isPending
                  ? 'Sending…'
                  : 'Update & Reply'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Complaint Information */}
      <Card>
        <CardHeader>
          <CardTitle>Complaint Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Delivery Order Number</p>
              <p className="font-medium">{complaint.delivery_order_number || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Complaint Date</p>
              <p className="font-medium">
                {complaint.complaint_date
                  ? formatDate(new Date(complaint.complaint_date))
                  : '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Customer Type</p>
              <p className="font-medium">{complaint.customer_type || '-'}</p>
            </div>
            {complaint.customer_type_others && (
              <div>
                <p className="text-sm text-muted-foreground">Customer Type (Other)</p>
                <p className="font-medium">{complaint.customer_type_others}</p>
              </div>
            )}
            <div>
              <p className="text-sm text-muted-foreground">Within Warranty</p>
              <p className="font-medium">{complaint.within_warranty || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Product Type</p>
              <p className="font-medium">{complaint.product_type || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Defects Discovered</p>
              <p className="font-medium">{complaint.defects_discovered || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Complaint Type</p>
              {complaint.complaint_type ? (
                <Badge variant="secondary">{complaint.complaint_type}</Badge>
              ) : (
                <p className="font-medium">-</p>
              )}
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Product Code</p>
              <p className="font-medium">{complaint.product_code || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Salesperson</p>
              <p className="font-medium">{complaint.salesperson || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Customer Name</p>
              <p className="font-medium">{complaint.customer_name || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Contact Person</p>
              <p className="font-medium">{complaint.contact_person || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Contact Number</p>
              <p className="font-medium">{complaint.contact_number || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Project Title</p>
              <p className="font-medium">{complaint.project_title || '-'}</p>
            </div>
          </div>
          {complaint.customer_address && (
            <div>
              <p className="text-sm text-muted-foreground">Customer Address</p>
              <p className="font-medium">{complaint.customer_address}</p>
            </div>
          )}
          {complaint.defect_description && (
            <div>
              <p className="text-sm text-muted-foreground">Defect Description</p>
              <p className="font-medium whitespace-pre-wrap">
                {complaint.defect_description}
              </p>
            </div>
          )}
          {complaint.respond_inbox_url && (
            <div>
              <p className="text-sm text-muted-foreground">Respond conversation</p>
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 py-0.5">
                <a
                  href={complaint.respond_inbox_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline text-sm break-all font-medium"
                >
                  {complaint.respond_inbox_url}
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
          <div>
            <p className="text-sm text-muted-foreground">Assignee</p>
            <p className="font-medium">
              {complaint.assigned_to_name ?? complaint.assigned_to ?? '-'}
            </p>
          </div>
          {complaint.status && (
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <p className="font-medium capitalize">{complaint.status}</p>
            </div>
          )}
          <div>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">Root Cause</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setNotifyRootCauseOpen(true)}
                disabled={
                  !complaint.root_cause_id ||
                  !complaint.respond_inbox_url ||
                  notifyRootCauseMutation.isPending
                }
                aria-label="Notify salesperson on root cause"
              >
                Notify salesperson
              </Button>
            </div>
            <p className="font-medium">{complaint.root_cause_name ?? '-'}</p>
            {complaint.root_cause_notified_at && (
              <p className="text-xs text-muted-foreground">
                Last notified {formatDateTimeInMalaysia(complaint.root_cause_notified_at)}
              </p>
            )}
          </div>
          <div>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">Resolution</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setNotifyResolutionOpen(true)}
                disabled={
                  !complaint.resolution_id ||
                  !complaint.respond_inbox_url ||
                  notifyResolutionMutation.isPending
                }
                aria-label="Notify salesperson on resolution"
              >
                Notify salesperson
              </Button>
            </div>
            <p className="font-medium">{complaint.resolution_name ?? '-'}</p>
            {complaint.resolution_notified_at && (
              <p className="text-xs text-muted-foreground">
                Last notified {formatDateTimeInMalaysia(complaint.resolution_notified_at)}
              </p>
            )}
          </div>
          <div>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">Technical Team Response</p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditTechnicalResponseValue(
                    displayComplaintTechnicalResponse(complaint.technical_team_response ?? ''),
                  );
                  setEditTechnicalResponseOpen(true);
                }}
                aria-label="Edit technical team response"
              >
                <Edit className="size-4" />
                Edit
              </Button>
            </div>
            <p className="font-medium whitespace-pre-wrap">
              {displayComplaintTechnicalResponse(complaint.technical_team_response) || '-'}
            </p>
          </div>
          {complaint.last_responded_at && (
            <div>
              <p className="text-sm text-muted-foreground">Last responded</p>
              <p className="font-medium">
                {formatDate(new Date(complaint.last_responded_at))}
                {complaint.last_responded_by_name && ` by ${complaint.last_responded_by_name}`}
              </p>
            </div>
          )}
          <div>
            <p className="text-sm text-muted-foreground">Created at</p>
            <p className="font-medium">
              {complaint.created_at
                ? formatDateTimeInMalaysia(complaint.created_at)
                : '-'}
            </p>
          </div>
        </CardContent>
      </Card>

      <ComplaintManualAttachmentsSection
        complaintId={complaintId}
        attachments={complaint.attachments ?? []}
      />

      <AuditTrail entityType="complaint" entityId={complaintId} title="Audit Trail" />

      {canUseRespondChat && (
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
              <ComplaintConversationPanel
                complaintId={complaintId}
                canReply={canUseRespondChat}
                respondInboxUrl={complaint.respond_inbox_url}
                showAsPopup
                technicalTeamResponse={displayComplaintTechnicalResponse(
                  complaint.technical_team_response,
                )}
                replyComposePrefill={replyComposePrefill}
                contactName={complaint.contact_person || complaint.customer_name}
                contactPhone={complaint.contact_number}
                onGetViewLink={
                  publicViewLinksEnabled
                    ? async () => {
                        const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                        const res = await getOrCreateComplaintViewLink(complaintId, baseUrl);
                        return res.view_url ?? '';
                      }
                    : undefined
                }
              />
            </div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
