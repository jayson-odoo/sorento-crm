'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Edit, Trash2, Settings, Check, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useGRN, useUpdateGRN } from '../hooks/useGRN';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant, formatStatusLabel } from '@/lib/status-badge';
import GRNDeleteDialog from './grn-delete-dialog';
import GRNNavigation from './GRNNavigation';

interface GRNDetailProps {
  grnId: string;
}

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
] as const;

export default function GRNDetail({ grnId }: GRNDetailProps) {
  const router = useRouter();
  const { data: grn, isLoading } = useGRN(grnId);
  const updateMutation = useUpdateGRN();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [lineSearch, setLineSearch] = useState('');
  const allLines = grn?.picking_lines ?? [];
  const filteredLines = useMemo(() => {
    const q = lineSearch.trim().toLowerCase();
    if (!q) return allLines;
    return allLines.filter((line) => {
      const haystack = [
        line.product?.product_code,
        line.product?.product_name,
        line.source_warehouse?.warehouse_code,
        line.source_warehouse?.warehouse_name,
        line.destination_warehouse?.warehouse_code,
        line.destination_warehouse?.warehouse_name,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [allLines, lineSearch]);
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

  const pickingStatusLabel = grn.picking_status
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
            <Badge variant={getStatusBadgeVariant(grn.picking_status)}>
              {formatStatusLabel(grn.picking_status) || pickingStatusLabel}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Picking Date:{' '}
            {grn.picking_date ? formatDate(new Date(grn.picking_date)) : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <GRNNavigation grnId={grnId} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" title="Change status">
                <Settings className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {STATUS_OPTIONS.map((opt) => (
                <DropdownMenuItem
                  key={opt.value}
                  onClick={async () => {
                    try {
                      await updateMutation.mutateAsync({
                        id: grnId,
                        data: { picking_status: opt.value },
                      });
                    } catch {
                      // toast handled by mutation
                    }
                  }}
                  disabled={updateMutation.isPending || grn.picking_status === opt.value}
                >
                  <span className="inline-flex w-5 shrink-0">
                    {grn.picking_status === opt.value ? (
                      <Check className="size-4" />
                    ) : null}
                  </span>
                  {opt.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
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
              <p className="text-sm text-muted-foreground">SPO Number</p>
              <p className="font-medium">{grn.spo_number ?? '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Supplier</p>
              <p className="font-medium">
                {grn.supplier
                  ? `${grn.supplier.supplier_name} (${grn.supplier.supplier_code})`
                  : grn.supplier_code ?? '-'}
              </p>
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
                variant={getStatusBadgeVariant(grn.picking_status)}
              >
                {pickingStatusLabel}
              </Badge>
            </div>
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
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <CardTitle>Picking Lines</CardTitle>
          <div className="flex items-center gap-3">
            {allLines.length > 0 && (
              <div className="relative">
                <Search className="size-4 absolute start-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={lineSearch}
                  onChange={(e) => setLineSearch(e.target.value)}
                  placeholder="Search product or warehouse"
                  className="ps-8 pe-8 w-64 h-8"
                />
                {lineSearch && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-6 absolute end-1 top-1/2 -translate-y-1/2"
                    onClick={() => setLineSearch('')}
                    aria-label="Clear search"
                  >
                    <X className="size-3.5" />
                  </Button>
                )}
              </div>
            )}
            <span className="text-sm text-muted-foreground whitespace-nowrap">
              {lineSearch.trim()
                ? `${filteredLines.length} of ${allLines.length} lines`
                : `${allLines.length} ${allLines.length === 1 ? 'line' : 'lines'}`}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          {allLines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No picking lines on this GRN yet. Import lines or edit the GRN to add them.
            </p>
          ) : filteredLines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No lines match &quot;{lineSearch}&quot;.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SPO Allocation</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Expected</TableHead>
                    <TableHead>Picked</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredLines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>
                        {line.spo_allocation ? (
                          <Link
                            href={`/procurement-management/spo-allocations/${line.spo_allocation.id}`}
                            className="text-primary hover:underline font-medium"
                          >
                            {line.spo_allocation.spo_number ?? line.spo_allocation.id}
                          </Link>
                        ) : (
                          '-'
                        )}
                      </TableCell>
                      <TableCell>
                        {line.product?.product_code || '-'}
                      </TableCell>
                      <TableCell>
                        {line.source_warehouse?.warehouse_code ?? line.destination_warehouse?.warehouse_code ?? '-'}
                      </TableCell>
                      <TableCell>{line.quantity_expected}</TableCell>
                      <TableCell>{line.quantity_picked}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
