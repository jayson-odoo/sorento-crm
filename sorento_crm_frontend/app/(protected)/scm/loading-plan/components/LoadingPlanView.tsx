'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Container, LoaderCircle, PackageOpen, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtInt } from '../../lib/format';
import {
  useBuildLoadingPlan,
  useContainerSizes,
  useFulfilmentSuppliers,
  useLoadingPlans,
  useRerunLoadingPlan,
  useStockListApplied,
  useSupplierStock,
  useUnfinishedStock,
} from '../../hooks/useFulfilment';
import type {
  DeferralReason,
  LoadingLineStatus,
  LoadingPlan,
  LoadingPlanLine,
} from '../../services/fulfilmentService';
import { StockListUploadDialog } from './StockListUploadDialog';
import { SupplierNoticePanel } from './SupplierNoticePanel';
import { RankFactorsPopover } from './RankFactorsPopover';

/**
 * Ms Tee's screen: what goes on the next container from one supplier.
 *
 * The order of the page IS the journey. Pick the supplier, see what they are holding and
 * when they told us, say how many containers, read the fill. Nothing is asked that can be
 * derived: the volume, the outstanding quantities, the ranking and the cut line all come out
 * of what is already on file, and the only two decisions are the supplier and the container
 * count.
 *
 * Deferred lines are shown with the winners rather than hidden behind a filter, because the
 * question this screen answers most often is not "what is on the container" but "why is my
 * line not on it".
 */

const STATUS_LABELS: Record<LoadingLineStatus, string> = {
  allocated: 'On the container',
  partial: 'Part loaded',
  deferred: 'Not loaded',
  unmeasured: 'No volume',
};

/** Mapped onto the shared palette rather than inventing a colour vocabulary. */
const STATUS_TONE: Record<LoadingLineStatus, string> = {
  allocated: 'fulfilled',
  partial: 'partially_delivered',
  deferred: 'cancelled',
  unmeasured: 'pending',
};

const REASON_LABELS: Record<DeferralReason, string> = {
  over_capacity: 'Container full',
  no_packed_stock: 'Not packed yet',
  not_in_stock_list: 'Not on the stock list',
  no_volume_on_file: 'No volume on file',
};

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border px-3 py-2">
      <div className="text-lg font-semibold tabular-nums leading-tight">{value}</div>
      <div className="text-2xs text-muted-foreground">{label}</div>
      {hint ? <div className="text-2xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

/** A load that rounds to 0% is not an empty container, and saying "0% full" beside a planned
 *  volume reads as nothing planned. */
function fillLabel(rate: number): string {
  const pct = Math.round(rate * 100);
  if (rate > 0 && pct === 0) return 'under 1% full';
  return `${pct}% full`;
}

function cbm(value: number | null | undefined): string {
  return value === null || value === undefined ? EM_DASH : `${value.toLocaleString()} cbm`;
}

export function LoadingPlanView() {
  const [supplierId, setSupplierId] = useState('');
  const [containerType, setContainerType] = useState('');
  const [containerCount, setContainerCount] = useState(1);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [planId, setPlanId] = useState<string | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);

  const suppliers = useFulfilmentSuppliers();
  const sizes = useContainerSizes();
  const stock = useSupplierStock(supplierId || null);
  const unfinished = useUnfinishedStock(supplierId || null);
  const plans = useLoadingPlans(supplierId || null);
  const build = useBuildLoadingPlan();
  const rerun = useRerunLoadingPlan();
  const invalidateSupplier = useStockListApplied();

  // The default container is the tenant's, not this component's: guessing 40HQ in the browser
  // would disagree with the server the moment somebody changes the configured default.
  useEffect(() => {
    if (containerType || !sizes.data?.length) return;
    setContainerType((sizes.data.find((s) => s.is_default) ?? sizes.data[0]).code);
  }, [sizes.data, containerType]);

  useEffect(() => {
    setPlanId(null);
  }, [supplierId]);

  const supplierName =
    suppliers.data?.find((s) => s.value === supplierId)?.label ?? 'this supplier';

  const plan: LoadingPlan | null =
    (build.data && build.data.supplier_id === supplierId ? build.data : null) ??
    (rerun.data && rerun.data.supplier_id === supplierId ? rerun.data : null) ??
    (planId ? plans.data?.find((p) => p.id === planId) ?? null : null);

  const lines = useMemo<LoadingPlanLine[]>(() => plan?.lines ?? [], [plan]);

  const columns = useMemo<ColumnDef<LoadingPlanLine>[]>(
    () => [
      {
        accessorKey: 'rank',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.rank ?? EM_DASH}</span>,
        size: 60,
        meta: { headerTitle: '#' },
      },
      {
        accessorKey: 'item_code',
        header: ({ column }) => <DataGridColumnHeader title="Item" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate font-medium" title={row.original.item_code ?? ''}>
              {row.original.item_code ?? EM_DASH}
            </span>
            <span className="text-2xs text-muted-foreground">{row.original.po_number}</span>
          </div>
        ),
        size: 190,
        meta: { headerTitle: 'Item' },
      },
      {
        accessorKey: 'qty_outstanding',
        header: ({ column }) => <DataGridColumnHeader title="Outstanding" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">{fmtInt(row.original.qty_outstanding)}</span>
        ),
        size: 110,
        meta: { headerTitle: 'Outstanding' },
      },
      {
        accessorKey: 'qty_packed_available',
        header: ({ column }) => <DataGridColumnHeader title="Packed" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.qty_packed_available === null
              ? EM_DASH
              : fmtInt(row.original.qty_packed_available)}
          </span>
        ),
        size: 100,
        meta: { headerTitle: 'Packed' },
      },
      {
        accessorKey: 'qty_planned',
        header: ({ column }) => <DataGridColumnHeader title="Loading" column={column} />,
        cell: ({ row }) => (
          <span className="tabular-nums font-medium">{fmtInt(row.original.qty_planned)}</span>
        ),
        size: 100,
        meta: { headerTitle: 'Loading' },
      },
      {
        accessorKey: 'cbm_planned',
        header: ({ column }) => <DataGridColumnHeader title="Volume" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="tabular-nums">{cbm(row.original.cbm_planned)}</span>
            {/* Where the figure came from is worth as much as the figure: a catalogue
                dimension is our guess, a supplier figure is theirs. */}
            {row.original.volume_basis ? (
              <span className="text-2xs text-muted-foreground">
                {row.original.volume_basis === 'supplier' ? 'supplier' : 'from dimensions'}
              </span>
            ) : null}
          </div>
        ),
        size: 130,
        meta: { headerTitle: 'Volume' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col gap-1">
            <span
              className={cn(STATUS_PILL_BASE, statusPillClass(STATUS_TONE[row.original.status]))}
            >
              {STATUS_LABELS[row.original.status]}
            </span>
            {row.original.deferral_reason ? (
              <span className="text-2xs text-muted-foreground">
                {REASON_LABELS[row.original.deferral_reason]}
              </span>
            ) : null}
          </div>
        ),
        size: 150,
        meta: { headerTitle: 'Outcome' },
      },
      {
        id: 'why',
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        cell: ({ row }) => <RankFactorsPopover line={row.original} />,
        size: 110,
        meta: { headerTitle: 'Rank' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const holding = stock.data?.rows ?? [];
  const packedItems = holding.filter((r) => r.qty_packed > 0).length;
  const loadable = holding.reduce(
    (sum, r) => sum + (r.cbm_per_unit === null ? 0 : r.cbm_per_unit * r.qty_packed),
    0,
  );

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 grow">
            <Label htmlFor="loading-plan-supplier" className="text-xs">
              Supplier
            </Label>
            <SearchableSelect
              id="loading-plan-supplier"
              value={supplierId}
              onChange={setSupplierId}
              options={suppliers.data ?? []}
              placeholder={suppliers.isLoading ? 'Loading suppliers...' : 'Choose a supplier'}
              className="mt-1 w-full sm:w-80"
            />
          </div>
          <Button
            variant="outline"
            onClick={() => setUploadOpen(true)}
            disabled={!supplierId}
            data-testid="open-stock-upload"
          >
            <Upload className="size-4" />
            Upload stock list
          </Button>
        </div>
      </Card>

      {!supplierId ? (
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Container className="size-5" />
          </span>
          <p className="text-sm font-medium">Choose a supplier to plan a container.</p>
          <p className="text-2xs text-muted-foreground">
            The plan is built from their stock list and your open purchase orders with them.
          </p>
        </Card>
      ) : (
        <>
          <Card className="p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold">What {supplierName} is holding</h3>
                <p className="text-2xs text-muted-foreground">
                  {stock.isLoading
                    ? 'Loading...'
                    : stock.data?.as_of
                      ? `As they told us on ${formatDateInMalaysia(stock.data.as_of)}`
                      : 'No stock list uploaded yet'}
                </p>
              </div>
            </div>

            {stock.isLoading ? (
              <Skeleton className="mt-3 h-16 w-full rounded-lg" />
            ) : holding.length === 0 ? (
              <div className="mt-3 rounded-lg border border-dashed border-border p-6 text-center">
                <PackageOpen className="mx-auto size-5 text-muted-foreground" />
                <p className="mt-2 text-sm font-medium">No stock list for {supplierName} yet.</p>
                <p className="text-2xs text-muted-foreground">
                  Upload the list they sent and the container plans itself from it.
                </p>
                <Button className="mt-3" size="sm" onClick={() => setUploadOpen(true)}>
                  <Upload className="size-4" />
                  Upload stock list
                </Button>
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Tile label="Items packed" value={fmtInt(packedItems)} />
                <Tile
                  label="Units packed"
                  value={fmtInt(holding.reduce((s, r) => s + r.qty_packed, 0))}
                />
                <Tile label="Loadable" value={cbm(Math.round(loadable * 100) / 100)} />
                <Tile
                  label="Unfinished"
                  value={fmtInt(holding.reduce((s, r) => s + r.qty_unfinished, 0))}
                  hint={unfinished.data?.length ? `${unfinished.data.length} items` : undefined}
                />
              </div>
            )}
          </Card>

          <Card className="p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div>
                <Label htmlFor="container-type" className="text-xs">
                  Container
                </Label>
                <SearchableSelect
                  id="container-type"
                  value={containerType}
                  onChange={(next) => {
                    setContainerType(next);
                    if (plan) rerun.mutate({ id: plan.id, container_type: next });
                  }}
                  options={(sizes.data ?? []).map((s) => ({
                    value: s.code,
                    label: `${s.code} (${s.cbm} cbm)`,
                  }))}
                  className="mt-1 w-48"
                />
              </div>
              <div>
                <Label htmlFor="container-count" className="text-xs">
                  How many
                </Label>
                <Input
                  id="container-count"
                  type="number"
                  min={1}
                  className="mt-1 w-24"
                  value={containerCount}
                  onChange={(e) => {
                    const next = Math.max(1, Number(e.target.value) || 1);
                    setContainerCount(next);
                    // AC-E6: a different count re-runs the same plan, with no re-upload and
                    // without leaving a second plan behind for one decision.
                    if (plan) rerun.mutate({ id: plan.id, container_count: next });
                  }}
                />
              </div>
              <Button
                onClick={() =>
                  build.mutate({
                    supplier_id: supplierId,
                    container_count: containerCount,
                    container_type: containerType || null,
                  })
                }
                disabled={build.isPending || rerun.isPending}
              >
                {build.isPending || rerun.isPending ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Container className="size-4" />
                )}
                {plan ? 'Plan again' : 'Plan containers'}
              </Button>
            </div>

            {plan ? (
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
                <Tile label="Capacity" value={cbm(plan.capacity_cbm)} />
                <Tile
                  label="Planned"
                  value={cbm(plan.planned_cbm)}
                  hint={plan.fill_rate === null ? undefined : fillLabel(plan.fill_rate)}
                />
                <Tile label="Lines" value={fmtInt(plan.line_count)} />
                <Tile label="Cut" value={fmtInt(plan.deferred_count)} hint="lines left behind" />
                <Tile label="No volume" value={fmtInt(plan.unmeasured_count)} />
              </div>
            ) : null}
          </Card>

          {plan ? (
            <DataGrid
              table={table}
              recordCount={lines.length}
              tableLayout={{ width: 'fixed', columnsResizable: true }}
              emptyMessage="No open purchase-order line at this supplier, so there is nothing to load."
            >
              <Card>
                <CardHeader className="py-3">
                  <h3 className="text-sm font-semibold">
                    Loading plan
                    {plan.computed_at ? (
                      <span className="ms-2 text-2xs font-normal text-muted-foreground">
                        {plan.container_count} x {plan.container_type ?? 'container'}
                      </span>
                    ) : null}
                  </h3>
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
          ) : null}

          {/* Step 3 of Ms Tee's journey. Rendered whenever there is a plan, and empty until
              something has been sent, so "nothing has gone out yet" is a state she can see
              rather than infer from an absent section. */}
          {plan ? <SupplierNoticePanel planId={plan.id} /> : null}

          {unfinished.data?.length ? (
            <Card className="p-4">
              <h3 className="text-sm font-semibold">Waiting on production</h3>
              <p className="text-2xs text-muted-foreground">
                Held unfinished, so it cannot be loaded until the supplier finishes it.
              </p>
              <ul className="mt-2 divide-y divide-border">
                {unfinished.data.map((row) => (
                  <li key={row.item_code} className="flex items-center justify-between py-1.5">
                    <span className="truncate text-xs" title={row.item_code}>
                      {row.item_code}
                      {row.product_name ? (
                        <span className="ms-2 text-muted-foreground">{row.product_name}</span>
                      ) : null}
                    </span>
                    <span className="tabular-nums text-xs">{fmtInt(row.qty_unfinished)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </>
      )}

      {supplierId ? (
        <StockListUploadDialog
          open={uploadOpen}
          onOpenChange={setUploadOpen}
          supplierId={supplierId}
          supplierName={supplierName}
          onApplied={() => invalidateSupplier(supplierId)}
        />
      ) : null}
    </div>
  );
}

export default LoadingPlanView;
