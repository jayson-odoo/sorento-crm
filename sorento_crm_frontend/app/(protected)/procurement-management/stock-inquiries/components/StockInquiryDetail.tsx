'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, FileDown, Send, Link2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import { useStockInquiry, useStockInquiryNeighbours, useUpdateStockInquiryAndReply } from '../hooks/useStockInquiries';
import { getOrCreateStockInquiryViewLink } from '../services/stockInquiryService';
import { toast } from 'sonner';
import { formatDate } from '@/lib/helpers';
import StockInquiryDeleteDialog from './stock-inquiry-delete-dialog';
import AuditTrail from '@/components/audit/AuditTrail';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';

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
  const updateAndReplyMutation = useUpdateStockInquiryAndReply();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [updateAndReplyDialogOpen, setUpdateAndReplyDialogOpen] = useState(false);
  const [replyMessage, setReplyMessage] = useState('');
  const [viewLinkCopying, setViewLinkCopying] = useState(false);
  const [exporting, setExporting] = useState(false);

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
                <span className="capitalize font-medium">{inquiry.status}</span>
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
        <div className="flex items-center gap-2">
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
            {inquiry.respond_inbox_url && (
              <DropdownMenuItem
                disabled={updateAndReplyMutation.isPending}
                onClick={async () => {
                  let defaultMsg = inquiry.purchasing_response ?? '';
                  try {
                    const baseUrl = typeof window !== 'undefined' ? window.location.origin : undefined;
                    const { view_url } = await getOrCreateStockInquiryViewLink(inquiryId, baseUrl);
                    if (view_url) {
                      defaultMsg = defaultMsg.trim()
                        ? `${defaultMsg.trim()}\n\nView full details: ${view_url}`
                        : `View full details: ${view_url}`;
                    }
                  } catch {
                    // keep default without view link
                  }
                  setReplyMessage(defaultMsg);
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
                <a
                  href={inquiry.respond_inbox_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline text-sm break-all font-medium"
                >
                  {inquiry.respond_inbox_url}
                </a>
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
              <p className="text-sm text-muted-foreground">
                Purchasing Response
              </p>
              <p className="font-medium whitespace-pre-wrap">
                {inquiry.purchasing_response ?? '-'}
              </p>
            </div>
            {inquiry.status && (
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <p className="font-medium capitalize">{inquiry.status}</p>
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

      <AuditTrail entityType="stock_inquiry" entityId={inquiryId} title="Audit Trail" />
    </div>
  );
}
