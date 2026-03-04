'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Edit, Trash2, Link as LinkIcon, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useSPOAllocation,
  useDeleteSPOAllocation,
  useUpdateSPOAllocation,
} from '../hooks/useSPOAllocations';
import { toast } from 'sonner';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant, formatStatusLabel } from '@/lib/status-badge';
import SPOAllocationDeleteDialog from './spo-allocation-delete-dialog';
import Link from 'next/link';

interface SPOAllocationDetailProps {
  spoAllocationId: string;
}

export default function SPOAllocationDetail({
  spoAllocationId,
}: SPOAllocationDetailProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: spoAllocation, isLoading } = useSPOAllocation(spoAllocationId);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const updateMutation = useUpdateSPOAllocation();

  const handleSetToPending = () => {
    updateMutation.mutate(
      { id: spoAllocationId, data: { receipt_status: 'pending' } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['spo-allocation', spoAllocationId] });
          toast.success('Status set to Pending');
        },
        onError: (err) => toast.error(err.message || 'Failed to update status'),
      }
    );
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!spoAllocation) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">SPO allocation not found</p>
        <Button
          variant="outline"
          onClick={() =>
            router.push('/procurement-management/spo-allocations')
          }
          className="mt-4"
        >
          Back to SPO Allocations
        </Button>
      </div>
    );
  }

  const statusLabel = formatStatusLabel(spoAllocation.receipt_status) || '-';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">
              {spoAllocation.spo_number || `SPO-${spoAllocation.id.slice(0, 8)}`}
            </h1>
            <Badge variant={getStatusBadgeVariant(spoAllocation.receipt_status)}>
              {statusLabel}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {spoAllocation.product?.product_name || 'No product'} • Warehouse:{' '}
            {spoAllocation.warehouse?.warehouse_name || '-'}
          </p>
        </div>
        <div className="flex gap-2">
          {(spoAllocation.receipt_status === 'received' ||
            spoAllocation.receipt_status === 'fully_received') && (
            <Button
              variant="outline"
              onClick={handleSetToPending}
              disabled={updateMutation.isPending}
            >
              <RotateCcw className="size-4" />
              Set to Pending
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() =>
              router.push(
                `/procurement-management/spo-allocations/${spoAllocationId}/edit`,
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

      {spoAllocation && (
        <SPOAllocationDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          spoAllocation={spoAllocation}
          onSuccess={() => {
            router.push('/procurement-management/spo-allocations');
          }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Allocation Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">SPO Number</p>
                <p className="font-medium">
                  {spoAllocation.spo_number || '-'}
                </p>
              </div>
              {spoAllocation.spo_line_number != null && (
                <div>
                  <p className="text-sm text-muted-foreground">SPO Line Number (legacy)</p>
                  <p className="font-medium">{spoAllocation.spo_line_number}</p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Product</p>
                <p className="font-medium">
                  {spoAllocation.product?.product_code || '-'} -{' '}
                  {spoAllocation.product?.product_name || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Warehouse</p>
                <p className="font-medium">
                  {spoAllocation.warehouse?.warehouse_name || '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">
                  Allocated Quantity
                </p>
                <p className="font-medium">
                  {spoAllocation.allocated_quantity}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity Received</p>
                <p className="font-medium">
                  {spoAllocation.quantity_received}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity Rejected</p>
                <p className="font-medium">
                  {spoAllocation.quantity_rejected}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge
                  variant={getStatusBadgeVariant(spoAllocation.receipt_status)}
                >
                  {statusLabel}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Created At</p>
                <p className="font-medium">
                  {formatDate(new Date(spoAllocation.created_at))}
                </p>
              </div>
            </div>
            {spoAllocation.allocation_notes && (
              <div>
                <p className="text-sm text-muted-foreground">Allocation Notes</p>
                <p className="font-medium">{spoAllocation.allocation_notes}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Related Documents</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {spoAllocation.inbound_shipment && (
              <div>
                <Link
                  href={`/procurement-management/packing-lists/${spoAllocation.inbound_shipment.id}`}
                  className="flex items-center gap-2 text-sm text-primary hover:underline"
                >
                  <LinkIcon className="size-4" />
                  Packing List: {spoAllocation.inbound_shipment.shipment_number}
                </Link>
              </div>
            )}
            {spoAllocation.linked_grns && spoAllocation.linked_grns.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Linked GRNs</p>
                <ul className="list-none space-y-1">
                  {spoAllocation.linked_grns.map((grn) => (
                    <li key={grn.id}>
                      <Link
                        href={`/procurement-management/grn/${grn.id}`}
                        className="flex items-center gap-2 text-sm text-primary hover:underline"
                      >
                        <LinkIcon className="size-4 shrink-0" />
                        {grn.picking_number || grn.id}
                        {grn.picking_status && (
                          <Badge variant="secondary" className="text-xs">
                            {grn.picking_status}
                          </Badge>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {spoAllocation.grn_lines_count !== undefined &&
              spoAllocation.grn_lines_count > 0 &&
              (!spoAllocation.linked_grns || spoAllocation.linked_grns.length === 0) && (
                <div>
                  <Link
                    href={`/procurement-management/grn?spo_allocation_id=${spoAllocationId}`}
                    className="flex items-center gap-2 text-sm text-primary hover:underline"
                  >
                    <LinkIcon className="size-4" />
                    GRN Records ({spoAllocation.grn_lines_count})
                  </Link>
                </div>
              )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
