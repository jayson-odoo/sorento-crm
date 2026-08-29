'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { useGRN, grnPagerQuery } from '../hooks/useGRN';
import { formatDate } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { SpoAllocationCell } from '@/components/common/SpoAllocationCell';
import DetailActions from '@/components/common/DetailActions';
import { useGrnActions } from '../actions';

interface GRNDetailProps {
  grnId: string;
}

/** How the GRN reached the system, in words a user recognises. */
const GRN_SOURCE_LABELS: Record<string, string> = {
  ui: 'created in the system',
  import: 'Excel import',
  external_api: 'AutoCount / n8n integration',
};

export default function GRNDetail({ grnId }: GRNDetailProps) {
  const router = useRouter();
  const { data: grn, isLoading } = useGRN(grnId);
  const { actions, dialogs } = useGrnActions(grn, {
    onDeleted: () => router.push('/procurement-management/grn'),
  });
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
      {/* Header. Stacks on mobile: a long GRN number beside non-wrapping actions
          overlaps the title and forces page-wide horizontal overflow. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold break-words">{grn.picking_number}</h1>
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(grn.picking_status)}`}
            >
              {formatStatusLabel(grn.picking_status) || pickingStatusLabel}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            Picking Date:{' '}
            {grn.picking_date ? formatDate(new Date(grn.picking_date)) : '-'}
          </p>
        </div>
        <DetailActions
          pager={{
            ...grnPagerQuery,
            detailPath: '/procurement-management/grn',
            currentId: grnId,
            ariaLabel: 'GRN',
          }}
          actions={actions}
          dialogs={dialogs}
          gearLabel="GRN options"
          primary={
            <Button
              onClick={() => router.push(`/procurement-management/grn/${grnId}/edit`)}
            >
              <Edit className="size-4" />
              Edit
            </Button>
          }
        />
      </div>

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
              <p className="text-sm text-muted-foreground">Picking Date</p>
              <p className="font-medium">
                {grn.picking_date
                  ? formatDate(new Date(grn.picking_date))
                  : '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Picking Status</p>
              <span
                className={`${STATUS_PILL_BASE} ${statusPillClass(grn.picking_status)}`}
              >
                {pickingStatusLabel}
              </span>
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
          {/* Provenance. Always rendered, including the unknown case: the question
              "who created this GRN, and into which company" had no answer on the
              page at all, which is what made a mis-companied upload untraceable.
              An explicit "Unknown" is the honest answer for rows that predate the
              recording - better than an absent section that reads as "no data". */}
          <div className="border-t pt-4">
            <p className="text-sm text-muted-foreground">Created by</p>
            <p className="font-medium">
              {grn.created_by_label ?? 'Unknown'}
              {grn.source_system && (
                <span className="text-muted-foreground font-normal">
                  {' '}
                  ({GRN_SOURCE_LABELS[grn.source_system] ?? grn.source_system})
                </span>
              )}
            </p>
            {grn.import_filename && (
              <p className="text-sm text-muted-foreground mt-1">
                Imported from <span className="font-medium">{grn.import_filename}</span>
              </p>
            )}
          </div>
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
                        <SpoAllocationCell
                          allocation={line.spo_allocation}
                          statedSpoNumber={line.spo_number_raw}
                        />
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
