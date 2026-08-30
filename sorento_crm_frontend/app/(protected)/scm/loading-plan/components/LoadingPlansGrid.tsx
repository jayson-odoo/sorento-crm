'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Ban, Search, Trash2, Upload, X } from 'lucide-react';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { ConfirmActionDialog } from '../../components/ConfirmActionDialog';
import { EM_DASH, fmtDate, fmtInt, fmtOpens, fmtTrimmedDecimal } from '../../lib/format';
import { useCancelLoadingPlan, useLoadingPlanList } from '../../hooks/useFulfilment';
import {
  deleteLoadingPlan,
  type LoadingPlanRecord,
  type LoadingPlanStatus,
} from '../../services/fulfilmentService';
import { PlanContainerDialog } from './PlanContainerDialog';

/**
 * The loading plans list (R3).
 *
 * A container plan is a record now, not a browser tab's state, so this screen is the same
 * shape every other listing in the system has: a DataGrid whose whole row opens the record,
 * server-side paging and search, and ONE primary action.
 *
 * That one action is **Upload** (R4, AC-A3). Starting a plan and handing over the supplier's
 * document are the same errand - "plan this supplier's next container, here is what they sent
 * me" - so there is one button for it, and the two Upload buttons the old single page carried
 * (header card and empty state) are gone with the page.
 */

const STATUS_LABEL: Record<LoadingPlanStatus, string> = {
  planning: 'Planning',
  sent: 'Sent',
  cancelled: 'Cancelled',
};

const STATUS_VARIANT: Record<LoadingPlanStatus, 'warning' | 'primary' | 'secondary'> = {
  planning: 'warning',
  sent: 'primary',
  cancelled: 'secondary',
};

/** The filter chip's own vocabulary. "Active" is the default because a cancelled plan is a
 *  decision already made, and a list that opens on it hides the work in front of somebody. */
const STATUS_OPTIONS = [
  { value: 'active', label: 'Active (planning and sent)' },
  { value: 'planning', label: 'Planning' },
  { value: 'sent', label: 'Sent' },
  { value: 'cancelled', label: 'Cancelled' },
];

export function LoadingPlansGrid() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'started_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [status, setStatus] = useState<LoadingPlanStatus | 'active'>('active');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [cancelling, setCancelling] = useState<LoadingPlanRecord | null>(null);
  const [deleting, setDeleting] = useState<LoadingPlanRecord | null>(null);

  const list = useLoadingPlanList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status,
  });
  const cancel = useCancelLoadingPlan();

  const columns = useMemo<ColumnDef<LoadingPlanRecord>[]>(
    () => [
      {
        id: 'started_at',
        accessorFn: (row) => row.started_at,
        header: ({ column }) => <DataGridColumnHeader title="Started" visibility column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {formatDateTimeInMalaysia(row.original.started_at)}
          </span>
        ),
        size: 170,
        enableSorting: true,
        meta: { headerTitle: 'Started', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'supplier_name',
        accessorFn: (row) => row.supplier_name ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Supplier" visibility column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.supplier_name ?? ''}>
            {row.original.supplier_name ?? EM_DASH}
          </span>
        ),
        size: 260,
        enableSorting: true,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'plan_horizon_date',
        accessorFn: (row) => row.plan_horizon_date ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="SO cut-off" visibility column={column} />
        ),
        cell: ({ row }) =>
          row.original.plan_horizon_date ? (
            <span className="tabular-nums">{fmtDate(row.original.plan_horizon_date)}</span>
          ) : (
            <span className="text-muted-foreground" title="Every open order counted">
              {EM_DASH}
            </span>
          ),
        size: 130,
        enableSorting: true,
        meta: { headerTitle: 'SO cut-off', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'document_label',
        accessorFn: (row) => row.document_label,
        header: ({ column }) => <DataGridColumnHeader title="Document" visibility column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.document_label}>
            {row.original.document_label}
          </span>
        ),
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Document', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'to_request_qty',
        accessorFn: (row) => row.to_request_qty ?? -1,
        header: ({ column }) => (
          <DataGridColumnHeader title="To request" visibility column={column} />
        ),
        // Two lines, because the buyer asks two questions of one figure: how many pieces, and
        // whether it fits a container. A plan nobody has opened yet has neither, and says so
        // rather than printing a zero that reads as "nothing to ask for".
        cell: ({ row }) =>
          row.original.to_request_qty === null ? (
            <span className="text-muted-foreground" title="Not built yet">
              {EM_DASH}
            </span>
          ) : (
            <div className="flex flex-col text-end">
              <span className="tabular-nums">{fmtInt(row.original.to_request_qty)}</span>
              {row.original.to_request_cbm !== null ? (
                <span className="text-2xs text-muted-foreground tabular-nums">
                  est. {fmtTrimmedDecimal(row.original.to_request_cbm, 1)} cbm
                </span>
              ) : null}
            </div>
          ),
        size: 130,
        enableSorting: true,
        meta: { headerTitle: 'To request', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'sent_at',
        accessorFn: (row) => row.sent_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Sent" visibility column={column} />,
        cell: ({ row }) =>
          row.original.sent_at ? (
            <span className="block truncate tabular-nums" title={row.original.sent_channel ?? ''}>
              {row.original.sent_channel === 'chat' ? 'Chat' : 'Email'}{' '}
              {formatDateTimeInMalaysia(row.original.sent_at)}
            </span>
          ) : (
            <span className="text-muted-foreground">{EM_DASH}</span>
          ),
        size: 170,
        enableSorting: true,
        meta: { headerTitle: 'Sent', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'opened_at',
        accessorFn: (row) => row.last_opened_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Opened" visibility column={column} />,
        // Two facts, one cell (AC-C8): how many times the supplier opened the link, and when
        // they last did. A plan they have never opened says so in words - a dash there reads
        // as "we do not know", and since S3 we do.
        cell: ({ row }) =>
          row.original.open_count > 0 ? (
            <div className="flex flex-col">
              <span className="truncate tabular-nums" title={fmtOpens(row.original.open_count, row.original.last_opened_at)}>
                {row.original.last_opened_at
                  ? formatDateTimeInMalaysia(row.original.last_opened_at)
                  : EM_DASH}
              </span>
              <span className="text-2xs text-muted-foreground">
                {fmtInt(row.original.open_count)}{' '}
                {row.original.open_count === 1 ? 'time' : 'times'}
              </span>
            </div>
          ) : (
            <span className="text-2xs text-muted-foreground">Not opened yet</span>
          ),
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'Opened', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'status',
        accessorFn: (row) => row.status,
        header: ({ column }) => <DataGridColumnHeader title="Status" visibility column={column} />,
        cell: ({ row }) => (
          <Badge variant={STATUS_VARIANT[row.original.status]} appearance="light" size="sm">
            {STATUS_LABEL[row.original.status]}
          </Badge>
        ),
        size: 110,
        enableSorting: true,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-5 w-16" /> },
      },
      {
        id: 'actions',
        header: '',
        // `stopPropagation` on both: the row is a link to the record, and a click meant for
        // Cancel that also navigates leaves the confirm dialog on a screen nobody chose.
        cell: ({ row }) => {
          const plan = row.original;
          const sent = !!plan.sent_at;
          return (
            <div className="flex items-center justify-end gap-1">
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                className="h-8 w-8"
                disabled={plan.status === 'cancelled'}
                title={plan.status === 'cancelled' ? 'Already cancelled' : 'Cancel this plan'}
                onClick={(e) => {
                  e.stopPropagation();
                  setCancelling(plan);
                }}
                aria-label="Cancel plan"
              >
                <Ban className="size-4" />
              </Button>
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                className="h-8 w-8 text-destructive"
                disabled={sent}
                title={sent ? 'Sent plans are cancelled, not deleted' : 'Delete this plan'}
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleting(plan);
                }}
                aria-label="Delete plan"
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          );
        },
        size: 90,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    [],
  );

  const rows = list.data?.data ?? [];
  const total = list.data?.total ?? 0;

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
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

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => setUploadOpen(true)} data-testid="open-plan-container">
      <Upload className="size-4" />
      Upload
    </Button>
  );

  return (
    <>
      <DataGrid
        table={table}
        recordCount={total}
        isLoading={list.isLoading}
        emptyMessage={
          searchQuery || status !== 'active'
            ? 'No plan matches this search and filter.'
            : 'No container plans yet. Upload a supplier stock list or proforma invoice to start one.'
        }
        onRowClick={(row) => router.push(`/scm/loading-plan/${row.id}`)}
        tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
        listingKey="scm.dashboard.view::loading-plans"
        emptyAction={listPrimaryAction}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              primaryAction={listPrimaryAction}
              filters={{
                kind: 'custom',
                active: status !== 'active',
                activeCount: status !== 'active' ? 1 : 0,
                activeSummary:
                  status !== 'active'
                    ? {
                        label: `Status: ${STATUS_LABEL[status]}`,
                        onClear: () => setStatus('active'),
                      }
                    : undefined,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="plan-status-filter" className="mb-1 block">
                        Status
                      </Label>
                      <SearchableSelect
                        id="plan-status-filter"
                        value={status}
                        onChange={(v) => {
                          setStatus((v || 'active') as LoadingPlanStatus | 'active');
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                        options={STATUS_OPTIONS}
                        placeholder="Active (planning and sent)"
                      />
                    </div>
                  </div>
                ),
              }}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search plans by supplier"
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setPagination((p) => ({ ...p, pageIndex: 0 }));
                    }}
                    className="w-full ps-9 sm:w-64"
                  />
                  {searchQuery.length > 0 ? (
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
              onRefresh={() => void list.refetch()}
              isRefreshing={list.isFetching}
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

      <PlanContainerDialog open={uploadOpen} onOpenChange={setUploadOpen} />

      <ConfirmActionDialog
        open={!!cancelling}
        onOpenChange={(next) => !next && setCancelling(null)}
        title="Cancel this plan?"
        description="The supplier link stops working. The plan stays on the list under the Cancelled filter."
        confirmLabel="Cancel plan"
        isBusy={cancel.isPending}
        onConfirm={() => {
          if (!cancelling) return;
          cancel.mutate(cancelling.id, { onSuccess: () => setCancelling(null) });
        }}
      />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Delete this plan?"
        description={
          <>
            {deleting?.supplier_name ?? 'This plan'}, started{' '}
            {deleting ? formatDateTimeInMalaysia(deleting.started_at) : ''}. The plan and the
            quantities typed on it are removed. This cannot be undone.
          </>
        }
        successMessage="Plan deleted"
        onDelete={async () => {
          if (deleting) await deleteLoadingPlan(deleting.id);
        }}
        onSuccess={() => {
          setDeleting(null);
          void list.refetch();
        }}
      />
    </>
  );
}

export default LoadingPlansGrid;
