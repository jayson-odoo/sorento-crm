'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { FileText, LoaderCircleIcon, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useCreateDoFromSalesOrder,
  useCreateSalesOrder,
  useDeleteSalesOrder,
  useSalesOrders,
  useUpdateSalesOrder,
} from '../../hooks/useSalesOrders';
import { fmtDate, fmtInt } from '../../lib/format';
import type {
  SalesOrder,
  SalesOrderFormData,
  SalesOrderPriority,
  SalesOrderStatus,
} from '../../types/scm.types';
import { SalesOrderFormModal } from './SalesOrderFormModal';

type BadgeVariant = 'destructive' | 'warning' | 'secondary' | 'outline' | 'primary' | 'success';
type BadgeDef = { variant: BadgeVariant; label: string };

/** Title-case an unknown enum value so any BE-supplied string still reads well. */
function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const PRIORITY_BADGE: Partial<Record<SalesOrderPriority, BadgeDef>> = {
  urgent: { variant: 'destructive', label: 'Urgent' },
  high: { variant: 'warning', label: 'High' },
  medium: { variant: 'secondary', label: 'Medium' },
  normal: { variant: 'secondary', label: 'Normal' },
  low: { variant: 'outline', label: 'Low' },
};

const STATUS_BADGE: Partial<Record<SalesOrderStatus, BadgeDef>> = {
  open: { variant: 'primary', label: 'Open' },
  partially_delivered: { variant: 'warning', label: 'Partially delivered' },
  fulfilled: { variant: 'success', label: 'Fulfilled' },
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const priorityBadge = (p: string): BadgeDef =>
  PRIORITY_BADGE[p as SalesOrderPriority] ?? { variant: 'secondary', label: titleCase(p) };
const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s as SalesOrderStatus] ?? { variant: 'secondary', label: titleCase(s) };

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'partially_delivered', label: 'Partially delivered' },
  { value: 'fulfilled', label: 'Fulfilled' },
  { value: 'cancelled', label: 'Cancelled' },
];

/** Who wrote the order. `Order inquiry` is separate from `Outstanding upload` because an
 *  order Joey's sheet created is one CS has never seen, and it decides who may edit it. */
const SOURCE_FILTER_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'inquiry', label: 'Order inquiry' },
  { value: 'upload', label: 'Outstanding upload' },
  { value: 'manual', label: 'Manual' },
];

/** How many purchase orders to name in the cell before collapsing the rest into a count. */
const WAITING_ON_LIMIT = 2;

const SOURCE_LABELS: Record<string, string> = {
  inquiry: 'Order inquiry',
  upload: 'Outstanding upload',
  manual: 'Manual',
};

const PRIORITY_FILTER_OPTIONS = [
  { value: '', label: 'All priorities' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'normal', label: 'Normal' },
  { value: 'low', label: 'Low' },
];

export default function SalesOrdersList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  // "Show me the orders the Order Inquiry sheet created" is a filter on this list rather
  // than a screen of its own: a second list of the same entity is how two screens start
  // disagreeing about the same order.
  const [sourceFilter, setSourceFilter] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SalesOrder | null>(null);
  const [deleting, setDeleting] = useState<SalesOrder | null>(null);
  const [creatingDo, setCreatingDo] = useState<SalesOrder | null>(null);

  const { data, isLoading, isFetching, refetch } = useSalesOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter || null,
    priority: priorityFilter || null,
    source: sourceFilter || null,
  });

  const createMut = useCreateSalesOrder();
  const updateMut = useUpdateSalesOrder();
  const deleteMut = useDeleteSalesOrder();
  const createDoMut = useCreateDoFromSalesOrder();

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery, statusFilter, priorityFilter, sourceFilter]);

  const rows = useMemo<SalesOrder[]>(() => data?.data ?? [], [data]);

  const handleSubmit = async (formData: SalesOrderFormData) => {
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, data: formData });
    } else {
      await createMut.mutateAsync(formData);
    }
    setFormOpen(false);
    setEditing(null);
  };

  const columns = useMemo<ColumnDef<SalesOrder>[]>(
    () => [
      {
        accessorKey: 'so_number',
        header: ({ column }) => <DataGridColumnHeader title="SO number" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.so_number}</span>
            <span className="text-xs text-muted-foreground">{fmtDate(row.original.order_date)}</span>
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'SO number', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
            {row.original.market_segment ? (
              <span className="text-xs text-muted-foreground">{row.original.market_segment}</span>
            ) : null}
          </div>
        ),
        size: 200,
        meta: { headerTitle: 'Customer' },
      },
      {
        accessorKey: 'order_type_label',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="outline" appearance="ghost">
            {row.original.order_type_label}
          </Badge>
        ),
        size: 140,
        meta: { headerTitle: 'Type' },
      },
      {
        accessorKey: 'priority',
        header: ({ column }) => <DataGridColumnHeader title="Priority" column={column} />,
        cell: ({ row }) => {
          const p = priorityBadge(row.original.priority);
          return <Badge variant={p.variant}>{p.label}</Badge>;
        },
        size: 110,
        meta: { headerTitle: 'Priority' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const s = statusBadge(row.original.status);
          return <Badge variant={s.variant} appearance="light">{s.label}</Badge>;
        },
        size: 160,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'total_qty',
        header: ({ column }) => <DataGridColumnHeader title="Total qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.total_qty),
        size: 100,
        meta: { headerTitle: 'Total qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'committed_qty',
        header: ({ column }) => <DataGridColumnHeader title="Committed" column={column} />,
        cell: ({ row }) => (
          <span className={row.original.committed_qty > 0 ? 'font-medium' : 'text-muted-foreground'}>
            {fmtInt(row.original.committed_qty)}
          </span>
        ),
        size: 110,
        meta: { headerTitle: 'Committed', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'requested_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Requested delivery" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{fmtDate(row.original.requested_delivery_date)}</span>
        ),
        size: 150,
        meta: { headerTitle: 'Requested delivery' },
      },
      {
        accessorKey: 'stock_locations',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => {
          // Plural, because one order can land in two and showing the first would be a
          // quiet lie about where the stock is going.
          const codes = row.original.stock_locations ?? [];
          if (!codes.length) return <span className="text-muted-foreground">-</span>;
          return (
            <span className="truncate" title={codes.join(', ')}>
              {codes.join(', ')}
            </span>
          );
        },
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Location' },
      },
      {
        accessorKey: 'linked_purchase_orders',
        header: ({ column }) => <DataGridColumnHeader title="Waiting on" column={column} />,
        cell: ({ row }) => {
          // The UNRESOLVED ones only. "Which of my orders is stuck behind a purchase order
          // we have not received" is the question this column exists to answer, and listing
          // the matched ones alongside would bury it.
          const waiting = (row.original.linked_purchase_orders ?? []).filter(
            (l) => !l.resolved,
          );
          if (!waiting.length) return <span className="text-muted-foreground">-</span>;
          // Capped, because a real order waits on 23 purchase orders and the full list
          // renders as a wall of text that says less than the first two plus a count. The
          // whole list is still on the title attribute for anyone who needs it.
          const numbers = waiting.map((l) => l.po_number);
          const shown = numbers.slice(0, WAITING_ON_LIMIT).join(', ');
          const hidden = numbers.length - Math.min(numbers.length, WAITING_ON_LIMIT);
          return (
            <span className="truncate" title={numbers.join(', ')}>
              {shown}
              {hidden > 0 ? (
                <span className="text-muted-foreground"> +{hidden} more</span>
              ) : null}
            </span>
          );
        },
        size: 170,
        enableSorting: false,
        meta: { headerTitle: 'Waiting on' },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.source === 'inquiry' ? 'primary' : 'secondary'} appearance="light">
            {SOURCE_LABELS[row.original.source ?? 'manual'] ?? 'Manual'}
          </Badge>
        ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Source' },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const canCreateDo = row.original.committed_qty > 0 && row.original.status !== 'cancelled';
          return (
            <div className="flex items-center justify-end gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1 px-2 text-xs"
                disabled={!canCreateDo}
                onClick={(e) => {
                  e.stopPropagation();
                  setCreatingDo(row.original);
                }}
                title={canCreateDo ? 'Create delivery order' : 'Nothing left to deliver'}
              >
                <FileText className="size-4" />
                Create DO
              </Button>
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                className="h-8 w-8"
                onClick={(e) => {
                  e.stopPropagation();
                  setEditing(row.original);
                  setFormOpen(true);
                }}
                aria-label="Edit"
              >
                <Pencil className="size-4" />
              </Button>
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                className="h-8 w-8 text-destructive"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleting(row.original);
                }}
                aria-label="Delete"
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          );
        },
        size: 200,
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
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filtersActive =
    (statusFilter ? 1 : 0) + (priorityFilter ? 1 : 0) + (sourceFilter ? 1 : 0);

  return (
    <>
      <DataGrid
        table={table}
        recordCount={data?.pagination.total || 0}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search SO or customer..."
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
                    <div>
                      <Label className="mb-1 block">Priority</Label>
                      <SearchableSelect
                        value={priorityFilter}
                        onChange={setPriorityFilter}
                        options={PRIORITY_FILTER_OPTIONS}
                        placeholder="All priorities"
                      />
                    </div>
                    <div>
                      <Label className="mb-1 block">Source</Label>
                      <SearchableSelect
                        value={sourceFilter}
                        onChange={setSourceFilter}
                        options={SOURCE_FILTER_OPTIONS}
                        placeholder="All sources"
                        clearable
                      />
                    </div>
                    {filtersActive > 0 ? (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setStatusFilter('');
                            setPriorityFilter('');
                            setSourceFilter('');
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'sales_orders_export.xlsx' }}
              onRefresh={() => void refetch()}
              isRefreshing={isFetching && !isLoading}
              primaryAction={
                <Button
                  onClick={() => {
                    setEditing(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus />
                  Add sales order
                </Button>
              }
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

      <SalesOrderFormModal
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) setEditing(null);
        }}
        editing={editing}
        onSubmit={handleSubmit}
        isPending={createMut.isPending || updateMut.isPending}
      />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        description={
          <>
            Delete sales order <span className="font-medium">{deleting?.so_number}</span> for{' '}
            {deleting?.customer_name}? This action cannot be undone.
          </>
        }
        onDelete={async () => {
          if (deleting) await deleteMut.mutateAsync(deleting.id);
        }}
        successMessage="Sales order deleted"
        onSuccess={() => setDeleting(null)}
      />

      <AlertDialog open={!!creatingDo} onOpenChange={(o) => !o && setCreatingDo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Create delivery order</AlertDialogTitle>
            <AlertDialogDescription>
              Create a delivery order from{' '}
              <span className="font-medium">{creatingDo?.so_number}</span>? Its committed quantity
              will be marked delivered and drop out of the dashboard&apos;s committed demand.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={createDoMut.isPending}
              onClick={async (e) => {
                e.preventDefault();
                if (creatingDo) {
                  await createDoMut.mutateAsync(creatingDo.id);
                  setCreatingDo(null);
                }
              }}
            >
              {createDoMut.isPending ? (
                <LoaderCircleIcon className="me-2 size-4 animate-spin" />
              ) : null}
              Create DO
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
