'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { usePurchaseRequest } from '../hooks/usePurchaseRequests';
import { formatDate } from '@/lib/helpers';
import PurchaseRequestDeleteDialog from './purchase-request-delete-dialog';

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
  const { data: request, isLoading } = usePurchaseRequest(
    isValidId ? requestId : null,
  );
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

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
        <div className="flex gap-2">
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
              <div>
                <p className="text-sm text-muted-foreground">Purpose</p>
                <p className="font-medium">{request.purpose || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Expected Delivery</p>
                <p className="font-medium">
                  {request.expected_delivery_date
                    ? formatDate(new Date(request.expected_delivery_date))
                    : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Expected PO Date</p>
                <p className="font-medium">
                  {request.expected_po_date_text ??
                    (request.expected_po_date
                      ? formatDate(new Date(request.expected_po_date))
                      : '-')}
                </p>
              </div>
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
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Line Items</CardTitle>
          </CardHeader>
          <CardContent>
            {request.lines && request.lines.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Item Code</TableHead>
                    <TableHead>Quantity</TableHead>
                    <TableHead>Remark</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {request.lines.map((line, idx) => (
                    <TableRow key={line.id}>
                      <TableCell>{idx + 1}</TableCell>
                      <TableCell>{line.item_code ?? '-'}</TableCell>
                      <TableCell>{line.quantity ?? '-'}</TableCell>
                      <TableCell>{line.remark ?? '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">No line items.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
