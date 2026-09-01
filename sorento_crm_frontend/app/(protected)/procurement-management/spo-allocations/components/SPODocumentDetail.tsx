'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  FileText,
  Info,
  Link as LinkIcon,
  ListOrdered,
  LoaderCircleIcon,
  RotateCcw,
  SquarePen,
  Trash2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { formatStatusLabel } from '@/lib/status-badge';
import { parseDetailSearch } from '@/lib/listNavQuery';
import DetailActions from '@/components/common/DetailActions';
import BackToList from '@/components/common/BackToList';
import { WarehouseCombobox } from './WarehouseCombobox';
import { useSPODocument, spoDocumentsPagerQuery } from '../hooks/useSPODocuments';
import { useUpdateSPOAllocation, useDeleteSPOAllocation } from '../hooks/useSPOAllocations';
import {
  fmtEta,
  fmtQty,
  overdueClassName,
  planningSpanBadge,
  spoDocumentStatusPill,
} from '../lib/spoDocumentStatus';
import type { SPODocument, SPODocumentLine } from '../types/spoDocument.types';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { Warehouse } from '@/app/(protected)/inventory-management/warehouses/types/warehouse.types';

const DETAIL_PATH = '/procurement-management/spo-allocations';

function detailHref(spoNumber: string, search: string): string {
  return `${DETAIL_PATH}/${encodeURIComponent(spoNumber)}${search ? `?${search}` : ''}`;
}

type LineDraft = {
  warehouse_id: string;
  allocated_quantity: string;
  quantity_received: string;
  quantity_rejected: string;
};

function seedDraft(line: SPODocumentLine): LineDraft {
  return {
    warehouse_id: line.warehouse_id ?? '',
    allocated_quantity: String(line.allocated_quantity),
    quantity_received: String(line.quantity_received),
    quantity_rejected: String(line.quantity_rejected),
  };
}

function Field({ label, htmlFor, children }: { label: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function SPODocumentDetail({ spoNumber }: { spoNumber: string }) {
  const { data, isLoading, isError } = useSPODocument(spoNumber);
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseDetailSearch(searchParams), [searchParams]);
  const filterProductId = filters.filters.product_id || null;
  const filterWarehouseId = filters.filters.warehouse_id || null;

  const doc = data ?? null;

  const [isEditing, setIsEditing] = useState(false);
  const [lineDrafts, setLineDrafts] = useState<Record<string, LineDraft>>({});
  const [removedLineIds, setRemovedLineIds] = useState<Set<string>>(new Set());
  const [supplierExpanded, setSupplierExpanded] = useState(false);
  const [saving, setSaving] = useState(false);

  const updateLineMutation = useUpdateSPOAllocation();
  const deleteLineMutation = useDeleteSPOAllocation();

  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  useEffect(() => {
    getWarehouses({ pageIndex: 0, pageSize: 100, sorting: [], searchQuery: '', is_active: true }).then((res) =>
      setWarehouses(res.data ?? []),
    );
  }, []);

  // Stepping to a neighbouring document (the pager, or Back then another row) must not
  // carry the previous document's edit session along with it.
  useEffect(() => {
    setIsEditing(false);
    setLineDrafts({});
    setRemovedLineIds(new Set());
    setSupplierExpanded(false);
  }, [spoNumber]);

  const beginEdit = (d: SPODocument) => {
    const drafts: Record<string, LineDraft> = {};
    for (const line of d.lines) drafts[line.id] = seedDraft(line);
    setLineDrafts(drafts);
    setRemovedLineIds(new Set());
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
    setLineDrafts({});
    setRemovedLineIds(new Set());
  };

  const toggleRemoveLine = (lineId: string) => {
    setRemovedLineIds((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  };

  const handleSave = async () => {
    if (!doc) return;
    setSaving(true);
    try {
      const toDelete = [...removedLineIds];
      // Only a line whose draft actually differs from what it was seeded with -
      // toggling one line's removal must not re-PUT every other line unchanged.
      const toUpdate = doc.lines
        .filter((l) => !removedLineIds.has(l.id) && lineDrafts[l.id])
        .filter((l) => {
          const draft = lineDrafts[l.id];
          const seed = seedDraft(l);
          return (
            draft.warehouse_id !== seed.warehouse_id ||
            draft.allocated_quantity !== seed.allocated_quantity ||
            draft.quantity_received !== seed.quantity_received ||
            draft.quantity_rejected !== seed.quantity_rejected
          );
        });

      const results = await Promise.allSettled([
        ...toUpdate.map((l) =>
          updateLineMutation.mutateAsync({
            id: l.id,
            data: {
              warehouse_id: lineDrafts[l.id].warehouse_id || null,
              allocated_quantity: Number(lineDrafts[l.id].allocated_quantity) || 0,
              quantity_received: Number(lineDrafts[l.id].quantity_received) || 0,
              quantity_rejected: Number(lineDrafts[l.id].quantity_rejected) || 0,
            },
          }),
        ),
        ...toDelete.map((id) => deleteLineMutation.mutateAsync(id)),
      ]);

      const changed = toUpdate.length + toDelete.length;
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (changed === 0) {
        toast.success('No changes to save.');
      } else if (failed === 0) {
        const parts = [
          toUpdate.length ? `${toUpdate.length} line${toUpdate.length === 1 ? '' : 's'} updated` : null,
          toDelete.length ? `${toDelete.length} line${toDelete.length === 1 ? '' : 's'} removed` : null,
        ].filter(Boolean);
        toast.success(`Saved. ${parts.join(', ')}.`);
      } else if (failed === changed) {
        toast.error(`Nothing saved - ${failed} line change${failed === 1 ? '' : 's'} failed.`);
      } else {
        toast.error(`Saved ${changed - failed} of ${changed} line changes; ${failed} failed.`);
      }
      if (failed === 0) {
        setIsEditing(false);
        setLineDrafts({});
        setRemovedLineIds(new Set());
      }
    } finally {
      setSaving(false);
    }
  };

  const isMatchingLine = (line: SPODocumentLine): boolean => {
    if (!filterProductId && !filterWarehouseId) return false;
    return (
      (!filterProductId || line.product_id === filterProductId) &&
      (!filterWarehouseId || line.warehouse_id === filterWarehouseId)
    );
  };

  const visibleLines = useMemo(() => doc?.lines ?? [], [doc]);
  const matchingCount = useMemo(
    () => (filterProductId || filterWarehouseId ? visibleLines.filter(isMatchingLine).length : 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleLines, filterProductId, filterWarehouseId],
  );

  const distinctSuppliers = useMemo(() => {
    const names = new Set<string>();
    for (const l of visibleLines) if (l.supplier_name) names.add(l.supplier_name);
    return [...names];
  }, [visibleLines]);

  const columns = useMemo<ColumnDef<SPODocumentLine>[]>(
    () => [
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          const matches = isMatchingLine(line);
          const removed = removedLineIds.has(line.id);
          return (
            <div className={cn('flex items-start gap-2', removed && 'opacity-50')}>
              {matches ? (
                <span
                  className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary"
                  aria-hidden
                  title="Matches your filter"
                />
              ) : null}
              <div className="flex min-w-0 flex-col">
                <span className={cn('truncate font-medium', matches && 'text-primary')}>
                  {line.product?.product_code ?? '-'}
                  {removed ? <span className="ms-1 text-xs font-normal text-muted-foreground">(removed)</span> : null}
                </span>
                <span className="truncate text-xs text-muted-foreground" title={line.product?.product_name}>
                  {line.product?.product_name ?? ''}
                </span>
              </div>
            </div>
          );
        },
        size: 220,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'warehouse',
        header: ({ column }) => <DataGridColumnHeader title="Warehouse" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (isEditing) {
            const draft = lineDrafts[line.id];
            return (
              <WarehouseCombobox
                value={draft?.warehouse_id ?? ''}
                onChange={(v) =>
                  setLineDrafts((prev) => ({ ...prev, [line.id]: { ...seedDraft(line), ...prev[line.id], warehouse_id: v } }))
                }
                warehouses={warehouses}
                warehouseFallback={line.warehouse}
                placeholder="No warehouse"
                className="h-8"
                clearable
              />
            );
          }
          return line.warehouse ? line.warehouse.warehouse_code : <span className="text-muted-foreground">No location</span>;
        },
        size: 160,
        meta: { headerTitle: 'Warehouse' },
      },
      {
        id: 'allocated',
        accessorFn: (l) => l.allocated_quantity,
        header: ({ column }) => <DataGridColumnHeader title="Allocated" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (isEditing) {
            const draft = lineDrafts[line.id];
            return (
              <Input
                type="number"
                min={0}
                aria-label={`Allocated qty on ${line.product?.product_code ?? line.id}`}
                value={draft?.allocated_quantity ?? String(line.allocated_quantity)}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [line.id]: { ...seedDraft(line), ...prev[line.id], allocated_quantity: e.target.value },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtQty(line.allocated_quantity);
        },
        size: 110,
        meta: { headerTitle: 'Allocated', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'received',
        accessorFn: (l) => l.quantity_received,
        header: ({ column }) => <DataGridColumnHeader title="Received" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (isEditing) {
            const draft = lineDrafts[line.id];
            return (
              <Input
                type="number"
                min={0}
                aria-label={`Received qty on ${line.product?.product_code ?? line.id}`}
                value={draft?.quantity_received ?? String(line.quantity_received)}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [line.id]: { ...seedDraft(line), ...prev[line.id], quantity_received: e.target.value },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtQty(line.quantity_received);
        },
        size: 110,
        meta: { headerTitle: 'Received', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'rejected',
        accessorFn: (l) => l.quantity_rejected,
        header: ({ column }) => <DataGridColumnHeader title="Rejected" column={column} />,
        cell: ({ row }) => {
          const line = row.original;
          if (isEditing) {
            const draft = lineDrafts[line.id];
            return (
              <Input
                type="number"
                min={0}
                aria-label={`Rejected qty on ${line.product?.product_code ?? line.id}`}
                value={draft?.quantity_rejected ?? String(line.quantity_rejected)}
                onChange={(e) =>
                  setLineDrafts((prev) => ({
                    ...prev,
                    [line.id]: { ...seedDraft(line), ...prev[line.id], quantity_rejected: e.target.value },
                  }))
                }
                className="h-8 text-right tabular-nums"
              />
            );
          }
          return fmtQty(line.quantity_rejected);
        },
        size: 100,
        meta: { headerTitle: 'Rejected', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'balance',
        accessorFn: (l) => l.balance,
        header: ({ column }) => <DataGridColumnHeader title="Balance" column={column} />,
        cell: ({ row }) => fmtQty(row.original.balance),
        size: 100,
        meta: { headerTitle: 'Balance', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'eta',
        accessorFn: (l) => l.arrival_date ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader
            title="ETA"
            column={column}
            // The source, on the column itself (markup ruling, Q3/Q16): shipment
            // `eta_delay_date` -> shipment `estimated_arrival_date` -> SPO line
            // `expected_date`. Rendered AS IS - no TBA masking of a placeholder date.
            icon={
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="size-3.5 text-muted-foreground" aria-label="Where this date comes from" />
                </TooltipTrigger>
                <TooltipContent>
                  Shipment revised ETA, else shipment estimate, else the SPO line&apos;s expected date.
                </TooltipContent>
              </Tooltip>
            }
          />
        ),
        cell: ({ row }) => fmtEta(row.original.arrival_date),
        size: 110,
        meta: { headerTitle: 'ETA' },
      },
      {
        id: 'overdue',
        accessorFn: (l) => l.overdue_days,
        header: ({ column }) => <DataGridColumnHeader title="Overdue" column={column} />,
        cell: ({ row }) => {
          const days = row.original.overdue_days;
          return <span className={overdueClassName(days)}>{days > 0 ? `${days}d` : '-'}</span>;
        },
        size: 100,
        meta: { headerTitle: 'Overdue', headerClassName: 'text-right', cellClassName: 'text-right' },
      },
      {
        id: 'plan',
        header: ({ column }) => <DataGridColumnHeader title="Plan" column={column} />,
        cell: ({ row }) => {
          const pill = planningSpanBadge(row.original.planning_span);
          return (
            <Badge variant={pill.variant} appearance="light" size="sm">
              {pill.label}
            </Badge>
          );
        },
        size: 110,
        meta: { headerTitle: 'Plan' },
      },
      {
        id: 'packing_list',
        header: 'Packing List',
        cell: ({ row }) => {
          const ship = row.original.inbound_shipment;
          if (!ship) return <span className="text-muted-foreground">-</span>;
          return (
            <Link
              href={`/procurement-management/packing-lists/${ship.id}`}
              className="flex items-center gap-1 text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              <LinkIcon className="size-3 shrink-0" />
              <span className="truncate">
                {ship.shipment_number}
                {ship.shipping_container_number ? ` (${ship.shipping_container_number})` : ''}
              </span>
            </Link>
          );
        },
        size: 170,
        meta: { headerTitle: 'Packing List' },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge status={row.original.receipt_status} size="sm">
            {formatStatusLabel(row.original.receipt_status)}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          if (!isEditing) return null;
          const line = row.original;
          const removed = removedLineIds.has(line.id);
          return (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={cn('gap-1.5', removed ? '' : 'text-destructive hover:text-destructive')}
              onClick={() => toggleRemoveLine(line.id)}
            >
              {removed ? <RotateCcw className="size-4" /> : <Trash2 className="size-4" />}
              {removed ? 'Undo' : 'Remove'}
            </Button>
          );
        },
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    // `isEditing` / `lineDrafts` / `removedLineIds` / `warehouses` drive the editable
    // cells; `filterProductId` / `filterWarehouseId` drive the highlight dot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isEditing, lineDrafts, removedLineIds, warehouses, filterProductId, filterWarehouseId],
  );

  const table = useReactTable({
    columns,
    data: visibleLines,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const backLink = <BackToList listPath={DETAIL_PATH} label="Back to SPO Allocations" />;

  if (isLoading && !doc) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !doc) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">SPO document not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This SPO number doesn&apos;t exist, or every allocation on it was removed. Head
            back to the list to pick another.
          </p>
        </Card>
      </div>
    );
  }

  const statusPill = spoDocumentStatusPill(doc.status);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="block py-4">
          {/* Back, the number, the status badge, Edit and the pager all read as ONE
              title row (review nit / AC-5) - not split across a page-level breadcrumb
              and this card the way most detail pages do it. */}
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {backLink}
              <CardTitle className="text-lg">{doc.spo_number}</CardTitle>
              <Badge variant={statusPill.variant} appearance="light" size="md">
                {statusPill.label}
              </Badge>
            </div>
            {isEditing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving ? <LoaderCircleIcon className="me-2 size-4 animate-spin" /> : null}
                  Save
                </Button>
              </div>
            ) : (
              <DetailActions
                pager={{
                  ...spoDocumentsPagerQuery,
                  detailPath: DETAIL_PATH,
                  currentId: doc.spo_number,
                  hrefFor: (id, search) => detailHref(id, search),
                  ariaLabel: 'SPO document',
                }}
                gearLabel="SPO document options"
                primary={
                  <Button variant="primary" size="sm" className="gap-1.5" onClick={() => beginEdit(doc)}>
                    <SquarePen className="size-4" />
                    Edit
                  </Button>
                }
              />
            )}
          </div>
        </CardHeader>
      </Card>

      <Tabs defaultValue="header" className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="header">
            <FileText />
            <span>Header</span>
          </TabsTrigger>
          <TabsTrigger value="lines">
            <ListOrdered />
            <span>Lines</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="header" className="mt-0 space-y-4 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Document</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Document" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
              <Field label="Supplier">
                <span className="flex flex-wrap items-center gap-1.5">
                  {doc.supplier_name ?? '-'}
                  {doc.supplier_extra_count > 0 ? (
                    <button
                      type="button"
                      onClick={() => setSupplierExpanded((v) => !v)}
                      className="text-xs font-normal text-primary hover:underline"
                    >
                      +{doc.supplier_extra_count} more
                    </button>
                  ) : null}
                </span>
                {supplierExpanded && distinctSuppliers.length > 1 ? (
                  <ul className="mt-1 list-disc space-y-0.5 ps-4 text-xs font-normal text-muted-foreground">
                    {distinctSuppliers.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                ) : null}
              </Field>
              <Field label="Doc date">{fmtEta(doc.doc_date)}</Field>
              <Field label="Allocated">{fmtQty(doc.total_allocated)}</Field>
              <Field label="Received">{fmtQty(doc.total_received)}</Field>
              <Field label="Balance">{fmtQty(doc.balance)}</Field>
              <Field label="Line count">{fmtQty(doc.line_count)}</Field>
            </section>
          </Card>
        </TabsContent>

        <TabsContent value="lines" className="mt-0 space-y-3 focus-visible:outline-none">
          {matchingCount > 0 ? (
            <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
              {matchingCount} line{matchingCount === 1 ? '' : 's'} below match your product/warehouse
              filter from the list - marked with a dot.
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={visibleLines.length}
            isLoading={false}
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            emptyMessage="This SPO document has no lines."
            // A real key, not the pathname fallback (review S2): every document's URL is
            // different, so a per-pathname key would fragment one reader's column prefs
            // across every SPO number they ever open instead of sharing ONE preference.
            listingKey="procurement.spo_allocations.view::spo-document-lines"
          >
            <Card>
              <CardHeader>
                <CardHeading>
                  <CardTitle>Lines</CardTitle>
                </CardHeading>
              </CardHeader>
              <CardTable>
                <DataGridTable />
              </CardTable>
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
            </Card>
          </DataGrid>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default SPODocumentDetail;
