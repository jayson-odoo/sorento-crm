'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Link2, ExternalLink, MessageSquare } from 'lucide-react';
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
import { useComplaint, useUpdateComplaint } from '../hooks/useComplaints';
import { getOrCreateComplaintViewLink } from '../services/complaintService';
import { toast } from 'sonner';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import ComplaintDeleteDialog from './complaint-delete-dialog';
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

  const openUpdateAndReplyInChatFromText = useCallback(
    async (technicalTeamResponseText: string) => {
      let viewUrl = '';
      if (publicViewLinksEnabled) {
        try {
          const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
          const res = await getOrCreateComplaintViewLink(complaintId, baseUrl);
          viewUrl = res.view_url ?? '';
        } catch {
          // continue without view link
        }
      }
      const technicalResponse = (technicalTeamResponseText ?? '').trim();
      const doNumber = (complaint?.delivery_order_number ?? '').toString().trim();
      const doPart = doNumber ? ` for delivery order ${doNumber}` : '';
      const linkPart = viewUrl ? ` ${viewUrl}` : '';
      const fullMessage = technicalResponse.startsWith('There has been an update')
        ? technicalResponse
        : `There has been an update regarding your complaint${doPart}${linkPart}: ${technicalResponse}`;
      setReplyComposePrefill((p) => ({
        key: (p?.key ?? 0) + 1,
        text: fullMessage,
      }));
      setConversationSheetOpen(true);
    },
    [complaintId, complaint, publicViewLinksEnabled],
  );

  const openUpdateAndReplyInChat = useCallback(async () => {
    if (!complaint) return;
    await openUpdateAndReplyInChatFromText(complaint.technical_team_response ?? '');
  }, [complaint, openUpdateAndReplyInChatFromText]);

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
            {complaint.delivery_order_number || 'Complaint Details'}
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
              setEditTechnicalResponseValue(complaint.technical_team_response ?? '');
              setEditTechnicalResponseOpen(true);
            }}
          >
            <Edit className="size-4 mr-1" />
            Edit technical team response
          </Button>
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
                disabled={openingReplySheet}
                onClick={async () => {
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

      <Dialog open={editTechnicalResponseOpen} onOpenChange={setEditTechnicalResponseOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit technical team response</DialogTitle>
            <DialogDescription>
              Save updates the record only. Use Update &amp; Reply to open the chat with this text prefilled so you can send to the contact.
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
                disabled={updateComplaintMutation.isPending || openingReplySheet}
                onClick={async () => {
                  setOpeningReplySheet(true);
                  try {
                    await updateComplaintMutation.mutateAsync({
                      id: complaintId,
                      data: { technical_team_response: editTechnicalResponseValue.trim() },
                    });
                    setEditTechnicalResponseOpen(false);
                    await openUpdateAndReplyInChatFromText(editTechnicalResponseValue);
                  } catch {
                    // toast from mutation
                  } finally {
                    setOpeningReplySheet(false);
                  }
                }}
              >
                <Send className="size-4 mr-1" />
                {openingReplySheet ? 'Opening…' : 'Update & Reply'}
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
              <p className="text-sm text-muted-foreground">Technical Team Response</p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditTechnicalResponseValue(complaint.technical_team_response ?? '');
                  setEditTechnicalResponseOpen(true);
                }}
                aria-label="Edit technical team response"
              >
                <Edit className="size-4" />
                Edit
              </Button>
            </div>
            <p className="font-medium whitespace-pre-wrap">
              {complaint.technical_team_response || '-'}
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
                technicalTeamResponse={complaint.technical_team_response}
                replyComposePrefill={replyComposePrefill}
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
