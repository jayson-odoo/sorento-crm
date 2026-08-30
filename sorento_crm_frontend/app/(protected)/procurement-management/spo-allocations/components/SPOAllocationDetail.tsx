'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Edit, Trash2, Link as LinkIcon, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import {
  useSPOAllocation,
  useUpdateSPOAllocation,
} from '../hooks/useSPOAllocations';
import { toast } from 'sonner';
import { formatDate } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
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
          Back to SPO allocations
        </Button>
      </div>
    );
  }

  const statusLabel = formatStatusLabel(spoAllocation.receipt_status) || '-';

  // The gear, left of Edit (D15): the record's secondary action first, Delete
  // last and in red. Edit stays the primary button and is not repeated here.
  const actions: RecordAction[] = [];
  if (
    spoAllocation.receipt_status === 'received' ||
    spoAllocation.receipt_status === 'fully_received'
  ) {
    actions.push({
      key: 'spo_allocation.set_pending',
      label: 'Set to pending',
      icon: RotateCcw,
      disabled: updateMutation.isPending,
      run: handleSetToPending,
    });
  }
  actions.push({
    key: 'spo_allocation.delete',
    label: 'Delete SPO allocation',
    icon: Trash2,
    kind: 'destructive',
    run: () => setDeleteDialogOpen(true),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            {/* An allocation with no SPO number is named by its product, then
                by "Untitled allocation" - never by a slice of its id (S5-05). */}
            <h2 className="text-2xl font-bold">
              {spoAllocation.spo_number?.trim() ||
                spoAllocation.product?.product_name ||
                'Untitled allocation'}
            </h2>
            <Badge status={spoAllocation.receipt_status}>
              {statusLabel}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {spoAllocation.product?.product_name || 'No product'} • Warehouse:{' '}
            {spoAllocation.warehouse?.warehouse_name || '-'}
          </p>
        </div>
        <DetailActions
          actions={actions}
          gearLabel="SPO allocation options"
          primary={
            <Button
              onClick={() =>
                router.push(
                  `/procurement-management/spo-allocations/${spoAllocationId}/edit`,
                )
              }
            >
              <Edit className="size-4" />
              Edit
            </Button>
          }
        />
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
                  status={spoAllocation.receipt_status}
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
