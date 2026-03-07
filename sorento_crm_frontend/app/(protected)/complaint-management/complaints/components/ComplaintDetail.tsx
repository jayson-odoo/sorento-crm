'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Send, Link2, ExternalLink } from 'lucide-react';
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
import { useComplaint, useUpdateComplaintAndReply } from '../hooks/useComplaints';
import { getOrCreateComplaintViewLink } from '../services/complaintService';
import { toast } from 'sonner';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import ComplaintDeleteDialog from './complaint-delete-dialog';
import ComplaintNavigation from './ComplaintNavigation';
import ComplaintManualAttachmentsSection from './ComplaintManualAttachmentsSection';
import AuditTrail from '@/components/audit/AuditTrail';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';

interface ComplaintDetailProps {
  complaintId: string;
}

export default function ComplaintDetail({ complaintId }: ComplaintDetailProps) {
  const router = useRouter();
  
  // Don't fetch if it's "new" or invalid
  const isValidId = complaintId && complaintId !== 'new' && complaintId !== 'edit';
  const { data: complaint, isLoading } = useComplaint(isValidId ? complaintId : null);
  const updateAndReplyMutation = useUpdateComplaintAndReply();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');
  const [replyViewUrl, setReplyViewUrl] = useState('');
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  
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
        <div className="flex gap-2">
          <DetailActionsMenu ariaLabel="Complaint actions">
            <DropdownMenuItem
              onClick={() =>
                router.push(`/complaint-management/complaints/${complaintId}/edit`)
              }
            >
              <Edit className="size-4" />
              Edit
            </DropdownMenuItem>
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
            <DropdownMenuItem
              disabled={updateAndReplyMutation.isPending}
              onClick={async () => {
                let viewUrl = '';
                try {
                  const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                  const res = await getOrCreateComplaintViewLink(complaintId, baseUrl);
                  viewUrl = res.view_url ?? '';
                  setReplyViewUrl(viewUrl);
                } catch {
                  setReplyViewUrl('');
                }
                const doNumber = (complaint.delivery_order_number ?? '').toString().trim();
                const doPart = doNumber ? ` for delivery order ${doNumber}` : '';
                const linkPart = viewUrl ? ` ${viewUrl}` : '';
                const technicalResponse = (complaint.technical_team_response ?? '').trim();
                const fullMessage = `There has been an update regarding your complaint${doPart}${linkPart}: ${technicalResponse}`;
                setReplyMessage(fullMessage);
                setUpdateAndReplyDialogOpen(true);
              }}
            >
              <Send className="size-4" />
              {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
            </DropdownMenuItem>
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

      <Dialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Update & Reply</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="complaint-detail-reply-message">Message that will be sent to the contact</Label>
              <Textarea
                id="complaint-detail-reply-message"
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="Message to send..."
                rows={6}
                className="resize-none font-mono text-sm"
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
                try {
                  await updateAndReplyMutation.mutateAsync({
                    id: complaintId,
                    data: { technical_team_response: replyMessage.trim() },
                  });
                  setUpdateAndReplyDialogOpen(false);
                  setReplyMessage('');
                  setReplyViewUrl('');
                } catch {
                  // toast from mutation
                }
              }}
            >
              {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
            </Button>
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
              <a
                href={complaint.respond_inbox_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline text-sm break-all font-medium"
              >
                {complaint.respond_inbox_url}
              </a>
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
            <p className="text-sm text-muted-foreground">Technical Team Response</p>
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
    </div>
  );
}
