'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { exportStockInquiryToExcel } from '../utils/exportStockInquiryToExcel';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useStockInquiry, useStockInquiryNeighbours } from '../hooks/useStockInquiries';
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
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
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
              onClick={handleExportExcel}
              disabled={exporting}
            >
              <FileDown className="size-4" />
              {exporting ? 'Exporting…' : 'Export to Excel'}
            </DropdownMenuItem>
          </DetailActionsMenu>
          <RecordNavigation
            basePath="/procurement-management/stock-inquiries"
            prevId={neighbours?.prev_id ?? null}
            nextId={neighbours?.next_id ?? null}
            ariaLabel="stock inquiry"
          />
          <Button
            variant="outline"
            onClick={() =>
              router.push(
                `/procurement-management/stock-inquiries/${inquiryId}/edit`,
              )
            }
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
