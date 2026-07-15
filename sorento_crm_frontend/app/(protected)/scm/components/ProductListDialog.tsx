'use client';

import { useEffect, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  PackageOpen,
  Search,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtDecimal, fmtDoc, fmtInt, fmtMoney, fmtSigned } from '../lib/format';
import { useScmProducts } from '../hooks/useScmDashboard';
import type { ScmFilters } from '../services/scmDashboardService';
import type { HealthState } from '../types/scm.types';
import {
  ClassChip,
  CommittedStockoutPill,
  DaysOfCoverInfo,
  NetPositionInfo,
  StateChip,
} from './HealthIndicators';

const PAGE_SIZE = 50;

/** Drill-down target scope (health state and/or a single warehouse). */
export interface ProductDrillTarget {
  status?: HealthState | null;
  warehouse?: string | null;
}

/**
 * Unified read-only drill-down popup. One component backs every "what's behind
 * this number?" surface on the dashboard — roll-up stat tiles, warehouse tile
 * counts, and the warehouse "view products" affordance. Callers pass the base
 * `filters` + a `target` scope; the popup owns its own server-side search / sort
 * / pagination (these sets can be thousands of rows). No mutations, no UUIDs.
 */
export interface ProductListDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Current dashboard filters — scope the drill-down set. */
  filters: ScmFilters;
  /** The scope this popup drills into (health state / warehouse). Null = closed. */
  target: ProductDrillTarget | null;
  /** When set, renders a "View in list" action that switches to the Product
   *  perspective pre-filtered (and closes the dialog). */
  onViewInList?: () => void;
}

type SortDir = 'asc' | 'desc';
interface SortState {
  field: string;
  dir: SortDir;
}

/** Columns mirror the Product-perspective grid order + alignment. Every data
 *  column is server-sortable (the BE allow-lists each field; Value/Demand sort by
 *  class letter A<B<C / X<Y<Z with unknown last). */
const COLUMNS: {
  id: string;
  label: string;
  align: 'left' | 'right' | 'center';
  info?: boolean;
  docInfo?: boolean;
  sortable?: boolean;
}[] = [
  { id: 'sku', label: 'SKU', align: 'left', sortable: true },
  { id: 'status', label: 'Status', align: 'left', sortable: true },
  { id: 'net_position', label: 'Net position', align: 'right', info: true, sortable: true },
  { id: 'on_hand', label: 'On hand', align: 'right', sortable: true },
  { id: 'on_order', label: 'On order', align: 'right', sortable: true },
  { id: 'committed', label: 'Committed', align: 'right', sortable: true },
  { id: 'stock_valuation', label: 'Stock valuation', align: 'right', sortable: true },
  { id: 'avg_daily_demand', label: 'Avg daily demand', align: 'right', sortable: true },
  { id: 'days_of_cover', label: 'Days of cover', align: 'right', docInfo: true, sortable: true },
  // Plain-language headers; underlying fields stay abc_class/xyz_class.
  { id: 'abc_class', label: 'Value', align: 'center', sortable: true },
  { id: 'xyz_class', label: 'Demand', align: 'center', sortable: true },
];

export function ProductListDialog({
  open,
  onOpenChange,
  title,
  filters,
  target,
  onViewInList,
}: ProductListDialogProps) {
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [sort, setSort] = useState<SortState | null>(null);
  const [page, setPage] = useState(1);

  // Reset all popup query state whenever the drill scope changes / reopens.
  const scopeKey = `${target?.status ?? ''}|${target?.warehouse ?? ''}|${open}`;
  useEffect(() => {
    setSearch('');
    setDebounced('');
    setSort(null);
    setPage(1);
  }, [scopeKey]);

  // Debounce the search input (server-side query).
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Search / sort changes reset to the first page.
  useEffect(() => {
    setPage(1);
  }, [debounced, sort]);

  // Health (incl. `overstock`, computed from days-of-cover server-side) + ABC/XYZ
  // filtering + pagination are all authoritative on the backend now. (`low` /
  // below reorder point is DEFERRED to M3, so there is no `low` drill path here.)
  const { data, isLoading, isFetching, isError } = useScmProducts(
    filters,
    open ? target : null,
    {
      q: debounced || undefined,
      sort: sort?.field,
      dir: sort?.dir,
      page,
      limit: PAGE_SIZE,
    },
  );

  const rows = data?.data ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const toggleSort = (field: string) => {
    setSort((prev) => {
      if (!prev || prev.field !== field) return { field, dir: 'asc' };
      if (prev.dir === 'asc') return { field, dir: 'desc' };
      return null; // third click clears back to the default order
    });
  };

  return (
    // `modal` so the overlay intercepts the outside click: clicking a card
    // behind the popup ONLY closes the popup (no click-through to the card).
    <Dialog open={open} onOpenChange={onOpenChange} modal>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {isLoading
              ? 'Loading products…'
              : `${fmtInt(total)} product${total === 1 ? '' : 's'}`}
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search product code or name…"
            className="pl-9"
            aria-label="Search products"
          />
        </div>

        <DialogBody className="max-h-[55dvh] overflow-auto">
          {isLoading ? (
            <div className="space-y-2 py-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="py-10 text-center text-sm text-scm-stockout">
              Couldn&apos;t load products. Close and reopen to retry.
            </div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <span className="flex size-11 items-center justify-center rounded-full bg-muted">
                <PackageOpen className="size-5 text-muted-foreground" />
              </span>
              <div className="text-sm text-muted-foreground">
                {debounced
                  ? `No products match “${debounced}”.`
                  : 'No products in this scope.'}
              </div>
            </div>
          ) : (
            <table className="w-full min-w-[880px] text-sm">
              <thead className="sticky top-0 z-10 bg-background">
                <tr className="text-2xs text-muted-foreground">
                  {COLUMNS.map((col) => {
                    const active = sort?.field === col.id;
                    const alignCls =
                      col.align === 'right'
                        ? 'text-right'
                        : col.align === 'center'
                          ? 'text-center'
                          : 'text-left';
                    return (
                      <th
                        key={col.id}
                        className={cn(
                          'py-2 font-medium',
                          alignCls,
                          col.id === 'sku' ? 'pr-2' : 'px-2',
                        )}
                      >
                        {col.sortable ? (
                          <button
                            type="button"
                            onClick={() => toggleSort(col.id)}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-sm hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                              col.align === 'right' && 'flex-row-reverse',
                              active && 'text-foreground',
                            )}
                          >
                            {col.label}
                            {active ? (
                              sort?.dir === 'asc' ? (
                                <ArrowUp className="size-3" />
                              ) : (
                                <ArrowDown className="size-3" />
                              )
                            ) : (
                              <ChevronsUpDown className="size-3 opacity-40" />
                            )}
                          </button>
                        ) : (
                          <span>{col.label}</span>
                        )}
                        {col.info ? <NetPositionInfo className="ms-1 align-middle" /> : null}
                        {col.docInfo ? <DaysOfCoverInfo className="ms-1 align-middle" /> : null}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className={cn(isFetching && 'opacity-60')}>
                {rows.map((p, i) => {
                  // ∞ cover = stock on hand but no forward demand; deficit → "—".
                  const docInfinite =
                    (p.avg_daily_demand === null || p.avg_daily_demand === 0) &&
                    p.net_position > 0;
                  return (
                  <tr
                    key={`${p.sku}-${p.warehouse_code}-${i}`}
                    className="border-t border-border/60"
                  >
                    <td className="py-2 pr-2">
                      <div className="font-medium">{p.sku}</div>
                      <div
                        className="truncate text-xs text-muted-foreground"
                        title={`${p.product_name} · ${p.warehouse_name}`}
                      >
                        {p.product_name} · {p.warehouse_name}
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap items-center gap-1">
                        <StateChip state={p.status} />
                        {p.stockout_with_committed ? <CommittedStockoutPill /> : null}
                      </div>
                    </td>
                    <td
                      className={cn(
                        'px-2 py-2 text-right font-semibold tabular-nums',
                        p.net_position < 0 && 'text-scm-stockout',
                      )}
                    >
                      {fmtSigned(p.net_position)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{fmtInt(p.on_hand)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{fmtInt(p.on_order)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{fmtInt(p.committed)}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-muted-foreground">
                      {p.stock_valuation === null ? EM_DASH : fmtMoney(p.stock_valuation)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
                      {fmtDecimal(p.avg_daily_demand)}
                    </td>
                    <td
                      className={cn(
                        'px-2 py-2 text-right tabular-nums',
                        docInfinite && 'text-scm-overstock',
                      )}
                    >
                      {fmtDoc(p.days_of_cover, docInfinite)}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <ClassChip value={p.abc_class} kind="abc" />
                    </td>
                    <td className="px-2 py-2 text-center">
                      <ClassChip value={p.xyz_class} kind="xyz" />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </DialogBody>

        <DialogFooter className="flex-row items-center justify-between gap-2 sm:justify-between">
          {pageCount > 1 ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="Previous page"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <span className="tabular-nums">
                Page {page} of {pageCount}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount || isFetching}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                aria-label="Next page"
              >
                <ChevronRight className="size-4" />
              </Button>
            </div>
          ) : (
            <span />
          )}

          {onViewInList ? (
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                onViewInList();
              }}
            >
              View in list
              <ArrowUpRight className="size-4" />
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
