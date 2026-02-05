'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useComplaint } from '../hooks/useComplaints';
import { formatDate } from '@/lib/helpers';
import ComplaintDeleteDialog from './complaint-delete-dialog';
import ComplaintNavigation from './ComplaintNavigation';
import ComplaintManualAttachmentsSection from './ComplaintManualAttachmentsSection';

interface ComplaintDetailProps {
  complaintId: string;
}

export default function ComplaintDetail({ complaintId }: ComplaintDetailProps) {
  const router = useRouter();
  
  // Don't fetch if it's "new" or invalid
  const isValidId = complaintId && complaintId !== 'new' && complaintId !== 'edit';
  const { data: complaint, isLoading } = useComplaint(isValidId ? complaintId : null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  
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
          </p>
        </div>
        <div className="flex gap-2">
          <ComplaintNavigation complaintId={complaintId} />
          <Button
            variant="outline"
            onClick={() =>
              router.push(`/complaint-management/complaints/${complaintId}/edit`)
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
        </CardContent>
      </Card>

      <ComplaintManualAttachmentsSection
          complaintId={complaintId}
          attachments={complaint.attachments ?? []}
        />
    </div>
  );
}
