'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Link as LinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { usePackingList, useDeletePackingList } from '../hooks/usePackingLists';
import { formatDate } from '@/lib/helpers';
import PackingListDeleteDialog from './packing-list-delete-dialog';
import Link from 'next/link';
import { Eye, Download } from 'lucide-react';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';

interface PackingListDetailProps {
  packingListId: string;
}

export default function PackingListDetail({
  packingListId,
}: PackingListDetailProps) {
  const router = useRouter();
  const { data: packingList, isLoading } = usePackingList(packingListId);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const downloadMutation = useDownloadAttachment();

  const handleDownload = async (attachmentId: string, filename: string) => {
    try {
      const blob = await downloadMutation.mutateAsync(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!packingList) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Packing list not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/procurement-management/packing-lists')}
          className="mt-4"
        >
          Back to Packing Lists
        </Button>
      </div>
    );
  }

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'in_transit':
        return 'secondary';
      case 'arrived_at_port':
        return 'primary';
      case 'at_warehouse':
        return 'primary';
      case 'partially_received':
        return 'primary';
      case 'fully_received':
        return 'primary';
      case 'closed':
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  const statusLabel = packingList.shipment_status
    ?.split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ') || '-';

  // Total items/cartons from shipment lines when present (source of truth)
  const totalItemsFromLines =
    packingList.shipment_lines?.reduce(
      (sum, line) => sum + (line.quantity_shipped ?? 0),
      0,
    ) ?? 0;
  const totalCartonsFromLines =
    packingList.shipment_lines?.reduce(
      (sum, line) => sum + (line.cartons_count ?? 0),
      0,
    ) ?? 0;
  const displayTotalItems =
    packingList.shipment_lines?.length && totalItemsFromLines > 0
      ? totalItemsFromLines
      : packingList.total_items_shipped ?? 0;
  const displayTotalCartons =
    packingList.shipment_lines?.length && totalCartonsFromLines > 0
      ? totalCartonsFromLines
      : packingList.total_cartons ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">
              {packingList.shipment_number}
            </h1>
            <Badge variant={getStatusBadgeVariant(packingList.shipment_status)}>
              {statusLabel}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {packingList.supplier?.supplier_name || 'No supplier'} • Shipment
            Date:{' '}
            {packingList.shipment_date
              ? formatDate(new Date(packingList.shipment_date))
              : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              router.push(
                `/procurement-management/packing-lists/${packingListId}/edit`,
              )
            }
          >
            <Edit className="size-4" />
            Edit
          </Button>
          <Button
            variant="destructive"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      {packingList && (
        <PackingListDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          packingList={packingList}
          onSuccess={() => {
            router.push('/procurement-management/packing-lists');
          }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Shipment Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Shipment Number</p>
                <p className="font-medium">{packingList.shipment_number}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Supplier</p>
                <p className="font-medium">
                  {packingList.supplier?.supplier_name || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Shipment Date</p>
                <p className="font-medium">
                  {packingList.shipment_date
                    ? formatDate(new Date(packingList.shipment_date))
                    : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Expected Arrival Date
                </p>
                <p className="font-medium">
                  {packingList.expected_arrival_date
                    ? formatDate(new Date(packingList.expected_arrival_date))
                    : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Actual Arrival Date
                </p>
                <p className="font-medium">
                  {packingList.actual_arrival_date
                    ? formatDate(new Date(packingList.actual_arrival_date))
                    : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge
                  variant={getStatusBadgeVariant(packingList.shipment_status)}
                >
                  {statusLabel}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Bill of Lading Number
                </p>
                <p className="font-medium">
                  {packingList.bill_of_lading_number || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Shipping Container Number
                </p>
                <p className="font-medium">
                  {packingList.shipping_container_number || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Invoice Number</p>
                <p className="font-medium">
                  {packingList.invoice_number || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Items</p>
                <p className="font-medium">{displayTotalItems}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Cartons</p>
                <p className="font-medium">{displayTotalCartons}</p>
              </div>
            </div>
            {packingList.notes && (
              <div>
                <p className="text-sm text-muted-foreground">Notes</p>
                <p className="font-medium">{packingList.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Related Documents</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {packingList.attachment_id && packingList.attachment && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Attachment</p>
                <div className="flex items-center gap-2 p-3 border rounded-lg">
                  <div className="flex-1">
                    <p className="text-sm font-medium">
                      {packingList.attachment.original_filename || 'Unknown'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {packingList.attachment.attachment_type?.type_name || 'No type'} •{' '}
                      {packingList.attachment.file_size_bytes
                        ? `${(packingList.attachment.file_size_bytes / 1024).toFixed(2)} KB`
                        : '-'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (packingList.attachment?.file_path) {
                          window.open(packingList.attachment.file_path, '_blank');
                        }
                      }}
                    >
                      <Eye className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (packingList.attachment_id && packingList.attachment?.original_filename) {
                          handleDownload(packingList.attachment_id, packingList.attachment.original_filename);
                        }
                      }}
                    >
                      <Download className="size-4" />
                    </Button>
                  </div>
                </div>
              </div>
            )}
            {packingList.spo_allocations_count !== undefined &&
              packingList.spo_allocations_count > 0 && (
                <div>
                  <Link
                    href={`/procurement-management/spo-allocations?shipment_id=${packingListId}`}
                    className="flex items-center gap-2 text-sm text-primary hover:underline"
                  >
                    <LinkIcon className="size-4" />
                    SPO Allocations ({packingList.spo_allocations_count})
                  </Link>
                </div>
              )}
          </CardContent>
        </Card>
      </div>

      {/* Line Items */}
      {packingList.shipment_lines &&
        packingList.shipment_lines.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Shipment Lines</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Product</TableHead>
                      <TableHead>Quantity Shipped</TableHead>
                      <TableHead>Cartons</TableHead>
                      <TableHead>Batch Number</TableHead>
                      <TableHead>Unit Cost</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {packingList.shipment_lines.map((line) => (
                      <TableRow key={line.id}>
                        <TableCell>
                          {line.product?.product_code || '-'}
                        </TableCell>
                        <TableCell>{line.quantity_shipped}</TableCell>
                        <TableCell>{line.cartons_count}</TableCell>
                        <TableCell>{line.batch_number || '-'}</TableCell>
                        <TableCell>
                          {line.unit_cost
                            ? new Intl.NumberFormat('en-US', {
                                style: 'currency',
                                currency: 'MYR',
                              }).format(line.unit_cost)
                            : '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}
    </div>
  );
}
