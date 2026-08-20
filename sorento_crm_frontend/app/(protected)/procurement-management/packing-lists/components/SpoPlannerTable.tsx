'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Check, Download, FileText, Info, LoaderCircle, RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useCreateSpo,
  useDownloadSpoWorksheet,
  useSpoSuggestion,
} from '@/app/(protected)/scm/hooks/useFulfilment';
import type {
  SpoConfirmLine,
  SpoLocationOption,
  SpoPoTake,
  SpoSuggestionLine,
} from '@/app/(protected)/scm/services/fulfilmentService';

/**
 * The packing-list-to-SPO planner (`PLAN-scm-proforma-to-spo.md`'s second amendment, captain
 * 21 Aug 00:40): "instead of looking at SO for loading plan, now I look at PO" - one row per
 * PACKED product, the same loading-plan-style ranked TABLE `ContainerRequestSection` renders
 * for the container request, not the first cut's checkbox list. Two questions per row, both
 * answered rather than asked:
 *
 *   - Which PO covers this, earliest first - `po_covered_qty` with its per-PO breakdown
 *     (`po_takes`) behind a drill, the uncovered remainder becoming the editable SPO qty.
 *   - Which warehouse the SPO should land at - `location_options`, ranked by Fulfilment
 *     Priority (project earlier delivery first, then retail), with the outstanding SO / on
 *     hand / incoming SPO / after-figure behind a drill; `suggested_warehouse_id` pre-selects
 *     the top one.
 *
 * No checkbox column, on purpose, mirroring `ContainerRequestSection.renderQtyCell`'s own
 * rule: the SPO qty input IS the include/exclude decision - edited to 0, a line stays on
 * screen but drops off the confirm, exactly the way a container-request row does.
 */

const EM_DASH = '-';
const intFmt = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return intFmt.format(value);
}
function fmtSigned(value: number): string {
  const s = intFmt.format(Math.abs(value));
  return value < 0 ? `-${s}` : s;
}

export function SpoPlannerTable({ shipmentId }: { shipmentId: string }) {
  const suggestion = useSpoSuggestion(shipmentId);
  const create = useCreateSpo(shipmentId);
  const worksheet = useDownloadSpoWorksheet(shipmentId);

  type LineState = { qty: number; warehouseId: string | null };
  const [state, setState] = useState<Record<string, LineState>>({});

  useEffect(() => {
    // A fresh suggestion replaces whatever she had edited - "refresh" looks again, it does
    // not keep edits made against a now-stale suggestion (same rule ContainerRequestSection
    // applies to its own qty overrides).
    const next: Record<string, LineState> = {};
    for (const ln of suggestion.data?.lines ?? []) {
      next[ln.shipment_line_id] = {
        qty: ln.suggested_qty,
        warehouseId: ln.cannot_convert ? null : ln.suggested_warehouse_id,
      };
    }
    setState(next);
  }, [suggestion.data]);

  const lines = useMemo(() => suggestion.data?.lines ?? [], [suggestion.data]);
  const alreadyConverted = suggestion.data?.already_converted ?? false;

  const qtyFor = (ln: SpoSuggestionLine) => state[ln.shipment_line_id]?.qty ?? ln.suggested_qty;
  const warehouseFor = (ln: SpoSuggestionLine) =>
    state[ln.shipment_line_id]?.warehouseId ?? ln.suggested_warehouse_id;

  const confirmLines: SpoConfirmLine[] = useMemo(
    () =>
      lines.map((ln) => {
        const qty = Math.max(qtyFor(ln), 0);
        const include = !ln.cannot_convert && qty > 0;
        return {
          shipment_line_id: ln.shipment_line_id,
          qty: include ? qty : 0,
          include,
          warehouse_id: include ? warehouseFor(ln) : null,
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lines, state],
  );
  const includedCount = confirmLines.filter((l) => l.include).length;

  const renderQtyCell = (ln: SpoSuggestionLine) => (
    <Input
      type="number"
      min={0}
      step={1}
      className="h-8 w-24 tabular-nums"
      value={qtyFor(ln)}
      disabled={ln.cannot_convert}
      title="packed - PO covered - on hand - incoming SPO, floored at 0"
      onChange={(e) => {
        const next = Math.max(0, Number(e.target.value) || 0);
        setState((prev) => ({
          ...prev,
          [ln.shipment_line_id]: { qty: next, warehouseId: prev[ln.shipment_line_id]?.warehouseId ?? ln.suggested_warehouse_id },
        }));
      }}
    />
  );

  const renderLocationCell = (ln: SpoSuggestionLine) => {
    const qty = qtyFor(ln);
    const disabled = ln.cannot_convert || qty <= 0 || ln.location_options.length === 0;
    return (
      <div className="flex items-center gap-1">
        <div className="w-40">
          <SearchableSelect
            size="sm"
            value={warehouseFor(ln) ?? ''}
            disabled={disabled}
            options={ln.location_options.map((o) => ({
              value: o.warehouse_id,
              label: o.warehouse_code ?? o.warehouse_id,
            }))}
            onChange={(v) =>
              setState((prev) => ({
                ...prev,
                [ln.shipment_line_id]: { qty: prev[ln.shipment_line_id]?.qty ?? ln.suggested_qty, warehouseId: v || null },
              }))
            }
            placeholder={ln.location_options.length ? 'Choose' : 'No location'}
          />
        </div>
        {ln.location_options.length > 0 ? (
          <LocationOptionsDrillPopover
            title={ln.item_code ?? ln.product_name ?? 'This product'}
            options={ln.location_options}
            qty={qty}
            selectedWarehouseId={warehouseFor(ln)}
          />
        ) : null}
      </div>
    );
  };

  const columns = useMemo<ColumnDef<SpoSuggestionLine>[]>(
    () => [
      {
        id: 'product',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          return (
            <div className={ln.cannot_convert ? 'flex min-w-0 flex-col opacity-60' : 'flex min-w-0 flex-col'}>
              <span className="truncate font-medium" title={ln.item_code ?? ''}>
                {ln.item_code ?? EM_DASH}
              </span>
              <span className="truncate text-2xs text-muted-foreground" title={ln.product_name ?? ''}>
                {ln.product_name ?? EM_DASH}
                {ln.supplier_name ? ` · ${ln.supplier_name}` : ''}
              </span>
              {ln.reason ? (
                <span className="truncate text-2xs text-muted-foreground" title={ln.reason}>
                  {ln.reason}
                </span>
              ) : null}
            </div>
          );
        },
        size: 240,
        enableSorting: false,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'packed_qty',
        header: ({ column }) => <DataGridColumnHeader title="Packed" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.packed_qty)}</span>,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Packed' },
      },
      {
        id: 'po_covered',
        header: ({ column }) => <DataGridColumnHeader title="PO covers" column={column} />,
        cell: ({ row }) => {
          const ln = row.original;
          if (!ln.po_takes.length) {
            return <span className="tabular-nums text-muted-foreground">{fmtInt(0)}</span>;
          }
          return (
            <PoTakesDrillPopover
              title={ln.item_code ?? ln.product_name ?? 'This product'}
              takes={ln.po_takes}
              total={ln.po_covered_qty}
            />
          );
        },
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'PO covers' },
      },
      {
        id: 'on_hand',
        header: ({ column }) => <DataGridColumnHeader title="On hand" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.on_hand)}</span>,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'On hand' },
      },
      {
        id: 'incoming_spo',
        header: ({ column }) => <DataGridColumnHeader title="Incoming SPO" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{fmtInt(row.original.incoming_spo)}</span>,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Incoming SPO' },
      },
      {
        id: 'suggested_qty',
        header: ({ column }) => <DataGridColumnHeader title="SPO qty" column={column} />,
        cell: ({ row }) => renderQtyCell(row.original),
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'SPO qty' },
      },
      {
        id: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => renderLocationCell(row.original),
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Location' },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state],
  );

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.shipment_line_id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (suggestion.isLoading) {
    return (
      <Card className="p-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="mt-3 h-40 w-full rounded-lg" />
      </Card>
    );
  }

  if (suggestion.isError) {
    return (
      <Card className="flex flex-col items-center gap-3 p-8 text-center">
        <p className="text-sm font-medium text-destructive">
          {suggestion.error instanceof Error
            ? suggestion.error.message
            : 'Failed to load the SPO planner.'}
        </p>
        <Button variant="outline" size="sm" onClick={() => suggestion.refetch()}>
          <RefreshCw className="size-4" />
          Try again
        </Button>
      </Card>
    );
  }

  if (alreadyConverted) {
    return (
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">SPO already created</h3>
            <p className="text-2xs text-muted-foreground">
              This packing list has already gone through Create SPO.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => worksheet.mutate(suggestion.data?.shipment_number ?? 'container')}
            disabled={worksheet.isPending}
          >
            {worksheet.isPending ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <Download className="size-4" aria-hidden />
            )}
            Download worksheet
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          {(suggestion.data?.existing_spos ?? []).map((spo) => (
            <Badge key={spo.purchase_order_id} variant="secondary" size="sm">
              {spo.po_number ?? EM_DASH}
              {spo.supplier_name ? ` · ${spo.supplier_name}` : ''}
            </Badge>
          ))}
        </div>
      </Card>
    );
  }

  if (!lines.length) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm font-medium">This container has no line we hold a product for.</p>
      </Card>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={lines.length}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="This container has no line we hold a product for."
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">SPO planner</h3>
            <p className="text-2xs text-muted-foreground">
              {suggestion.data?.shipment_status === 'draft'
                ? "Draft shipment - based on this draft's own packed quantities, not a real packing list yet."
                : 'What is packed, what an open PO already covers, and where the rest should land.'}
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => create.mutate(confirmLines)}
            disabled={!includedCount || create.isPending}
          >
            {create.isPending ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            ) : (
              <Check className="size-4" aria-hidden />
            )}
            Create SPO
          </Button>
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter className="justify-end text-2xs text-muted-foreground">
          {includedCount} of {lines.length} line{lines.length === 1 ? '' : 's'} will create an
          SPO
        </CardFooter>
      </Card>
    </DataGrid>
  );
}

function PoTakesDrillPopover({
  title,
  takes,
  total,
}: {
  title: string;
  takes: SpoPoTake[];
  total: number;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-sm tabular-nums underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          title="Which PO covers this, earliest first"
        >
          {fmtInt(total)}
          <Info className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 space-y-2 p-3">
        <p className="text-xs font-medium">{title} - covered by PO</p>
        <div className="space-y-1">
          {takes.map((t) => (
            <div key={t.po_line_id} className="flex items-center justify-between text-xs">
              <span className="truncate" title={t.po_number}>
                {t.po_number}
              </span>
              <span className="tabular-nums">{fmtInt(t.qty)}</span>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function LocationOptionsDrillPopover({
  title,
  options,
  qty,
  selectedWarehouseId,
}: {
  title: string;
  options: SpoLocationOption[];
  qty: number;
  selectedWarehouseId: string | null;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={`View candidate locations for ${title}`}
        >
          <Info className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 space-y-2 p-3">
        <p className="text-xs font-medium">{title} - candidate locations</p>
        <p className="text-2xs text-muted-foreground">
          Ranked by Fulfilment Priority (project earlier delivery first, then retail).
        </p>
        <div className="space-y-2">
          {options.map((o) => (
            <div
              key={o.warehouse_id}
              className={
                o.warehouse_id === selectedWarehouseId
                  ? 'rounded-md border border-primary/40 bg-primary/5 px-2 py-1.5'
                  : 'rounded-md border px-2 py-1.5'
              }
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium" title={o.warehouse_code ?? undefined}>
                  {o.warehouse_code ?? EM_DASH}
                </span>
                {o.rank_score === null ? (
                  <span className="text-2xs text-muted-foreground">No open demand</span>
                ) : null}
              </div>
              <div className="mt-1 grid grid-cols-4 gap-1 text-2xs text-muted-foreground">
                <span>SO {fmtInt(o.outstanding_so)}</span>
                <span>On hand {fmtInt(o.on_hand)}</span>
                <span>SPO {fmtInt(o.incoming_spo)}</span>
                <span title="available now">Now {fmtSigned(o.available)}</span>
              </div>
              <div className="mt-0.5 text-2xs">
                After this SPO: <span className="tabular-nums font-medium">{fmtSigned(o.available + qty)}</span>
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default SpoPlannerTable;
