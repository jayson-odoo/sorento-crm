'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { buildDetailSearch } from '@/lib/listNavQuery';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { toast } from 'sonner';
import { CheckCircle2, LoaderCircle, PackageCheck, Search, Upload, X } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePurchaseOrders } from '../../hooks/usePurchaseOrders';
import { usePurchaseOrderActions } from '../../hooks/usePurchaseOrderActions';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { BulkActionsMenu } from '../../components/BulkActionsMenu';
import { OutstandingUploadDialog } from '../../reorder/components/OutstandingUploadDialog';
import { buildPoBulkActions } from '../lib/poBulkActions';
import { EM_DASH, fmtDate, fmtInt, fmtMoney, fmtSupplierCost } from '../../lib/format';
import type { PurchaseOrder, PurchaseOrderStatus } from '../../types/scm.types';

/** All / Outstanding / Closed - the buyer's "at a glance" read (the captain, 20 Aug: "how
 *  do i know the open PO / outstanding PO"). Maps straight onto the list's `outstanding`
 *  query param: `true` / `false` / omitted. Default Outstanding, because that is the
 *  question this screen exists to answer. */
type OutstandingFilter = 'all' | 'outstanding' | 'closed';

const OUTSTANDING_TO_PARAM: Record<OutstandingFilter, boolean | null> = {
  all: null,
  outstanding: true,
  closed: false,
};

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
  // Default Outstanding: the buyer's "at a glance" question, answered without opening
  // the advanced Filters popover.
  const [outstandingFilter, setOutstandingFilter] = useState<OutstandingFilter>('outstanding');
  // "Have we ever bought this item, and for how much." The plan now takes its cost from
  // this book, so when a plan line shows no cost, this is where the buyer finds out why.
  const [productFilter, setProductFilter] = useState('');
  // Committed on Enter or blur rather than per keystroke: this filter hits the whole order
  // book by line, and firing it on every character is a query per letter typed.
  const [productDraft, setProductDraft] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // Confirm-flow dialog state.
  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);
  const [grPo, setGrPo] = useState<PurchaseOrder | null>(null);
  // Bulk delete (captain, 20 Aug: "give me an option to bulk delete purchase orders").
  const [deleteIds, setDeleteIds] = useState<string[] | null>(null);
  // The outstanding PURCHASE-ORDER book is loaded here, on the screen whose actor owns
  // it, until AutoCount is integrated.
  const [uploadOpen, setUploadOpen] = useState(false);

  const { data, isLoading, isFetching, refetch } = usePurchaseOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter || null,
    supplier: null,
    productCode: productFilter || null,
    outstanding: OUTSTANDING_TO_PARAM[outstandingFilter],
  });

  const { confirm, createGr, bulkDelete } = usePurchaseOrderActions();

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    setRowSelection({});
  }, [searchQuery, statusFilter, productFilter, outstandingFilter]);

  const rows = useMemo<PurchaseOrder[]>(() => data?.data ?? [], [data]);

  // Carried into the detail URL so its prev/next pager walks the SAME filtered, sorted page
  // the user was reading (same param names as the list GET).
  const detailSearch = useMemo(
    () =>
      buildDetailSearch(
        { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
        {
          status: statusFilter || undefined,
          product_code: productFilter || undefined,
          outstanding: OUTSTANDING_TO_PARAM[outstandingFilter] ?? undefined,
        },
      ),
    [
      pagination.pageIndex,
      pagination.pageSize,
      sorting,
      searchQuery,
      statusFilter,
      productFilter,
      outstandingFilter,
    ],
  );

  const columns = useMemo<ColumnDef<PurchaseOrder>[]>(
    () => [
      // Select-all means all rows (the user unticks what they don't want); the Confirm
      // action then applies to the draft subset of the selection (see bulkActions).
      buildSelectColumn<PurchaseOrder>(),
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO number" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <Link
              href={`/scm/purchase-orders/${row.original.id}${detailSearch ? `?${detailSearch}` : ''}`}
              onClick={(e) => e.stopPropagation()}
              className="font-medium text-primary hover:underline"
              title={`Open ${row.original.po_number}`}
            >
              {row.original.po_number}
            </Link>
            <span className="text-xs text-muted-foreground">{fmtDate(row.original.order_date)}</span>
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'PO number', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) =>
          row.original.supplier_name ? (
            <span className="truncate" title={row.original.supplier_name}>
              {row.original.supplier_name}
            </span>
          ) : (
            // An imported historical PO can carry no supplier at all. Blank read as the
            // warehouse underneath it standing in for the supplier - the captain's "why
            // is BRW under supplier?" - so this is an explicit dash, never the location.
            <span
              className="truncate text-muted-foreground"
              title="No supplier on this imported PO"
            >
              {EM_DASH}
            </span>
          ),
        size: 180,
        meta: { headerTitle: 'Supplier' },
      },
      // No header-level Location column (captain, 20 Aug: "PO's location is at line
      // level ... at header level we don't need location actually") - the per-line
      // warehouse lives on the detail page's lines grid, where the fact is real.
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
        // have no per-row action - they're confirmed via the bulk Actions menu.
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const po = row.original;
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
    [detailSearch],
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
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filtersActive = (statusFilter ? 1 : 0) + (productFilter ? 1 : 0);
  const lastCost = data?.product_cost ?? null;

  // Confirm applies to the DRAFT subset of the selection (select-all can include actives);
  // Delete applies to the WHOLE selection regardless of status.
  const selectedIds = table.getSelectedRowModel().rows.map((r) => r.original.id);
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
        `Confirmed ${res.confirmed_count} purchase order${res.confirmed_count === 1 ? '' : 's'} - now counted as incoming stock`,
      );
      setConfirmIds(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to confirm purchase orders');
    }
  };

  /**
   * The upload was QUEUED, so there is nothing yet to report: it writes on the worker and
   * the drawer is already following the job. Refetching is still worth doing - the list
   * re-reads as soon as the job lands rather than showing yesterday's book until a reload -
   * and the dialog has already told the user it is queued.
   */
  const bookQueued = () => {
    void refetch();
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

  const runBulkDelete = async () => {
    if (!deleteIds) return;
    try {
      const res = await bulkDelete.mutateAsync(deleteIds);
      table.resetRowSelection();
      const deletedMsg = `Deleted ${res.deleted} purchase order${res.deleted === 1 ? '' : 's'}`;
      // The side effect the buyer has to know about, not just the count they asked for:
      // any row that was placed on one of these POs is back on the board unplaced.
      toast.success(
        res.unplaced_rows > 0
          ? `${deletedMsg} - ${res.unplaced_rows} order-inquiry row${res.unplaced_rows === 1 ? '' : 's'} placed on them ${res.unplaced_rows === 1 ? 'was' : 'were'} put back on the board`
          : deletedMsg,
      );
      setDeleteIds(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete purchase orders');
    }
  };

  return (
    <div className="space-y-3">
      {/* The draft-vs-active explainer banner lived here until the captain removed it
          (20 Aug) - teaching prose belongs in the user guide, not the UI. */}
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        emptyMessage="No purchase orders yet. Accept a funded reorder recommendation to draft one."
      >
        <Card>
          {productFilter ? (
            <div
              className="border-b px-5 py-2.5 text-sm"
              role="status"
              aria-label="Last purchase price"
            >
              {lastCost ? (
                <span>
                  Last paid{' '}
                  <span className="font-medium tabular-nums">
                    {/* In the currency the order was written in. The book is 8438 lines
                        USD against 4186 MYR, so "RM 45" against a USD purchase order is a
                        wrong number, not a formatting detail. */}
                    {fmtSupplierCost(lastCost.unit_cost, lastCost.currency)}
                  </span>{' '}
                  for <span className="font-medium">{productFilter}</span>
                  {lastCost.supplier_name ? ` from ${lastCost.supplier_name}` : ''} on{' '}
                  {lastCost.po_number}
                  {lastCost.issue_date ? ` (${fmtDate(lastCost.issue_date)})` : ''}.
                </span>
              ) : (
                // Never bought is a different answer from bought for nothing, and this is
                // the screen where the buyer tells them apart: a plan line with no cost is
                // explained by this sentence.
                <span className="text-muted-foreground">
                  No purchase order records a price for{' '}
                  <span className="font-medium text-foreground">{productFilter}</span>, so the
                  plan has no cost to work from.
                </span>
              )}
            </div>
          ) : null}
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <>
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
                  {/* "How do i know the open PO / outstanding PO" (the captain, 20 Aug) -
                      a glance-able control, not buried inside the Filters popover. */}
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    value={outstandingFilter}
                    onValueChange={(v) => v && setOutstandingFilter(v as OutstandingFilter)}
                  >
                    <ToggleGroupItem value="all" className="px-3">
                      All
                    </ToggleGroupItem>
                    <ToggleGroupItem value="outstanding" className="px-3">
                      Outstanding
                    </ToggleGroupItem>
                    <ToggleGroupItem value="closed" className="px-3">
                      Closed
                    </ToggleGroupItem>
                  </ToggleGroup>
                </>
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="po-product-code" className="mb-1 block">
                        Product code
                      </Label>
                      <Input
                        id="po-product-code"
                        placeholder="e.g. MWC7624-RL-S10"
                        value={productDraft}
                        onChange={(e) => setProductDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') setProductFilter(productDraft.trim());
                        }}
                        onBlur={() => setProductFilter(productDraft.trim())}
                      />
                    </div>
                    <div>
                      <Label htmlFor="po-status" className="mb-1 block">
                        Status
                      </Label>
                      <SearchableSelect
                        id="po-status"
                        value={statusFilter}
                        onChange={setStatusFilter}
                        options={STATUS_FILTER_OPTIONS}
                        placeholder="All statuses"
                      />
                    </div>
                    {filtersActive > 0 ? (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setStatusFilter('');
                            setProductFilter('');
                            setProductDraft('');
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              bulkActionsSlot={
                // Unified "Actions" dropdown (same pattern as the reorder results grid).
                // Confirm surfaces when the selection contains ≥1 draft; Delete surfaces
                // whenever anything at all is selected. BulkActionsMenu renders nothing
                // (button hidden) when neither applies.
                <BulkActionsMenu
                  actions={buildPoBulkActions(
                    { draftCount: selectedDraftIds.length, selectedCount: selectedIds.length },
                    {
                      onConfirm: () => setConfirmIds(selectedDraftIds),
                      onDelete: () => setDeleteIds(selectedIds),
                    },
                  )}
                />
              }
              secondaryActions={[
                {
                  key: 'upload-order-book',
                  label: 'Upload order book',
                  icon: Upload,
                  onClick: () => setUploadOpen(true),
                },
              ]}
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

      <OutstandingUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        kind="purchase-orders"
        onQueued={bookQueued}
      />

      {/* Destructive - AlertDialog + destructive button per ADR-PRODUCT-STANDARDS, not
          ConfirmActionDialog (that one is reserved for non-destructive confirms). */}
      <AlertDialog open={!!deleteIds} onOpenChange={(o) => !o && setDeleteIds(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteIds
                ? `Delete ${fmtInt(deleteIds.length)} purchase order${
                    deleteIds.length === 1 ? '' : 's'
                  }? This action cannot be undone.`
                : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteIds(null)}
              disabled={bulkDelete.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={runBulkDelete}
              disabled={bulkDelete.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {bulkDelete.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
