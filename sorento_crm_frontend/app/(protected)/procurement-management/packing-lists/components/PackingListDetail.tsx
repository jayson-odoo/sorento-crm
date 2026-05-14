'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, Link as LinkIcon, Search, X, ArrowUpDown, ArrowUp, ArrowDown, Link2, Unlink, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { usePackingList, useDeletePackingList, useUpdatePackingList } from '../hooks/usePackingLists';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant, formatStatusLabel } from '@/lib/status-badge';
import PackingListDeleteDialog from './packing-list-delete-dialog';
import PackingListNavigation from './PackingListNavigation';
import Link from 'next/link';
import { Eye, Download } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { toast } from 'sonner';
import ComplaintLinkAttachmentBrowserDialog from '@/app/(protected)/complaint-management/complaints/components/ComplaintLinkAttachmentBrowserDialog';

interface PackingListDetailProps {
  packingListId: string;
}

export default function PackingListDetail({
  packingListId,
}: PackingListDetailProps) {
  const router = useRouter();
  const { data: packingList, isLoading } = usePackingList(packingListId);
  const updatePackingListMutation = useUpdatePackingList();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [linkAttachmentDialogOpen, setLinkAttachmentDialogOpen] = useState(false);
  const [shipmentLinesSearch, setShipmentLinesSearch] = useState('');
  const [sortField, setSortField] = useState<'product' | 'quantity_shipped' | 'spo_allocated' | 'quantity_received' | 'status'>('product');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const downloadMutation = useDownloadAttachment();

  const linkPackingListAttachment = async (_entityId: string, attachmentId: string) => {
    await updatePackingListMutation.mutateAsync({
      id: packingListId,
      data: { attachment_id: attachmentId },
    });
  };

  const handleUnlinkAttachment = async () => {
    try {
      await updatePackingListMutation.mutateAsync({
        id: packingListId,
        data: { attachment_id: null },
      });
      toast.success('Attachment unlinked');
    } catch {
      toast.error('Failed to unlink attachment');
    }
  };

  const linkedAttachmentIds = useMemo(
    () => (packingList?.attachment_id ? new Set([packingList.attachment_id]) : new Set<string>()),
    [packingList?.attachment_id]
  );

  /** Line-level status from quantity shipped, allocated, and received. */
  const getLineStatus = (
    quantityShipped: number,
    allocated: number,
    received: number
  ): string => {
    const qty = quantityShipped ?? 0;
    const alloc = allocated ?? 0;
    const recv = received ?? 0;
    if (alloc === 0) return 'in_transit';
    // Received: full or over-received (recv >= alloc)
    if (recv >= alloc) return 'received';
    if (qty > alloc) return 'partially_allocated';
    // Allocated: allocated qty >= shipped and nothing received yet
    if (alloc >= qty && recv === 0) return 'allocated';
    if (alloc >= qty && recv > 0) return 'partially_received';
    return 'in_transit';
  };

  // Sort and filter shipment lines - must be called before early returns (Rules of Hooks)
  const sortedAndFilteredLines = useMemo(() => {
    if (!packingList?.shipment_lines) return [];
    
    let filtered = packingList.shipment_lines.filter((line) => {
      if (!shipmentLinesSearch.trim()) return true;
      const q = shipmentLinesSearch.trim().toLowerCase();
      const code = line.product?.product_code?.toLowerCase() ?? '';
      const name = line.product?.product_name?.toLowerCase() ?? '';
      return code.includes(q) || name.includes(q);
    });

    // Sort
    filtered = [...filtered].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortField) {
        case 'product':
          aVal = a.product?.product_code?.toLowerCase() ?? '';
          bVal = b.product?.product_code?.toLowerCase() ?? '';
          break;
        case 'quantity_shipped':
          aVal = a.quantity_shipped ?? 0;
          bVal = b.quantity_shipped ?? 0;
          break;
        case 'spo_allocated':
          aVal = a.spo_allocated_quantity ?? 0;
          bVal = b.spo_allocated_quantity ?? 0;
          break;
        case 'quantity_received':
          aVal = a.quantity_received ?? 0;
          bVal = b.quantity_received ?? 0;
          break;
        case 'status':
          aVal =
            a.line_status ??
            getLineStatus(a.quantity_shipped ?? 0, a.spo_allocated_quantity ?? 0, a.quantity_received ?? 0);
          bVal =
            b.line_status ??
            getLineStatus(b.quantity_shipped ?? 0, b.spo_allocated_quantity ?? 0, b.quantity_received ?? 0);
          break;
        default:
          return 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      } else {
        return sortDirection === 'asc'
          ? (aVal as number) - (bVal as number)
          : (bVal as number) - (aVal as number);
      }
    });

    return filtered;
  }, [packingList?.shipment_lines, shipmentLinesSearch, sortField, sortDirection]);

  const handleSort = (field: 'product' | 'quantity_shipped' | 'spo_allocated' | 'quantity_received' | 'status') => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const SortIcon = ({ field }: { field: 'product' | 'quantity_shipped' | 'spo_allocated' | 'quantity_received' | 'status' }) => {
    if (sortField !== field) {
      return <ArrowUpDown className="size-4 ml-1 text-muted-foreground" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="size-4 ml-1" />
    ) : (
      <ArrowDown className="size-4 ml-1" />
    );
  };

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

  const handlePreview = async (attachmentId: string) => {
    try {
      const previewUrl = await getAttachmentPreviewUrl(attachmentId);
      if (previewUrl) {
        window.open(previewUrl, '_blank');
      }
    } catch {
      toast.error('Failed to open attachment preview');
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
          <h1 className="text-2xl font-bold">
            {packingList.shipping_container_number || packingList.shipment_number || `Packing list ${packingList.id.slice(0, 8)}`}
          </h1>
          <p className="text-sm text-muted-foreground">
            {packingList.supplier?.supplier_name || 'No supplier'} • Shipment
            Date:{' '}
            {packingList.shipment_date
              ? formatDate(new Date(packingList.shipment_date))
              : '-'}
          </p>
        </div>
        <div className="flex gap-2">
          <PackingListNavigation packingListId={packingListId} />
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
                <p className="font-medium">{packingList.shipment_number || '-'}</p>
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
                  Estimated Arrival Date
                </p>
                <p className="font-medium">
                  {packingList.estimated_arrival_date
                    ? formatDate(new Date(packingList.estimated_arrival_date))
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
            {packingList.attachment_id && packingList.attachment ? (
              <div className="space-y-2">
                <p className="text-sm font-medium">Attachment</p>
                <div className="flex items-center gap-2 p-3 border rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {packingList.attachment.original_filename || 'Unknown'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {packingList.attachment.attachment_type?.type_name || 'No type'} •{' '}
                      {packingList.attachment.file_size_bytes
                        ? `${(packingList.attachment.file_size_bytes / 1024).toFixed(2)} KB`
                        : '-'}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (packingList.attachment_id) {
                          handlePreview(packingList.attachment_id);
                        }
                      }}
                      title="Preview"
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
                      title="Download"
                    >
                      <Download className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleUnlinkAttachment}
                      disabled={updatePackingListMutation.isPending}
                      title="Unlink attachment"
                    >
                      <Unlink className="size-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">No attachment linked. Link one to attach a document to this packing list.</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setLinkAttachmentDialogOpen(true)}
                  className="gap-2"
                >
                  <Link2 className="size-4" />
                  Link attachment
                </Button>
              </div>
            )}
            <ComplaintLinkAttachmentBrowserDialog
              open={linkAttachmentDialogOpen}
              onOpenChange={setLinkAttachmentDialogOpen}
              entityId={packingListId}
              linkedAttachmentIds={linkedAttachmentIds}
              linkAttachment={linkPackingListAttachment}
              invalidateQueryKeys={[['packing-list', packingListId], ['packing-lists']]}
              successEntityLabel="packing list"
              maxSelections={1}
            />
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
            <CardHeader className="flex-row items-center justify-between gap-3">
              <CardTitle>Shipment Lines</CardTitle>
              <div className="relative flex items-center gap-2">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <Input
                  placeholder="Search by product code"
                  value={shipmentLinesSearch}
                  onChange={(e) => setShipmentLinesSearch(e.target.value)}
                  className="ps-9 w-56"
                />
                {shipmentLinesSearch && (
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8"
                    onClick={() => setShipmentLinesSearch('')}
                  >
                    <X className="size-4" />
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                    <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>
                        <button
                          onClick={() => handleSort('product')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          Product
                          <SortIcon field="product" />
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          onClick={() => handleSort('quantity_shipped')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          Quantity Shipped
                          <SortIcon field="quantity_shipped" />
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          onClick={() => handleSort('spo_allocated')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          SPO Allocated
                          <SortIcon field="spo_allocated" />
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          onClick={() => handleSort('quantity_received')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          Received Quantity
                          <SortIcon field="quantity_received" />
                        </button>
                      </TableHead>
                      <TableHead>
                        <button
                          onClick={() => handleSort('status')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          Status
                          <SortIcon field="status" />
                        </button>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedAndFilteredLines.map((line) => {
                      const lineStatus =
                        line.line_status ??
                        getLineStatus(
                          line.quantity_shipped ?? 0,
                          line.spo_allocated_quantity ?? 0,
                          line.quantity_received ?? 0
                        );
                      return (
                        <TableRow key={line.id}>
                          <TableCell>
                            {line.product?.id ? (
                              <Link
                                href={`/master-data-management/products/${line.product.id}`}
                                className="font-medium text-primary hover:underline"
                              >
                                {line.product.product_code}
                              </Link>
                            ) : (
                              line.product?.product_code || '-'
                            )}
                          </TableCell>
                          <TableCell>{line.quantity_shipped}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>
                                {line.spo_allocated_quantity != null ? line.spo_allocated_quantity : '-'}
                              </span>
                              {line.related_spo_allocations?.length ? (
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-6 text-muted-foreground hover:text-foreground"
                                      aria-label={`View related SPO for ${line.product?.product_code || 'this line'}`}
                                    >
                                      <Info className="size-4" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent align="start" className="w-80 space-y-4 p-4">
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">
                                        {line.product?.product_code || 'Related SPO'}
                                      </p>
                                      <p className="text-xs text-muted-foreground">
                                        Navigate to related SPO allocations for this line.
                                      </p>
                                    </div>

                                    <div className="space-y-2">
                                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                        Related SPO
                                      </p>
                                      <div className="space-y-2">
                                        {line.related_spo_allocations.map((spo) => (
                                          <Link
                                            key={spo.id}
                                            href={`/procurement-management/spo-allocations/${spo.id}`}
                                            className="block rounded-md border px-3 py-2 hover:bg-muted/50"
                                          >
                                            <div className="flex items-center justify-between gap-2">
                                              <span className="text-sm font-medium text-primary">
                                                {spo.spo_number || 'SPO Allocation'}
                                              </span>
                                              {spo.receipt_status ? (
                                                <Badge
                                                  variant={getStatusBadgeVariant(spo.receipt_status)}
                                                  className="shrink-0"
                                                >
                                                  {formatStatusLabel(spo.receipt_status)}
                                                </Badge>
                                              ) : null}
                                            </div>
                                            {spo.allocated_quantity != null ? (
                                              <p className="mt-1 text-xs text-muted-foreground">
                                                Allocated: {spo.allocated_quantity}
                                              </p>
                                            ) : null}
                                          </Link>
                                        ))}
                                      </div>
                                    </div>
                                  </PopoverContent>
                                </Popover>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>
                                {line.quantity_received != null ? line.quantity_received : '-'}
                              </span>
                              {line.related_grns?.length ? (
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-6 text-muted-foreground hover:text-foreground"
                                      aria-label={`View related GRN for ${line.product?.product_code || 'this line'}`}
                                    >
                                      <Info className="size-4" />
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent align="start" className="w-80 space-y-4 p-4">
                                    <div className="space-y-1">
                                      <p className="text-sm font-medium">
                                        {line.product?.product_code || 'Related GRN'}
                                      </p>
                                      <p className="text-xs text-muted-foreground">
                                        Navigate to related GRNs for this line.
                                      </p>
                                    </div>

                                    <div className="space-y-2">
                                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                        Related GRN
                                      </p>
                                      <div className="space-y-2">
                                        {line.related_grns.map((grn) => (
                                          <Link
                                            key={grn.id}
                                            href={`/procurement-management/grn/${grn.id}`}
                                            className="block rounded-md border px-3 py-2 hover:bg-muted/50"
                                          >
                                            <div className="flex items-center justify-between gap-2">
                                              <span className="text-sm font-medium text-primary">
                                                {grn.picking_number || 'GRN'}
                                              </span>
                                              {grn.picking_status ? (
                                                <Badge
                                                  variant={getStatusBadgeVariant(grn.picking_status)}
                                                  className="shrink-0"
                                                >
                                                  {formatStatusLabel(grn.picking_status)}
                                                </Badge>
                                              ) : null}
                                            </div>
                                            <p className="mt-1 text-xs text-muted-foreground">
                                              {grn.spo_number || 'No SPO'}
                                              {grn.picking_date
                                                ? ` • ${formatDate(new Date(grn.picking_date))}`
                                                : ''}
                                            </p>
                                          </Link>
                                        ))}
                                      </div>
                                    </div>
                                  </PopoverContent>
                                </Popover>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={getStatusBadgeVariant(lineStatus)}>
                              {formatStatusLabel(lineStatus)}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}
    </div>
  );
}
