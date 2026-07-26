'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import { CheckCircle2, Info, PackageCheck, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { usePurchaseOrders } from '../../hooks/usePurchaseOrders';
import { usePurchaseOrderActions } from '../../hooks/usePurchaseOrderActions';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { BulkActionsMenu } from '../../components/BulkActionsMenu';
import { buildPoBulkActions } from '../lib/poBulkActions';
import { fmtDate, fmtInt } from '../../lib/format';
import type { PurchaseOrder, PurchaseOrderStatus } from '../../types/scm.types';

type BadgeDef = { variant: 'secondary' | 'primary' | 'warning' | 'success'; label: string };

/** Title-case an unknown enum value so any BE-supplied string still reads well. */
function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_BADGE: Partial<Record<PurchaseOrderStatus, BadgeDef>> = {
  draft: { variant: 'secondary', label: 'Draft' },
  draft_recommendation: { variant: 'secondary', label: 'Draft' },
  active: { variant: 'primary', label: 'Active' },
  confirmed: { variant: 'primary', label: 'Confirmed' },
  partially_received: { variant: 'warning', label: 'Partially received' },
  received: { variant: 'success', label: 'Received' },
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s as PurchaseOrderStatus] ?? { variant: 'secondary', label: titleCase(s) };

const isDraft = (s: string) => s === 'draft_recommendation' || s === 'draft';
const countsAsOnOrder = (po: PurchaseOrder) =>
  po.is_on_order ?? (!isDraft(po.status) && po.status !== 'cancelled');

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'draft_recommendation', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'partially_received', label: 'Partially received' },
  { value: 'received', label: 'Received' },
  { value: 'cancelled', label: 'Cancelled' },
];

export default function PurchaseOrdersList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // Confirm-flow dialog state.
  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);
  const [grPo, setGrPo] = useState<PurchaseOrder | null>(null);

  const { data, isLoading, isFetching, refetch } = usePurchaseOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter || null,
    supplier: null,
  });

  const { confirm, createGr } = usePurchaseOrderActions();

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setRowSelection({});
  }, [searchQuery, statusFilter]);

  const rows = useMemo<PurchaseOrder[]>(() => data?.data ?? [], [data]);

  const columns = useMemo<ColumnDef<PurchaseOrder>[]>(
    () => [
      // Select-all means all rows (the user unticks what they don't want); the Confirm
      // action then applies to the draft subset of the selection (see bulkActions).
      buildSelectColumn<PurchaseOrder>(),
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO number" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col gap-0.5">
            <div className="flex min-w-0 items-center gap-2">
              <Link
                href={`/scm/purchase-orders/${row.original.id}`}
                onClick={(e) => e.stopPropagation()}
                className="truncate font-medium text-primary hover:underline"
                title={`Open ${row.original.po_number}`}
              >
                {row.original.po_number}
              </Link>
              {row.original.source === 'autocount' ? (
                <AutoCountSourceBadge source="autocount" />
              ) : null}
            </div>
            <span className="text-xs text-muted-foreground">{fmtDate(row.original.order_date)}</span>
          </div>
        ),
        size: 200,
        meta: { headerTitle: 'PO number', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate" title={row.original.supplier_name}>
              {row.original.supplier_name}
            </span>
            {row.original.warehouse_name ? (
              <span className="text-xs text-muted-foreground">{row.original.warehouse_name}</span>
            ) : null}
          </div>
        ),
        size: 220,
        meta: { headerTitle: 'Supplier' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const s = statusBadge(row.original.status);
          return (
            <Badge variant={s.variant} appearance="light">
              {s.label}
            </Badge>
          );
        },
        size: 150,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'on_order',
        header: ({ column }) => <DataGridColumnHeader title="On order" column={column} />,
        cell: ({ row }) =>
          countsAsOnOrder(row.original) ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-scm-incoming">
              <CheckCircle2 className="size-3.5" /> On order
            </span>
          ) : (
            <span className="text-xs text-muted-foreground" title="Drafts don't count as incoming stock until confirmed">
              Not on order
            </span>
          ),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'On order' },
      },
      {
        accessorKey: 'expected_date',
        header: ({ column }) => <DataGridColumnHeader title="Expected date" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{fmtDate(row.original.expected_date)}</span>
        ),
        size: 140,
        meta: { headerTitle: 'Expected date' },
      },
      {
        accessorKey: 'total_qty',
        header: ({ column }) => <DataGridColumnHeader title="Total qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.total_qty),
        size: 100,
        meta: { headerTitle: 'Total qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => fmtInt(row.original.line_count),
        size: 80,
        meta: { headerTitle: 'Lines', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        // create-GR stays a PER-ROW action on an active PO (not bulk). Drafts
        // have no per-row action — they're confirmed via the bulk Actions menu.
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const po = row.original;
          // AutoCount-mirrored POs are read-only — no Create GR (the BE 403s it).
          if (po.source === 'autocount') return null;
          if (po.status === 'active' || po.status === 'confirmed' || po.status === 'partially_received') {
            return (
              <div className="flex items-center justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1 px-2 text-xs"
                  onClick={() => setGrPo(po)}
                >
                  <PackageCheck className="size-3.5" />
                  Create GR
                </Button>
              </div>
            );
          }
          return null;
        },
        size: 130,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    // AutoCount-mirrored POs are read-only — exclude them from bulk-select so
    // they can never be swept into a bulk Confirm (the BE 403s them anyway).
    enableRowSelection: (row) => row.original.source !== 'autocount',
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filtersActive = statusFilter ? 1 : 0;

  // Confirm applies to the DRAFT subset of the selection (select-all can include actives).
  const selectedDraftIds = table
    .getSelectedRowModel()
    .rows.filter((r) => isDraft(r.original.status))
    .map((r) => r.original.id);

  const runConfirm = async () => {
    if (!confirmIds) return;
    try {
      const res = await confirm.mutateAsync(confirmIds);
      table.resetRowSelection();
      toast.success(
        `Confirmed ${res.confirmed_count} purchase order${res.confirmed_count === 1 ? '' : 's'} — now counted as incoming stock`,
      );
      setConfirmIds(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to confirm purchase orders');
    }
  };

  const runCreateGr = async () => {
    if (!grPo) return;
    try {
      const res = await createGr.mutateAsync(grPo.id);
      toast.success(`Goods receipt ${res.gr_reference} created for ${grPo.po_number}`);
      setGrPo(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to create goods receipt');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          Draft POs are drafted from accepted reorder recommendations and are NOT counted as incoming
          stock. Confirm a draft (single or in bulk) to make it Active — only then does it count as
          on-order. Create a goods receipt from an Active PO to record what arrived.
        </span>
      </div>

      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage="No purchase orders yet. Accept a funded reorder recommendation to draft one."
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search PO or supplier..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-64 ps-9"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label className="mb-1 block">Status</Label>
                      <SearchableSelect
                        value={statusFilter}
                        onChange={setStatusFilter}
                        options={STATUS_FILTER_OPTIONS}
                        placeholder="All statuses"
                      />
                    </div>
                    {filtersActive > 0 ? (
                      <div className="flex justify-end">
                        <Button variant="ghost" size="sm" onClick={() => setStatusFilter('')}>
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              bulkActionsSlot={
                // Unified "Actions" dropdown (same pattern as the reorder results grid).
                // Only surfaces Confirm when the selection contains ≥1 draft; BulkActionsMenu
                // renders nothing (button hidden) when no action applies to the selection.
                <BulkActionsMenu
                  actions={
                    selectedDraftIds.length > 0
                      ? [
                          {
                            key: 'confirm',
                            label: `Confirm ${selectedDraftIds.length} draft${selectedDraftIds.length === 1 ? '' : 's'}`,
                            icon: CheckCircle2,
                            onClick: () => setConfirmIds(selectedDraftIds),
                          },
                        ]
                      : []
                  }
                />
              }
              exportConfig={{ filename: 'purchase_orders_export.xlsx' }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <ConfirmActionDialog
        open={!!confirmIds}
        onOpenChange={(o) => !o && setConfirmIds(null)}
        title="Confirm purchase orders?"
        description={
          confirmIds
            ? `Confirm ${fmtInt(confirmIds.length)} draft purchase order${
                confirmIds.length === 1 ? '' : 's'
              }? Confirming makes these count as incoming stock (on-order) in the next reorder run.`
            : ''
        }
        confirmLabel="Confirm POs"
        onConfirm={runConfirm}
        isBusy={confirm.isPending}
      />

      <ConfirmActionDialog
        open={!!grPo}
        onOpenChange={(o) => !o && setGrPo(null)}
        title="Create goods receipt?"
        description={
          grPo
            ? `Create a goods receipt for ${grPo.po_number} (${grPo.supplier_name})? This stamps the received quantity against each line.`
            : ''
        }
        confirmLabel="Create GR"
        onConfirm={runCreateGr}
        isBusy={createGr.isPending}
      />
    </div>
  );
}
