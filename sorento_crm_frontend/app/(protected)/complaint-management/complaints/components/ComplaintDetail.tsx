'use client';

import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Link2, ExternalLink, MessageSquare, CheckCircle2, XCircle, BadgeCheck, FileDown, ArrowUpCircle, Ban } from 'lucide-react';
import { getFormSLATrackers, escalateFormTracking } from '@/app/(protected)/sla-management/_shared/formSLAService';
import { SlaActiveTrackerControls } from '@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls';
import { SlaExtendMenuItem, SlaExtendDialog } from '@/app/(protected)/sla-management/_shared/SlaExtendAction';
import { useHandlingLock } from '@/app/(protected)/sla-management/_shared/useHandlingLock';
import { HandlingLockBanner } from '@/app/(protected)/sla-management/_shared/HandlingLockBanner';
import { HandlingLockReleaseMenuItem } from '@/app/(protected)/sla-management/_shared/HandlingLockActions';
import { RejectionReasonBanner } from '@/components/common/RejectionReasonBanner';
import { VoidBanner } from '@/components/common/VoidBanner';
import { VoidDialog } from '@/components/common/VoidDialog';
import { useFormVoid } from '@/hooks/useFormVoid';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { complaintStatusPillClass, complaintStatusLabel } from '@/lib/complaint-status';
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
  useProcessComplaintByCs,
  useCloseComplaint,
  useExportComplaintPdf,
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
import { EntityDownloadsButton } from '@/components/my-downloads/EntityDownloadsButton';
import { usePublicViewLinksEnabled } from '@/hooks/usePublicViewLinksEnabled';

interface ComplaintDetailProps {
  complaintId: string;
}

// Status label + pill colour come from the shared map so the internal view and
// the customer portal always tally. See lib/complaint-status.
const statusPillClass = complaintStatusPillClass;
const statusLabel = complaintStatusLabel;

export default function ComplaintDetail({ complaintId }: ComplaintDetailProps) {
  const router = useRouter();

  // Don't fetch if it's "new" or invalid
  const isValidId = complaintId && complaintId !== 'new' && complaintId !== 'edit';
  const { data: complaint, isLoading } = useComplaint(isValidId ? complaintId : null);
  const updateComplaintMutation = useUpdateComplaint();
  const updateComplaintAndReplyMutation = useUpdateComplaintAndReply();
  const approveComplaintMutation = useApproveComplaint();
  const rejectComplaintMutation = useRejectComplaint();
  const processComplaintMutation = useProcessComplaintByCs();
  const closeComplaintMutation = useCloseComplaint();
  const exportPdfMutation = useExportComplaintPdf();
  const notifyRootCauseMutation = useNotifyComplaintRootCause();
  const notifyResolutionMutation = useNotifyComplaintResolution();
  const canApprove = useHasPermission('complaint_management.complaints.approve');
  const canReject = useHasPermission('complaint_management.complaints.reject');
  const canProcess = useHasPermission('complaint_management.complaints.resolve');
  const canClose = useHasPermission('complaint_management.complaints.close');
  const canVoid = useHasPermission('complaint_management.complaints.void');
  const [voidDialogOpen, setVoidDialogOpen] = useState(false);
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [processDialogOpen, setProcessDialogOpen] = useState(false);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [finalizeNote, setFinalizeNote] = useState('');
  const [notifyRootCauseOpen, setNotifyRootCauseOpen] = useState(false);
  const [notifyResolutionOpen, setNotifyResolutionOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  // Escalate the active form-SLA stage from the gear menu.
  const queryClient = useQueryClient();
  const [escalateOpen, setEscalateOpen] = useState(false);
  // Extend the active form-SLA deadline (with reason) from the gear menu — same
  // flow as conversation SLA (notifies the next/parent tier).
  const [extendOpen, setExtendOpen] = useState(false);
  const [escalateReason, setEscalateReason] = useState('');
  const [escalating, setEscalating] = useState(false);
  const { data: slaTrackers } = useQuery({
    // Key on status so the escalation banner clears on resolve without a refresh.
    queryKey: ['form-sla-trackers', 'complaint', complaintId, complaint?.status],
    queryFn: () => getFormSLATrackers('complaint', complaintId),
    enabled: !!isValidId,
  });
  const activeTracker = (slaTrackers ?? []).find((t) => !t.is_resolved) ?? null;
  // Handling-lock ("I'm handling this") — live off the form-SLA handling tracker query.
  const handlingLock = useHandlingLock({
    sourceEntityType: 'complaint',
    sourceEntityId: isValidId ? complaintId : null,
    entityKey: complaint?.status,
  });
  // A voided complaint is fully read-only — suppress every business CTA.
  const isVoided = (complaint?.status ?? '').trim().toLowerCase() === 'voided';
  const businessCtasEnabled = handlingLock.businessCtasEnabled && !isVoided;
  const voidMutation = useFormVoid('complaints-management/complaints', complaintId, {
    queryKeysToInvalidate: [['complaint', complaintId]],
  });
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1 min-w-0">
          <h1 className="text-2xl font-bold break-words">
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
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${statusPillClass(complaint.status)}`}
                >
                  {statusLabel(complaint.status)}
                </span>
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
          {/* Business CTAs hide (not disable) while the handling lock is held by
              someone else / unclaimed — keeps the header uncluttered. When the
              lock does not bite (tier 1, flag off, or I hold it) businessCtasEnabled
              is true and they render on their normal status+permission gates. */}
          {businessCtasEnabled && (
            <Button
              // Submitted = the technical team's response is the next action, so make
              // it the primary CTA; otherwise it's a secondary edit.
              variant={complaint.status === 'submitted' ? 'primary' : 'outline'}
              size="sm"
              data-guide-target="complaint-management.complaints.tech-team.edit-response"
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
          )}
          {businessCtasEnabled && complaint.status === 'responded' && canApprove && (
            <Button
              size="sm"
              data-guide-target="complaint-management.complaints.tech-team.approve"
              disabled={approveComplaintMutation.isPending}
              onClick={() => setApproveDialogOpen(true)}
            >
              <CheckCircle2 className="size-4 mr-1" />
              Approve
            </Button>
          )}
          {businessCtasEnabled && complaint.status === 'responded' && canReject && (
            <Button
              variant="outline"
              size="sm"
              data-guide-target="complaint-management.complaints.tech-team.reject"
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
          {businessCtasEnabled && complaint.status === 'approved' && canProcess && (
            <Button
              size="sm"
              disabled={processComplaintMutation.isPending}
              onClick={() => {
                setFinalizeNote('');
                setProcessDialogOpen(true);
              }}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              <BadgeCheck className="size-4 mr-1" />
              Processed by CS
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            data-guide-target="complaint-management.complaints.download-pdf"
            disabled={exportPdfMutation.isPending}
            onClick={() => exportPdfMutation.mutate(complaintId)}
          >
            <FileDown className="size-4 mr-1" />
            {exportPdfMutation.isPending ? 'Preparing…' : 'Download PDF'}
          </Button>
          <EntityDownloadsButton
            entityType="complaint"
            entityId={complaintId}
            label={complaint.complaint_number ?? undefined}
            className="h-8 border border-border"
          />
          <DetailActionsMenu ariaLabel="Complaint actions">
            {activeTracker && (
              <DropdownMenuItem
                onSelect={(e) => {
                  e.preventDefault();
                  setEscalateReason('');
                  setEscalateOpen(true);
                }}
              >
                <ArrowUpCircle className="size-4" />
                Escalate SLA
              </DropdownMenuItem>
            )}
            <SlaExtendMenuItem
              activeTracker={activeTracker}
              onSelect={() => setExtendOpen(true)}
            />
            <HandlingLockReleaseMenuItem
              state={handlingLock.state}
              onRelease={handlingLock.release}
            />
            {businessCtasEnabled && complaint.status === 'approved' && canClose && (
              <DropdownMenuItem
                disabled={closeComplaintMutation.isPending}
                onClick={() => {
                  setFinalizeNote('');
                  setCloseDialogOpen(true);
                }}
              >
                <XCircle className="size-4" />
                Mark as closed
              </DropdownMenuItem>
            )}
            {!isVoided && (
              <DropdownMenuItem
                onClick={() =>
                  router.push(`/complaint-management/complaints/${complaintId}/edit`)
                }
              >
                <Edit className="size-4" />
                Edit
              </DropdownMenuItem>
            )}
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
            {canUseRespondChat && !isVoided && (
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
            {canVoid && !isVoided && (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setVoidDialogOpen(true)}
              >
                <Ban className="size-4" />
                Void
              </DropdownMenuItem>
            )}
            {!isVoided && (
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setDeleteDialogOpen(true)}
              >
                <Trash2 className="size-4" />
                Delete
              </DropdownMenuItem>
            )}
          </DetailActionsMenu>
          <ComplaintNavigation complaintId={complaintId} />
        </div>
      </div>

      <HandlingLockBanner
        state={handlingLock.state}
        tracker={handlingLock.tracker}
        onClaim={handlingLock.claim}
        onTakeOver={handlingLock.takeOver}
      />

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

      <AlertDialog open={processDialogOpen} onOpenChange={setProcessDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark complaint as processed by CS?</AlertDialogTitle>
            <AlertDialogDescription>
              This closes the customer-service stage and sets the status to{' '}
              <span className="font-medium">processed by CS</span>. A status update is
              sent to the contact. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
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
            <AlertDialogCancel disabled={processComplaintMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={processComplaintMutation.isPending}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await processComplaintMutation.mutateAsync({
                    id: complaintId,
                    note: finalizeNote,
                  });
                  setProcessDialogOpen(false);
                } catch {
                  // toast handled in hook
                }
              }}
            >
              Processed by CS
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={closeDialogOpen} onOpenChange={setCloseDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark complaint as closed?</AlertDialogTitle>
            <AlertDialogDescription>
              Use this when the complaint can&apos;t be resolved. The status is set to{' '}
              <span className="font-medium">closed</span> (not resolved), but the
              customer-service SLA stage is closed. A status update is sent to the
              contact. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
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
            <AlertDialogCancel disabled={closeComplaintMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={closeComplaintMutation.isPending}
              className="bg-slate-600 text-white hover:bg-slate-700"
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await closeComplaintMutation.mutateAsync({
                    id: complaintId,
                    note: finalizeNote,
                  });
                  setCloseDialogOpen(false);
                } catch {
                  // toast handled in hook
                }
              }}
            >
              Mark as closed
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={escalateOpen} onOpenChange={setEscalateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Escalate SLA</DialogTitle>
            <DialogDescription>
              Force-escalate the current SLA stage to the next tier and reassign per the
              escalation policy. Optionally add a reason.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="cmp-escalate-reason">Reason*</Label>
            <Textarea
              id="cmp-escalate-reason"
              value={escalateReason}
              onChange={(e) => setEscalateReason(e.target.value)}
              placeholder="Why escalate now?"
              rows={3}
              className="resize-none"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEscalateOpen(false)} disabled={escalating}>
              Cancel
            </Button>
            <Button
              disabled={escalating || !activeTracker}
              onClick={async () => {
                if (!activeTracker) return;
                setEscalating(true);
                try {
                  const res = await escalateFormTracking(activeTracker.id, escalateReason.trim());
                  queryClient.invalidateQueries({ queryKey: ['form-sla-trackers', 'complaint', complaintId] });
                  handlingLock.refresh(); // lock banner keys on a separate query — refetch so it appears without reload
                  toast.success(`Escalated to tier ${res.current_tier}`);
                  setEscalateOpen(false);
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : 'Failed to escalate');
                } finally {
                  setEscalating(false);
                }
              }}
            >
              {escalating ? 'Escalating…' : 'Escalate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SlaExtendDialog
        activeTracker={activeTracker}
        label={`Complaint${complaint.complaint_number ? ` · ${complaint.complaint_number}` : ''}`}
        open={extendOpen}
        onOpenChange={setExtendOpen}
        onExtended={() =>
          queryClient.invalidateQueries({ queryKey: ['form-sla-trackers', 'complaint', complaintId] })
        }
      />

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
              data-guide-target="complaint-management.complaints.tech-team.save-response"
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
                data-guide-target="complaint-management.complaints.tech-team.update-reply"
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

      {complaint.status === 'rejected' && (
        <RejectionReasonBanner
          reason={complaint.rejection_reason}
          // Phase 2: BE to emit `rejected_by_name` / `rejected_by_wa_phone` / `rejected_at`
          // on the complaint detail DTO (rejecter resolved from `rejected_by` = respond_user_id).
          rejectedByName={(complaint as { rejected_by_name?: string | null }).rejected_by_name ?? undefined}
          rejectedByWaPhone={(complaint as { rejected_by_wa_phone?: string | null }).rejected_by_wa_phone ?? undefined}
          rejectedAt={(complaint as { rejected_at?: string | null }).rejected_at ?? undefined}
        />
      )}

      <VoidBanner
        voided={isVoided}
        voidedByName={complaint.voided_by_name}
        voidedAt={complaint.voided_at}
        voidReason={complaint.void_reason}
      />

      <VoidDialog
        open={voidDialogOpen}
        onOpenChange={setVoidDialogOpen}
        isPending={voidMutation.isPending}
        onConfirm={(reason) => voidMutation.mutateAsync({ void_reason: reason })}
      />

      <SlaActiveTrackerControls
        activeTracker={activeTracker}
        label={`Complaint${complaint.complaint_number ? ` · ${complaint.complaint_number}` : ''}`}
        onExtended={() =>
          void queryClient.invalidateQueries({
            queryKey: ['form-sla-trackers', 'complaint', complaintId],
          })
        }
      />

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
            <div className="md:col-span-2">
              <p className="text-sm text-muted-foreground mb-1">Products</p>
              {(() => {
                const lines =
                  complaint.product_lines && complaint.product_lines.length > 0
                    ? complaint.product_lines
                    : (complaint.product_code || '')
                        .split(',')
                        .map((c) => c.trim())
                        .filter(Boolean)
                        .map((code, i) => ({
                          product_code: code,
                          product_type: (complaint.product_type || '').split(',')[i]?.trim() || null,
                          quantity: (complaint.quantity || '').split(',')[i]?.trim() || null,
                        }));
                if (lines.length === 0) {
                  return <p className="font-medium">-</p>;
                }
                return (
                  <div className="overflow-x-auto rounded-md border">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-left">Product code</th>
                          <th className="px-3 py-2 text-left">Product type</th>
                          <th className="w-24 px-3 py-2 text-left">Qty</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lines.map((line, i) => (
                          <tr key={i} className="border-t">
                            <td className="px-3 py-2 font-medium">{line.product_code}</td>
                            <td className="px-3 py-2">{line.product_type || '-'}</td>
                            <td className="px-3 py-2">{line.quantity || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
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
              <p className="text-sm text-muted-foreground">Delivery Address</p>
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
          {/* Replacement / fulfilment delivery orders now live in their own
              "Fulfilment DOs" tab (see the complaint detail page wrapper). */}
          <div>
            <p className="text-sm text-muted-foreground">Assignee</p>
            <p className="font-medium">
              {complaint.assigned_to_name ?? complaint.assigned_to ?? '-'}
            </p>
          </div>
          {complaint.status && (
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <p className="font-medium">{statusLabel(complaint.status)}</p>
            </div>
          )}
          <div>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">Root Cause</p>
              <Button
                variant="outline"
                size="sm"
                data-guide-target="complaint-management.complaints.tech-team.notify-root-cause"
                onClick={() => setNotifyRootCauseOpen(true)}
                disabled={
                  isVoided ||
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
                data-guide-target="complaint-management.complaints.tech-team.notify-resolution"
                onClick={() => setNotifyResolutionOpen(true)}
                disabled={
                  isVoided ||
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
              {businessCtasEnabled && (
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
              )}
            </div>
            <p className="font-medium whitespace-pre-wrap">
              {displayComplaintTechnicalResponse(complaint.technical_team_response) || '-'}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Required on site support</p>
            <p className="font-medium">
              {complaint.required_on_site_support === true ? 'Yes' : 'No'}
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
