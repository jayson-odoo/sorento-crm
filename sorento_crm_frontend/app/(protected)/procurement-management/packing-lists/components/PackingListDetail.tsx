'use client';

import { useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Edit, Trash2, Link as LinkIcon, Search, X, ArrowUpDown, ArrowUp, ArrowDown, Link2, Unlink, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  usePackingList,
  useDeletePackingList,
  usePackingListSourceInvoices,
  useUpdatePackingList,
} from '../hooks/usePackingLists';
import { useSupplierSelectQuery } from '../../suppliers/hooks/useSupplierSelectQuery';
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
import LinkAttachmentBrowserDialog from '@/components/common/LinkAttachmentBrowserDialog';
import ClearanceDeliveryCard from './ClearanceDeliveryCard';
import { CLEARANCE_ATTRIBUTE_FIELDS } from '../forms/packing-list-schema';
import SourceProformaInvoicesCard from './SourceProformaInvoicesCard';
import SpoPlannerTable from './SpoPlannerTable';

interface PackingListDetailProps {
  packingListId: string;
}

/** A Numeric column arrives as a string on the wire; anything unreadable is "not stated". */
function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Volume as a person writes it: `3.4`, not `3.4000`, and "-" when nobody measured it. */
function fmtCbm(value: number | string | null | undefined): string {
  const parsed = toNumber(value);
  if (parsed === null) return '-';
  return String(Number(parsed.toFixed(3)));
}

export default function PackingListDetail({
  packingListId,
}: PackingListDetailProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: packingList, isLoading } = usePackingList(packingListId);

  // `?tab=` so a tab survives a refresh and can be linked to directly. Written
  // with replace() so tab switching does not fill the back button with history.
  const TABS = ['timeline', 'details', 'documents', 'lines', 'spo'] as const;
  const requestedTab = searchParams.get('tab');
  const activeTab = TABS.includes(requestedTab as (typeof TABS)[number])
    ? (requestedTab as string)
    : 'timeline';
  const setActiveTab = (next: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', next);
    router.replace(`?${params.toString()}`, { scroll: false });
  };
  const updatePackingListMutation = useUpdatePackingList();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const lineCount = packingList?.shipment_lines?.length ?? 0;
  const [linkAttachmentDialogOpen, setLinkAttachmentDialogOpen] = useState(false);
  const [shipmentLinesSearch, setShipmentLinesSearch] = useState('');
  const [sortField, setSortField] = useState<'product' | 'quantity_shipped' | 'spo_allocated' | 'quantity_received' | 'status'>('product');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const downloadMutation = useDownloadAttachment();
  // The proforma invoices behind this container, read ONCE for the four places that show
  // them: the Details card, the Lines column, the Timeline entry and the Documents list.
  const { data: sourceInvoices } = usePackingListSourceInvoices(packingListId);
  const invoicesByLine = sourceInvoices?.by_shipment_line ?? {};
  const sourcePiNumbers = (sourceInvoices?.invoices ?? []).map((pi) => pi.pi_number);

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

  // The line response carries `supplier_id` and nothing else, and a UUID is not something
  // anyone reads. Same cached select every other procurement screen resolves suppliers with.
  const { data: suppliers = [] } = useSupplierSelectQuery();

  const supplierNameById = useMemo(() => {
    const byId = new Map<string, string>();
    for (const s of suppliers) byId.set(s.id, s.supplier_name);
    // The header's own supplier is already resolved on the payload, so it stays readable
    // even before the select answers.
    if (packingList?.supplier) byId.set(packingList.supplier.id, packingList.supplier.supplier_name);
    return byId;
  }, [suppliers, packingList?.supplier]);

  const lineSupplierName = (supplierId?: string | null): string | null =>
    (supplierId ? supplierNameById.get(supplierId) : null) ?? null;

  /**
   * Every factory named on the lines, in the order they appear.
   *
   * One container is routinely loaded by two or three of them, and the header supplier is
   * null once it is mixed - the lines are then the only record of who loaded it, so a page
   * reading the header alone would say "No supplier" about a full container.
   */
  const lineSupplierNames = useMemo(() => {
    const names: string[] = [];
    for (const line of packingList?.shipment_lines ?? []) {
      if (!line.supplier_id) continue;
      const name = supplierNameById.get(line.supplier_id);
      if (name && !names.includes(name)) names.push(name);
    }
    return names.join(', ');
  }, [packingList?.shipment_lines, supplierNameById]);

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

  /**
   * What the rows on screen add up to. The VISIBLE rows, deliberately: a footer under a
   * searched table that quietly totals the whole container reads as the search having
   * found more than it did.
   *
   * `unmeasured` is counted rather than folded into the volume, because a total of 41 cbm
   * computed from half the lines is not 41 cbm, and a container planned on it arrives too
   * full to close.
   */
  const lineTotals = useMemo(() => {
    let qty = 0;
    let cartons = 0;
    let cbm = 0;
    let unmeasured = 0;
    for (const line of sortedAndFilteredLines) {
      qty += line.quantity_shipped ?? 0;
      cartons += line.cartons_count ?? 0;
      const volume = toNumber(line.cbm);
      if (volume === null) unmeasured += 1;
      else cbm += volume;
    }
    return { qty, cartons, cbm: cbm === 0 && unmeasured > 0 ? null : cbm, unmeasured };
  }, [sortedAndFilteredLines]);

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
      {/* Header. `flex items-center justify-between` does NOT wrap: at phone width
          the 305px action group cannot fit beside the title, so it was pushed past
          the viewport and dragged the whole page into horizontal scroll (measured
          504px of content in a 360px viewport - the table below is already clipped
          by its own scroller, so the header was the only real offender). */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-bold break-words">
            {packingList.shipping_container_number || packingList.shipment_number || `Packing list ${packingList.id.slice(0, 8)}`}
          </h1>
          <p className="text-sm text-muted-foreground">
            {packingList.supplier?.supplier_name || lineSupplierNames || 'No supplier'} • Shipment
            Date:{' '}
            {packingList.shipment_date
              ? formatDate(new Date(packingList.shipment_date))
              : '-'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
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

      {/* Tabs, not stacked sections: four cards down one page meant scrolling past
          the timeline to reach the lines. `?tab=` keeps a tab linkable and keeps
          the choice on a refresh. */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="lines">
            Shipment Lines
            {lineCount > 0 && (
              <Badge variant="secondary" className="ms-2">
                {lineCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="spo">SPO Planner</TabsTrigger>
        </TabsList>

        <TabsContent value="timeline" className="mt-6 space-y-6">
          {/* Where this container came from, at the top of its own timeline: it is the
              first thing that happened to it (AC-F9). Always rendered - a container from a
              real packing-list upload says so rather than hiding the row. */}
          <Card>
            <CardHeader>
              <CardTitle>Origin</CardTitle>
            </CardHeader>
            <CardContent>
              {sourcePiNumbers.length > 0 ? (
                <p className="text-sm">
                  Created from {sourcePiNumbers.join(', ')}
                  {packingList.created_by ? ` by ${packingList.created_by}` : ''}
                  {packingList.created_at
                    ? ` on ${formatDate(new Date(packingList.created_at))}`
                    : ''}
                  .
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Read from a packing list, not drafted from a proforma invoice.
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Clearance &amp; Delivery</CardTitle>
            </CardHeader>
            <CardContent>
              <ClearanceDeliveryCard packingList={packingList} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="details" className="mt-6">
        <Card>
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
                  {packingList.supplier?.supplier_name || lineSupplierNames || '-'}
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

        {/* The non-date clearance attributes. Rendered here because the edit form
            can set them and this tab is where their read-only counterpart belongs:
            the timeline above covers the DATES, and a field you can type but never
            see afterwards reads as a save that did not work.

            Always rendered, every row, even when empty - per the CRUD standard a
            section is never hidden on missing data, and "-" is the honest answer
            for a container that has not cleared yet. */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Clearance Details</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {CLEARANCE_ATTRIBUTE_FIELDS.map((f) => {
                const value = (packingList as unknown as Record<string, unknown>)[f.name];
                return (
                  <div key={f.name} className="min-w-0">
                    <p className="text-sm text-muted-foreground">{f.label}</p>
                    <p className="font-medium break-words">
                      {value === null || value === undefined || value === '' ? '-' : String(value)}
                    </p>
                  </div>
                );
              })}
              <div className="min-w-0">
                {/* Provenance, not an editable attribute - it says which workbook
                    tab the row came from, so it is shown but never typed. */}
                <p className="text-sm text-muted-foreground">Source sheet</p>
                <p className="font-medium break-words">{packingList.source_sheet || '-'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        {/* Which proforma invoices this container was drafted from (AC-F9). */}
        <SourceProformaInvoicesCard packingListId={packingListId} />
        </TabsContent>

        <TabsContent value="documents" className="mt-6">
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
            {/* The proforma invoice files these lines were read from (AC-F9). Always
                rendered: "none" is the honest answer for a container that came off a real
                packing list, and a section that vanishes teaches nobody where to look. */}
            <div className="space-y-2">
              <p className="text-sm font-medium">Proforma invoices</p>
              {(sourceInvoices?.invoices ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No proforma invoice behind this container.
                </p>
              ) : (
                <div className="space-y-2">
                  {(sourceInvoices?.invoices ?? []).map((pi) => (
                    <div
                      key={pi.id}
                      className="flex items-center gap-2 rounded-lg border p-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{pi.pi_number}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {pi.source_ref || 'No source file recorded'}
                          {pi.supplier_name ? ` • ${pi.supplier_name}` : ''}
                        </p>
                      </div>
                      <Link
                        href={`/scm/proforma-invoices/${pi.id}`}
                        className="shrink-0 text-sm text-primary hover:underline"
                      >
                        Open
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <LinkAttachmentBrowserDialog
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
        </TabsContent>

        <TabsContent value="lines" className="mt-6">
        {!packingList.shipment_lines || packingList.shipment_lines.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-sm font-medium">No shipment lines</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This packing list has no product lines yet. They arrive with the
                packing list import, or can be added by editing the packing list.
              </p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            {/* Same non-wrapping trap as the page header: "Shipment Lines" plus a
                224px search box does not fit the 286px of card content at 375px. */}
            <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="min-w-0 break-words">Shipment Lines</CardTitle>
              <div className="relative flex w-full items-center gap-2 sm:w-auto">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <Input
                  placeholder="Search by product code"
                  value={shipmentLinesSearch}
                  onChange={(e) => setShipmentLinesSearch(e.target.value)}
                  className="ps-9 w-full sm:w-56"
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
                      {/* Whose line this is. Not sortable: the lines arrive grouped by the
                          packing list they were read from, and re-ordering them loses that. */}
                      <TableHead>Supplier</TableHead>
                      <TableHead>
                        <button
                          onClick={() => handleSort('quantity_shipped')}
                          className="flex items-center hover:text-foreground transition-colors"
                        >
                          Quantity Shipped
                          <SortIcon field="quantity_shipped" />
                        </button>
                      </TableHead>
                      {/* How much room the goods take. Carried from the proforma invoice
                          on conversion and from the packing-list file on import, and shown
                          here because "will the next container hold this" is answered from
                          this tab (AC-F2). Not sortable, same reason as Supplier. */}
                      <TableHead className="text-end">Cartons</TableHead>
                      <TableHead className="text-end">CBM</TableHead>
                      {/* Which document charged these goods (AC-F9). Empty on a line that
                          came off a real packing list rather than a proforma invoice. */}
                      <TableHead>From PI</TableHead>
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
                          <TableCell>
                            <span
                              className="block max-w-[180px] truncate"
                              title={lineSupplierName(line.supplier_id) ?? undefined}
                            >
                              {lineSupplierName(line.supplier_id) ?? '-'}
                            </span>
                          </TableCell>
                          <TableCell>{line.quantity_shipped}</TableCell>
                          <TableCell className="text-end tabular-nums">
                            {line.cartons_count ?? '-'}
                          </TableCell>
                          <TableCell className="text-end tabular-nums">
                            {/* Null reads "-", never 0: a line nobody measured and a line
                                that takes no room are different facts (AC-F2). */}
                            {fmtCbm(line.cbm)}
                          </TableCell>
                          <TableCell>
                            {(invoicesByLine[line.id] ?? []).length === 0 ? (
                              <span className="text-muted-foreground">-</span>
                            ) : (
                              <div className="flex flex-col gap-0.5">
                                {invoicesByLine[line.id].map((src) => (
                                  <Link
                                    key={`${src.proforma_invoice_id}-${line.id}`}
                                    href={`/scm/proforma-invoices/${src.proforma_invoice_id}`}
                                    className="text-primary hover:underline"
                                  >
                                    {src.pi_number}
                                    <span className="ms-1 text-xs text-muted-foreground">
                                      {src.qty}
                                    </span>
                                  </Link>
                                ))}
                              </div>
                            )}
                          </TableCell>
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
                  {/* The total is what the container is judged against, so it sits under
                      the column rather than being added up by hand. */}
                  <TableFooter>
                    <TableRow>
                      <TableCell colSpan={2}>Total</TableCell>
                      <TableCell className="text-end tabular-nums">{lineTotals.qty}</TableCell>
                      <TableCell className="text-end tabular-nums">
                        {lineTotals.cartons}
                      </TableCell>
                      <TableCell className="text-end tabular-nums">
                        {fmtCbm(lineTotals.cbm)}
                        {lineTotals.unmeasured > 0 ? (
                          <span className="ms-1 text-xs font-normal text-muted-foreground">
                            ({lineTotals.unmeasured} unmeasured)
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell colSpan={4} />
                    </TableRow>
                  </TableFooter>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}
        </TabsContent>

        <TabsContent value="spo" className="mt-6">
          <SpoPlannerTable shipmentId={packingListId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
