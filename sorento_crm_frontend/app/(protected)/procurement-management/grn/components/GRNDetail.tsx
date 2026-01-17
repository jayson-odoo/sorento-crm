'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
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
import { useGRN } from '../hooks/useGRN';
import { formatDate } from '@/lib/helpers';
import GRNDeleteDialog from './grn-delete-dialog';

interface GRNDetailProps {
  grnId: string;
}

export default function GRNDetail({ grnId }: GRNDetailProps) {
  const router = useRouter();
  const { data: grn, isLoading } = useGRN(grnId);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!grn) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">GRN not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/procurement-management/grn')}
          className="mt-4"
        >
          Back to GRN
        </Button>
      </div>
    );
  }

  const getPickingStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'draft':
        return 'secondary';
      case 'submitted':
        return 'primary';
      case 'approved':
        return 'primary';
      case 'posted':
        return 'primary';
      case 'rejected':
        return 'destructive';
      case 'closed':
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  const getInspectionStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'pending':
        return 'secondary';
      case 'passed':
        return 'primary';
      case 'failed':
        return 'destructive';
      case 'partial_pass':
        return 'primary';
      default:
        return 'secondary';
    }
  };

  const pickingStatusLabel = grn.picking_status
    ?.split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ') || '-';

  const inspectionStatusLabel = grn.inspection_status
    ?.split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ') || '-';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{grn.picking_number}</h1>
            <Badge variant={getPickingStatusBadgeVariant(grn.picking_status)}>
              {pickingStatusLabel}
            </Badge>
            <Badge
              variant={getInspectionStatusBadgeVariant(grn.inspection_status)}
            >
              {inspectionStatusLabel}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Picking Date:{' '}
            {grn.picking_date ? formatDate(new Date(grn.picking_date)) : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              router.push(`/procurement-management/grn/${grnId}/edit`)
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

      {grn && (
        <GRNDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          grn={grn}
          onSuccess={() => {
            router.push('/procurement-management/grn');
          }}
        />
      )}

      <Card>
        <CardHeader>
          <CardTitle>GRN Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">GRN Number</p>
              <p className="font-medium">{grn.picking_number}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Picking Date</p>
              <p className="font-medium">
                {grn.picking_date
                  ? formatDate(new Date(grn.picking_date))
                  : '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Picking Status</p>
              <Badge
                variant={getPickingStatusBadgeVariant(grn.picking_status)}
              >
                {pickingStatusLabel}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                Inspection Status
              </p>
              <Badge
                variant={getInspectionStatusBadgeVariant(
                  grn.inspection_status,
                )}
              >
                {inspectionStatusLabel}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                Total Items Picked
              </p>
              <p className="font-medium">{grn.total_items_picked || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                Total Items Discrepancy
              </p>
              <p className="font-medium">
                {grn.total_items_discrepancy || 0}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Cost</p>
              <p className="font-medium">
                {grn.total_cost
                  ? new Intl.NumberFormat('en-US', {
                      style: 'currency',
                      currency: 'USD',
                    }).format(grn.total_cost)
                  : '-'}
              </p>
            </div>
            {grn.inspection_date && (
              <div>
                <p className="text-sm text-muted-foreground">
                  Inspection Date
                </p>
                <p className="font-medium">
                  {formatDate(new Date(grn.inspection_date))}
                </p>
              </div>
            )}
          </div>
          {grn.quality_remarks && (
            <div>
              <p className="text-sm text-muted-foreground">Quality Remarks</p>
              <p className="font-medium">{grn.quality_remarks}</p>
            </div>
          )}
          {grn.notes && (
            <div>
              <p className="text-sm text-muted-foreground">Notes</p>
              <p className="font-medium">{grn.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Picking Lines */}
      {grn.picking_lines && grn.picking_lines.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Picking Lines</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SPO Allocation</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Expected</TableHead>
                    <TableHead>Picked</TableHead>
                    <TableHead>Discrepancy</TableHead>
                    <TableHead>Condition</TableHead>
                    <TableHead>Unit Cost</TableHead>
                    <TableHead>Line Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {grn.picking_lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>
                        {line.spo_allocation?.spo_number || '-'}
                      </TableCell>
                      <TableCell>
                        {line.product?.product_code || '-'} -{' '}
                        {line.product?.product_name || '-'}
                      </TableCell>
                      <TableCell>{line.quantity_expected}</TableCell>
                      <TableCell>{line.quantity_picked}</TableCell>
                      <TableCell>{line.quantity_discrepancy}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {line.picked_condition
                            ?.split('_')
                            .map(
                              (word) =>
                                word.charAt(0).toUpperCase() + word.slice(1),
                            )
                            .join(' ') || '-'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {line.unit_cost
                          ? new Intl.NumberFormat('en-US', {
                              style: 'currency',
                              currency: 'USD',
                            }).format(line.unit_cost)
                          : '-'}
                      </TableCell>
                      <TableCell>
                        {line.line_total
                          ? new Intl.NumberFormat('en-US', {
                              style: 'currency',
                              currency: 'USD',
                            }).format(line.line_total)
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
