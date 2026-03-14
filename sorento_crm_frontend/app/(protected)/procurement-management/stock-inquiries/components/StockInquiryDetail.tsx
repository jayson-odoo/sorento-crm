'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, FileDown, Send, Link2, ExternalLink, CheckCircle, XCircle, RotateCcw, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
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
import { exportStockInquiryToExcel } from '../utils/exportStockInquiryToExcel';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useStockInquiry,
  useStockInquiryNeighbours,
  useUpdateStockInquiry,
  useUpdateStockInquiryAndReply,
  useSubmitStockInquiryForProjectSales,
  useProjectSalesApproveStockInquiry,
  useProjectSalesRejectStockInquiry,
  usePurchasingRejectStockInquiry,
  useReopenStockInquiry,
} from '../hooks/useStockInquiries';
import { getOrCreateStockInquiryViewLink } from '../services/stockInquiryService';
import { toast } from 'sonner';
import { formatDate } from '@/lib/helpers';
import { useHasPermission } from '@/hooks/usePermissions';
import StockInquiryDeleteDialog from './stock-inquiry-delete-dialog';
import AuditTrail from '@/components/audit/AuditTrail';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import StockInquiryAttachmentsSection from './StockInquiryAttachmentsSection';
import StockInquiryConversationPanel from './StockInquiryConversationPanel';
import { STOCK_INQUIRY_STATUS_LABELS } from '../types/stockInquiry.types';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';

interface StockInquiryDetailProps {
  inquiryId: string;
}

export default function StockInquiryDetail({
  inquiryId,
}: StockInquiryDetailProps) {
  const router = useRouter();
  const isValidId = inquiryId && inquiryId !== 'new' && inquiryId !== 'edit';
  const { data: inquiry, isLoading } = useStockInquiry(
    isValidId ? inquiryId : null,
  );
  const { data: neighbours } = useStockInquiryNeighbours(isValidId ? inquiryId : null);
  const updateInquiryMutation = useUpdateStockInquiry();
  const updateAndReplyMutation = useUpdateStockInquiryAndReply();
  const submitForProjectSalesMutation = useSubmitStockInquiryForProjectSales();
  const projectSalesApproveMutation = useProjectSalesApproveStockInquiry();
  const projectSalesRejectMutation = useProjectSalesRejectStockInquiry();
  const purchasingRejectMutation = usePurchasingRejectStockInquiry();
  const reopenMutation = useReopenStockInquiry();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectAction, setRejectAction] = useState<'project_sales' | 'purchasing' | null>(null);
  const [reopenDialogOpen, setReopenDialogOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState('');
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [conversationSheetOpen, setConversationSheetOpen] = useState(false);
  const [editPurchasingResponseOpen, setEditPurchasingResponseOpen] = useState(false);
  const [editPurchasingResponseValue, setEditPurchasingResponseValue] = useState('');
  const canSubmitForProjectSales = useHasPermission('procurement.stock_inquiries.submit_for_project_sales');
  const canProjectSalesApprove = useHasPermission('procurement.stock_inquiries.project_sales_approve');
  const canProjectSalesReject = useHasPermission('procurement.stock_inquiries.project_sales_reject');
  const canPurchasingReject = useHasPermission('procurement.stock_inquiries.purchasing_reject');
  const canReopen = useHasPermission('procurement.stock_inquiries.reopen');

  const handleExportExcel = async () => {
    if (!inquiry) return;
    setExporting(true);
    try {
      await exportStockInquiryToExcel(inquiry);
    } finally {
      setExporting(false);
    }
  };

  if (!isValidId) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Invalid stock inquiry ID</p>
        <Button
          variant="outline"
          onClick={() => router.push('/procurement-management/stock-inquiries')}
          className="mt-4"
        >
          Back to Stock Inquiries
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

  if (!inquiry) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Stock inquiry not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/procurement-management/stock-inquiries')}
          className="mt-4"
        >
          Back to Stock Inquiries
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
            Stock Inquiry - {inquiry.product_code || 'Details'}
          </h1>
          <p className="text-sm text-muted-foreground">
            Created:{' '}
            {inquiry.created_at
              ? formatDate(new Date(inquiry.created_at))
              : '-'}
            {inquiry.status && (
              <>
                {' · '}
                <Badge variant={inquiry.status === 'rejected' ? 'destructive' : inquiry.status === 'responded' ? 'success' : 'secondary'}>
                  {STOCK_INQUIRY_STATUS_LABELS[inquiry.status] ?? inquiry.status}
                </Badge>
              </>
            )}
          </p>
          {inquiry.last_responded_at && (
            <p className="text-sm text-muted-foreground">
              Last responded: {formatDate(new Date(inquiry.last_responded_at))}
              {(inquiry.last_responded_by_name ?? inquiry.last_responded_by) &&
                ` by ${inquiry.last_responded_by_name ?? inquiry.last_responded_by}`}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Workflow actions: visible next to header */}
          {inquiry.status === 'new' && canSubmitForProjectSales && (
            <Button
              variant="primary"
              size="sm"
              disabled={submitForProjectSalesMutation.isPending}
              onClick={() => submitForProjectSalesMutation.mutate(inquiryId)}
            >
              {submitForProjectSalesMutation.isPending ? 'Submitting…' : 'Submit for project sales'}
            </Button>
          )}
          {inquiry.status === 'pending_project_sales' && (
            <>
              {canProjectSalesApprove && (
                <Button
                  variant="primary"
                  size="sm"
                  disabled={projectSalesApproveMutation.isPending}
                  onClick={() => projectSalesApproveMutation.mutate(inquiryId)}
                >
                  <CheckCircle className="size-4 mr-1" />
                  {projectSalesApproveMutation.isPending ? 'Approving…' : 'Approve (send to purchasing)'}
                </Button>
              )}
              {canProjectSalesReject && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={projectSalesRejectMutation.isPending}
                  onClick={() => {
                    setRejectAction('project_sales');
                    setRejectReason('');
                    setRejectDialogOpen(true);
                  }}
                >
                  <XCircle className="size-4 mr-1" />
                  Reject
                </Button>
              )}
            </>
          )}
          {inquiry.status === 'pending_purchasing' && (
            <>
              {inquiry.respond_inbox_url && (
                <Button
                  variant="primary"
                  size="sm"
                  disabled={updateAndReplyMutation.isPending}
                  onClick={async () => {
                    let viewUrl = '';
                    try {
                      const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                      const res = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
                      viewUrl = res.view_url ?? '';
                    } catch {
                      // continue
                    }
                    const purchasingResponse = (inquiry.purchasing_response ?? '').trim();
                    const linkPart = viewUrl ? ` ${viewUrl}` : '';
                    const fullMessage = `There is a response to your stock inquiry${linkPart}: ${purchasingResponse}`;
                    setReplyMessage(fullMessage);
                    setUpdateAndReplyDialogOpen(true);
                  }}
                >
                  <Send className="size-4 mr-1" />
                  Update & Reply
                </Button>
              )}
              {canPurchasingReject && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={purchasingRejectMutation.isPending}
                  onClick={() => {
                    setRejectAction('purchasing');
                    setRejectReason('');
                    setRejectDialogOpen(true);
                  }}
                >
                  <XCircle className="size-4 mr-1" />
                  Reject
                </Button>
              )}
            </>
          )}
          {inquiry.status === 'rejected' && canReopen && (
            <Button
              variant="outline"
              size="sm"
              disabled={reopenMutation.isPending}
              onClick={() => {
                setReopenReason('');
                setReopenDialogOpen(true);
              }}
            >
              <RotateCcw className="size-4 mr-1" />
              {inquiry.rejected_from === 'pending_purchasing'
                ? 'Reopen to pending purchasing'
                : 'Reopen to pending project sales'}
            </Button>
          )}
          <DetailActionsMenu ariaLabel="Stock inquiry actions">
            <DropdownMenuItem
              onClick={() =>
                router.push(
                  `/procurement-management/stock-inquiries/${inquiryId}/edit`,
                )
              }
            >
              <Edit className="size-4" />
              Edit
            </DropdownMenuItem>
            {inquiry.respond_inbox_url && (
              <DropdownMenuItem onClick={() => setConversationSheetOpen(true)}>
                <MessageSquare className="size-4" />
                Chat records
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              disabled={viewLinkCopying}
              onClick={async () => {
                try {
                  setViewLinkCopying(true);
                  const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                  const { view_url } = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
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
                  const { view_url } = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
                  window.open(view_url, '_blank');
                } catch {
                  toast.error('Failed to open view link');
                }
              }}
            >
              <ExternalLink className="size-4" />
              View in system
            </DropdownMenuItem>
            {inquiry.respond_inbox_url && inquiry.status === 'pending_purchasing' && (
              <DropdownMenuItem
                disabled={updateAndReplyMutation.isPending}
                onClick={async () => {
                  let viewUrl = '';
                  try {
                    const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                    const res = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
                    viewUrl = res.view_url ?? '';
                  } catch {
                    // continue without view link
                  }
                  const purchasingResponse = (inquiry.purchasing_response ?? '').trim();
                  const linkPart = viewUrl ? ` ${viewUrl}` : '';
                  const fullMessage = `There is a response to your stock inquiry${linkPart}: ${purchasingResponse}`;
                  setReplyMessage(fullMessage);
                  setUpdateAndReplyDialogOpen(true);
                }}
              >
                <Send className="size-4" />
                {updateAndReplyMutation.isPending ? 'Sending…' : 'Update & Reply'}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              onClick={handleExportExcel}
              disabled={exporting}
            >
              <FileDown className="size-4" />
              {exporting ? 'Exporting…' : 'Export to Excel'}
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => setDeleteDialogOpen(true)}
            >
              <Trash2 className="size-4" />
              Delete
            </DropdownMenuItem>
          </DetailActionsMenu>
          <RecordNavigation
            basePath="/procurement-management/stock-inquiries"
            prevId={neighbours?.prev_id ?? null}
            nextId={neighbours?.next_id ?? null}
            ariaLabel="stock inquiry"
          />
        </div>
      </div>

      {/* Reject dialog */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reject stock inquiry</DialogTitle>
            <DialogDescription>Optionally provide a reason for the rejection.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reject-reason">Reason (optional)</Label>
            <Textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection..."
              rows={3}
              className="resize-none"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={
                (rejectAction === 'project_sales' && projectSalesRejectMutation.isPending) ||
                (rejectAction === 'purchasing' && purchasingRejectMutation.isPending)
              }
              onClick={async () => {
                if (rejectAction === 'project_sales') {
                  await projectSalesRejectMutation.mutateAsync({ id: inquiryId, reason: rejectReason.trim() || undefined });
                } else if (rejectAction === 'purchasing') {
                  await purchasingRejectMutation.mutateAsync({ id: inquiryId, reason: rejectReason.trim() || undefined });
                }
                setRejectDialogOpen(false);
                setRejectAction(null);
              }}
            >
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reopen dialog */}
      <Dialog open={reopenDialogOpen} onOpenChange={setReopenDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reopen stock inquiry</DialogTitle>
            <DialogDescription>
              {inquiry.rejected_from === 'pending_purchasing'
                ? 'Reopen to pending purchasing. Optionally provide a reason.'
                : 'Reopen to pending project sales. Optionally provide a reason.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reopen-reason">Reason (optional)</Label>
            <Textarea
              id="reopen-reason"
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              placeholder="Reason for reopening..."
              rows={3}
              className="resize-none"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReopenDialogOpen(false)}>Cancel</Button>
            <Button
              disabled={reopenMutation.isPending}
              onClick={async () => {
                await reopenMutation.mutateAsync({ id: inquiryId, reason: reopenReason.trim() || undefined });
                setReopenDialogOpen(false);
              }}
            >
              Reopen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {inquiry && (
        <StockInquiryDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          inquiry={inquiry}
          onSuccess={() => {
            router.push('/procurement-management/stock-inquiries');
          }}
        />
      )}

      <Dialog open={updateAndReplyDialogOpen} onOpenChange={setUpdateAndReplyDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Update & Reply</DialogTitle>
            <DialogDescription>
              Edit the message below. It will be saved as the purchasing response and sent to the customer via Respond.io. The conversation will be marked as responded.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="stock-inquiry-detail-reply-message">Message to send</Label>
              <Textarea
                id="stock-inquiry-detail-reply-message"
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="Purchasing response..."
                rows={5}
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
                try {
                  await updateAndReplyMutation.mutateAsync({
                    id: inquiryId,
                    data: { purchasing_response: replyMessage.trim() },
                  });
                  setUpdateAndReplyDialogOpen(false);
                  setReplyMessage('');
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

      <Dialog open={editPurchasingResponseOpen} onOpenChange={setEditPurchasingResponseOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit purchasing response</DialogTitle>
            <DialogDescription>
              Update the purchasing team response text. This does not send a message to the contact.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="edit-purchasing-response">Purchasing response</Label>
            <Textarea
              id="edit-purchasing-response"
              value={editPurchasingResponseValue}
              onChange={(e) => setEditPurchasingResponseValue(e.target.value)}
              placeholder="Response text..."
              rows={5}
              className="resize-none"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditPurchasingResponseOpen(false)}>Cancel</Button>
            <Button
              disabled={updateInquiryMutation.isPending}
              onClick={async () => {
                try {
                  await updateInquiryMutation.mutateAsync({
                    id: inquiryId,
                    data: { purchasing_response: editPurchasingResponseValue.trim() },
                  });
                  setEditPurchasingResponseOpen(false);
                } catch {
                  // toast from mutation
                }
              }}
            >
              {updateInquiryMutation.isPending ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Stock Inquiry Information */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Inquiry Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Salesperson</p>
                <p className="font-medium">{inquiry.salesperson || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Product Code</p>
                <p className="font-medium">{inquiry.product_code || '-'}</p>
              </div>
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Item Description</p>
                <p className="font-medium">{inquiry.item_description || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{inquiry.quantity ?? '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Delivery Date</p>
                <p className="font-medium">{inquiry.delivery_date ?? '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Remark</p>
                <p className="font-medium whitespace-pre-wrap">{inquiry.remark ?? '-'}</p>
              </div>
            </div>
            {inquiry.additional_remark && (
              <div>
                <p className="text-sm text-muted-foreground">Additional Remark</p>
                <p className="font-medium whitespace-pre-wrap">
                  {inquiry.additional_remark}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Project & Response</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {inquiry.respond_inbox_url && (
              <div>
                <p className="text-sm text-muted-foreground">Respond Inbox</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <a
                    href={inquiry.respond_inbox_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline text-sm break-all font-medium"
                  >
                    {inquiry.respond_inbox_url}
                  </a>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConversationSheetOpen(true)}
                    aria-label="Open chat records"
                  >
                    <MessageSquare className="size-4 mr-1" />
                  </Button>
                </div>
              </div>
            )}
            <div>
              <p className="text-sm text-muted-foreground">Project Customer</p>
              <p className="font-medium">{inquiry.project_customer || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Project Name</p>
              <p className="font-medium">{inquiry.project_name || '-'}</p>
            </div>
            <div>
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm text-muted-foreground">
                  Purchasing Response
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setEditPurchasingResponseValue(inquiry.purchasing_response ?? '');
                    setEditPurchasingResponseOpen(true);
                  }}
                  aria-label="Edit purchasing response"
                >
                  <Edit className="size-4" />
                  Edit
                </Button>
              </div>
              <p className="font-medium whitespace-pre-wrap">
                {inquiry.purchasing_response ?? '-'}
              </p>
            </div>
            {inquiry.rejection_reason != null && inquiry.rejection_reason !== '' && (
              <div>
                <p className="text-sm text-muted-foreground">Rejection reason</p>
                <p className="font-medium whitespace-pre-wrap">{inquiry.rejection_reason}</p>
                {(inquiry.rejected_at || inquiry.rejected_by) && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {inquiry.rejected_at && formatDate(new Date(inquiry.rejected_at))}
                    {(inquiry.rejected_by_name ?? inquiry.rejected_by) && ` by ${inquiry.rejected_by_name ?? inquiry.rejected_by}`}
                  </p>
                )}
              </div>
            )}
            {inquiry.reopen_reason != null && inquiry.reopen_reason !== '' && (
              <div>
                <p className="text-sm text-muted-foreground">Reopen reason</p>
                <p className="font-medium whitespace-pre-wrap">{inquiry.reopen_reason}</p>
                {(inquiry.reopened_at || inquiry.reopened_by) && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {inquiry.reopened_at && formatDate(new Date(inquiry.reopened_at))}
                    {(inquiry.reopened_by_name ?? inquiry.reopened_by) && ` by ${inquiry.reopened_by_name ?? inquiry.reopened_by}`}
                  </p>
                )}
              </div>
            )}
            {inquiry.last_responded_at && (
              <div>
                <p className="text-sm text-muted-foreground">Last responded</p>
                <p className="font-medium">
                  {formatDate(new Date(inquiry.last_responded_at))}
                  {inquiry.last_responded_by_name && ` by ${inquiry.last_responded_by_name}`}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {inquiry.respond_inbox_url && (
        <Sheet open={conversationSheetOpen} onOpenChange={setConversationSheetOpen}>
          <SheetContent side="right" className="flex flex-col w-full sm:max-w-lg overflow-y-auto">
            <SheetHeader className="sr-only">
              <SheetTitle>Chat Records</SheetTitle>
            </SheetHeader>
            <div className="flex-1 min-h-0 pt-2">
              <StockInquiryConversationPanel
                inquiryId={inquiryId}
                canReply={inquiry.status === 'pending_purchasing'}
                respondInboxUrl={inquiry.respond_inbox_url}
                showAsPopup
                purchasingResponse={inquiry.purchasing_response}
                onGetViewLink={async () => {
                  const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                  const res = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
                  return res.view_url ?? '';
                }}
              />
            </div>
          </SheetContent>
        </Sheet>
      )}

      <StockInquiryAttachmentsSection
        inquiryId={inquiryId}
        attachments={inquiry.attachments ?? []}
      />

      <AuditTrail entityType="stock_inquiry" entityId={inquiryId} title="Audit Trail" />
    </div>
  );
}
