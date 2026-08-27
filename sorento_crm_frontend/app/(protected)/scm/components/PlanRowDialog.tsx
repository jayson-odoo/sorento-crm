'use client';

import { Fragment, useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';

import { EM_DASH, fmtDate, fmtInt, fmtMoney, fmtSupplierCost } from '../lib/format';
import { useContainerRequestDrill } from '../hooks/useContainerRequestDrill';
import { useLocationStock } from '../reorder/hooks/useReorderRun';
import { StockDocumentsPanel } from '../../project-sales/fulfilment-planning/components/StockDocumentsPanel';
import type {
  ContainerRequestDrillIncomingPlRow,
  ContainerRequestDrillPoRow,
  ContainerRequestDrillSpoRow,
} from '../services/containerRequestDrillService';

/**
 * ONE lightbox for the SCM family (R7, AC-B1/AC-B7).
 *
 * Every figure a buyer would want to argue with opens a dialog naming the DOCUMENTS behind
 * it: the sales orders, the shipping orders, the packing lists, the purchase orders, the
 * stock rows. What this replaces on the loading plan and the SPO planner was a hover popover
 * per number - mouse-only, too narrow for a document table, dismissed by the mouse drifting
 * off it, and (inside a DataGrid cell) painted over by the sticky column beside it, which is
 * why each one carried a `PopoverPortal` workaround.
 *
 * The shell is copied from the reorder-revamp lane's `PlanRowDialogs.tsx` rather than
 * reinvented, so the two screens' lightboxes are the same object to a reader; at whichever
 * merge lands second, that lane re-points its import here and one file survives (plan
 * section 9).
 *
 * The shell knows nothing about any body: it is a titled frame, and the caller renders what
 * belongs inside. A registry keyed on `kind` would have to import every body and so every
 * body's data hook, which is how one dialog comes to fetch for six screens.
 */

export type PlanRowDialogKind =
  | 'project'
  | 'retail'
  | 'on_hand'
  | 'spo'
  | 'incoming_pl'
  | 'po'
  | 'po_takes'
  | 'so_coverage';

/** The word in front of the product code. Kept here so the eight titles cannot drift. */
export const PLAN_ROW_DIALOG_TITLES: Record<PlanRowDialogKind, string> = {
  project: 'Project',
  retail: 'Retail',
  on_hand: 'On hand',
  spo: 'SPO',
  incoming_pl: 'Incoming PL',
  po: 'PO',
  po_takes: 'PO covers',
  so_coverage: 'SO covered',
};

// ---------------------------------------------------------------------------
// Table furniture - exported so a body written by another screen looks the same
// ---------------------------------------------------------------------------

export function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return (
    <th
      className={cn(
        'whitespace-nowrap px-2 py-1.5 font-medium text-muted-foreground',
        right ? 'text-right' : 'text-left',
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  right,
  title,
  className,
  colSpan,
}: {
  children: ReactNode;
  right?: boolean;
  title?: string;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      className={cn('px-2 py-1.5', right && 'text-right tabular-nums', className)}
      title={title}
      colSpan={colSpan}
    >
      {children}
    </td>
  );
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-2 py-6 text-center text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

export function LoadingRows({ colSpan }: { colSpan: number }) {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <tr key={i}>
          <td colSpan={colSpan} className="px-2 py-1.5">
            <Skeleton className="h-4 w-full" />
          </td>
        </tr>
      ))}
    </>
  );
}

export function DocTable({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">{children}</table>
    </div>
  );
}

/** What a body says when a drill has no SPO on its way to a pool for this product. */
export const NO_SPO_TO_POOL = 'No SPO is on its way to a site pool for this product.';

function textCell(value: string | null | undefined) {
  return value ? value : <span className="text-muted-foreground">{EM_DASH}</span>;
}

function moneyCell(value: number | null | undefined) {
  return value === null || value === undefined ? (
    <span className="text-muted-foreground">{EM_DASH}</span>
  ) : (
    fmtMoney(value)
  );
}

/**
 * A footing row: the label on the left, the figure UNDER the column it totals, and the
 * columns after it left blank. `colSpan` is how many columns precede the total, `trailing`
 * how many follow it - stated rather than derived so a table that gains a column fails to
 * line up visibly instead of silently misfooting.
 */
function TotalRow({
  colSpan,
  label,
  total,
  trailing = 0,
}: {
  colSpan: number;
  label: string;
  total: number;
  trailing?: number;
}) {
  return (
    <tr className="border-t font-medium">
      <Td colSpan={colSpan}>{label}</Td>
      <Td right>{fmtInt(total)}</Td>
      {trailing > 0 ? <Td colSpan={trailing}> </Td> : null}
    </tr>
  );
}

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** `2026-04` reads `Apr 26`. The bucket is a month, so it is never rendered as a date. */
export function monthLabel(month: string | null): string {
  if (!month) return EM_DASH;
  const [year, m] = month.split('-');
  const name = MONTHS[Number(m) - 1];
  if (!name || !year) return month;
  return `${name} ${year.slice(2)}`;
}

// ---------------------------------------------------------------------------
// Project / Retail - the orders behind a channel's number, and the 12-month series
// ---------------------------------------------------------------------------

/** One open sales-order line behind the Project or Retail figure. */
export interface PlanDemandLineRow {
  so_number: string | null;
  customer: string | null;
  project: string | null;
  agent: string | null;
  /** What the customer pays, in ringgit. Null when the line carries no price. */
  price: number | null;
  qty: number;
  required_date: string | null;
  /** The sales order's own page, when the caller can name one. */
  href?: string | null;
}

/** One month of the two 12-month series (AC-B2 / AC-B6). */
export interface PlanHistoryPoint {
  month: string;
  project_qty: number;
  retail_qty: number;
}

function peakOf(history: PlanHistoryPoint[], channel: 'project' | 'retail') {
  let peak: PlanHistoryPoint | null = null;
  for (const point of history) {
    const qty = channel === 'project' ? point.project_qty : point.retail_qty;
    const best = peak ? (channel === 'project' ? peak.project_qty : peak.retail_qty) : -1;
    if (qty > best) peak = point;
  }
  if (!peak) return null;
  return {
    month: peak.month,
    qty: channel === 'project' ? peak.project_qty : peak.retail_qty,
  };
}

/**
 * One channel's demand, twice: what is still open before the plan's cut-off, and what the
 * product's order history says over the last twelve months.
 *
 * Controlled and pure - the loading-plan grid already holds both payloads (the build's
 * `include_lines` read and the history read), so a second fetch here would ask the server for
 * what the caller is holding. `initialTab='history'` is how the Project peak / Retail peak
 * cells open the same dialog on the series they name (AC-B6).
 */
export function ProjectRetailTabs({
  channel,
  lines,
  history,
  initialTab = 'open',
  focus,
  loading,
}: {
  channel: 'project' | 'retail';
  lines: PlanDemandLineRow[];
  history: PlanHistoryPoint[];
  initialTab?: 'open' | 'history';
  /** Which series the reader came in for. Defaults to the channel's own. */
  focus?: 'project' | 'retail';
  loading?: boolean;
}) {
  const focused = focus ?? channel;
  const total = useMemo(() => lines.reduce((sum, l) => sum + (l.qty || 0), 0), [lines]);
  const projectPeak = peakOf(history, 'project');
  const retailPeak = peakOf(history, 'retail');
  const openLabel =
    channel === 'project'
      ? `Open project SO lines (${fmtInt(lines.length)})`
      : `Open sales orders (${fmtInt(lines.length)})`;

  return (
    <Tabs defaultValue={initialTab}>
      <TabsList>
        <TabsTrigger value="open">{openLabel}</TabsTrigger>
        <TabsTrigger value="history">12-month history</TabsTrigger>
      </TabsList>

      <TabsContent value="open">
        <DocTable>
          <thead>
            <tr className="border-b">
              <Th>Sales order</Th>
              <Th>Customer</Th>
              <Th>Project</Th>
              <Th>Agent</Th>
              <Th right>Price</Th>
              <Th right>Qty</Th>
              <Th right>Required</Th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <LoadingRows colSpan={7} />
            ) : lines.length === 0 ? (
              <EmptyRow colSpan={7}>Nothing open on this channel for this product.</EmptyRow>
            ) : (
              <>
                {lines.map((l, i) => (
                  <tr key={`${l.so_number ?? 'unnumbered'}-${i}`} className="border-b last:border-0">
                    <Td>
                      {l.href ? (
                        <a className="hover:underline" href={l.href}>
                          {l.so_number ?? 'Not numbered'}
                        </a>
                      ) : (
                        (l.so_number ?? 'Not numbered')
                      )}
                    </Td>
                    <Td title={l.customer ?? undefined}>
                      <span className="block max-w-56 truncate">{textCell(l.customer)}</span>
                    </Td>
                    <Td title={l.project ?? undefined}>
                      <span className="block max-w-56 truncate">{textCell(l.project)}</span>
                    </Td>
                    <Td>{textCell(l.agent)}</Td>
                    <Td right>{moneyCell(l.price)}</Td>
                    <Td right>{fmtInt(l.qty)}</Td>
                    <Td right>{fmtDate(l.required_date)}</Td>
                  </tr>
                ))}
                <TotalRow colSpan={5} label="Total" total={total} trailing={1} />
              </>
            )}
          </tbody>
        </DocTable>
      </TabsContent>

      <TabsContent value="history">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-4 text-xs">
            <span className={cn(focused === 'project' && 'font-medium')}>
              {`Project peak ${projectPeak ? `${fmtInt(projectPeak.qty)} ${monthLabel(projectPeak.month)}` : EM_DASH}`}
            </span>
            <span className={cn(focused === 'retail' && 'font-medium')}>
              {`Retail peak ${retailPeak ? `${fmtInt(retailPeak.qty)} ${monthLabel(retailPeak.month)}` : EM_DASH}`}
            </span>
          </div>
          <DocTable>
            <thead>
              <tr className="border-b">
                <Th>Month</Th>
                <Th right>Project</Th>
                <Th right>Retail</Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <LoadingRows colSpan={3} />
              ) : history.length === 0 ? (
                <EmptyRow colSpan={3}>Nothing was ordered in the last twelve months.</EmptyRow>
              ) : (
                history.map((point) => (
                  <tr key={point.month} className="border-b last:border-0">
                    <Td>{monthLabel(point.month)}</Td>
                    <Td right className={cn(focused === 'project' && 'font-medium')}>
                      {fmtInt(point.project_qty)}
                    </Td>
                    <Td right className={cn(focused === 'retail' && 'font-medium')}>
                      {fmtInt(point.retail_qty)}
                    </Td>
                  </tr>
                ))
              )}
            </tbody>
          </DocTable>
        </div>
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// On hand - the site pools' stock, row by row, with the documents under each
// ---------------------------------------------------------------------------

/**
 * Reorder planning's On hand lightbox, verbatim (AC-B3 / AC-G3): the SITE POOL rows only,
 * each expanding to the documents standing behind that location.
 *
 * Pools only, because a project bin holds stock already spoken for by an Order Inquiry, and
 * counting it here would disagree with the cell, which nets pools alone. A response with no
 * pool row at all falls back to everything it was given, rather than showing an empty table
 * for a product that plainly has stock somewhere.
 */
export function OnHandTable({ productId, itemCode }: { productId: string; itemCode: string }) {
  const stock = useLocationStock(productId, Boolean(productId));
  const [openRow, setOpenRow] = useState<string | null>(null);

  const rows = useMemo(() => {
    const locations = stock.data?.locations ?? [];
    const pools = locations.filter((l) => (l as { is_pool?: boolean }).is_pool);
    return pools.length ? pools : locations;
  }, [stock.data]);

  const total = rows.reduce((sum, l) => sum + (l.on_hand || 0), 0);

  return (
    <div className="space-y-2">
      <DocTable>
        <thead>
          <tr className="border-b">
            <Th> </Th>
            <Th>Location</Th>
            <Th right>On hand</Th>
            <Th right>Reserved</Th>
            <Th right>Free</Th>
            <Th right>SO qty</Th>
            <Th right>SPO qty</Th>
            <Th right>Available</Th>
            <Th right>PO qty</Th>
          </tr>
        </thead>
        <tbody>
          {stock.isLoading ? (
            <LoadingRows colSpan={9} />
          ) : rows.length === 0 ? (
            <EmptyRow colSpan={9}>No stock rows for this product.</EmptyRow>
          ) : (
            <>
              {rows.map((loc) => {
                const expanded = openRow === loc.warehouse_id;
                // `po_qty` arrives with the reorder lane's own extension of this endpoint;
                // until it merges the column reads as "not stated", never as zero.
                const poQty = (loc as { po_qty?: number | null }).po_qty;
                return (
                  <Fragment key={loc.warehouse_id}>
                    <tr
                      className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                      onClick={() => setOpenRow(expanded ? null : loc.warehouse_id)}
                    >
                      <Td className="w-8">
                        {expanded ? (
                          <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
                        ) : (
                          <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden />
                        )}
                      </Td>
                      <Td title={loc.warehouse_code ?? undefined}>
                        {textCell(loc.warehouse_code)}
                      </Td>
                      <Td right>{fmtInt(loc.on_hand)}</Td>
                      <Td right>{fmtInt(loc.reserved)}</Td>
                      <Td right>{fmtInt(loc.free)}</Td>
                      <Td right>{fmtInt(loc.so_qty)}</Td>
                      <Td right>{fmtInt(loc.spo_qty)}</Td>
                      <Td right>
                        <span className={cn(loc.available < 0 && 'text-destructive')}>
                          {fmtInt(loc.available)}
                        </span>
                      </Td>
                      <Td right>
                        {poQty === null || poQty === undefined ? (
                          <span className="text-muted-foreground">{EM_DASH}</span>
                        ) : (
                          fmtInt(poQty)
                        )}
                      </Td>
                    </tr>
                    {expanded ? (
                      <tr>
                        <td colSpan={9} className="bg-muted/30 p-0">
                          <StockDocumentsPanel
                            productId={productId}
                            warehouseId={loc.warehouse_id}
                            itemCode={itemCode}
                            locationCode={loc.warehouse_code ?? EM_DASH}
                          />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
              <TotalRow colSpan={2} label="Site pools" total={total} trailing={6} />
            </>
          )}
        </tbody>
      </DocTable>
      {/* The newest stock timestamp for the product, never the moment this dialog asked. */}
      {stock.data?.as_of ? (
        <p className="text-2xs text-muted-foreground">
          Stock as of {formatDateTimeInMalaysia(stock.data.as_of)}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SPO - what is on the water for the site pools
// ---------------------------------------------------------------------------

/**
 * The shipping orders behind the SPO cell (AC-B4), open first and then what has landed.
 *
 * Rows come from `/container-requests/drill?kind=spo`, whose total IS the cell - see that
 * service's docstring for why the reader is `spo_allocations` and not the purchase-order
 * table (migration 420 moved every SPO document out of it).
 */
export function SpoTabs({ supplierId, productId }: { supplierId: string; productId: string }) {
  const drill = useContainerRequestDrill(supplierId, productId, 'spo');
  const open = (drill.data?.rows ?? []) as ContainerRequestDrillSpoRow[];
  const history = (drill.data?.history ?? []) as ContainerRequestDrillSpoRow[];

  const body = (rows: ContainerRequestDrillSpoRow[], emptyText: string, withTotal: boolean) => (
    <DocTable>
      <thead>
        <tr className="border-b">
          <Th>SPO</Th>
          <Th>Packing list</Th>
          <Th>To</Th>
          <Th right>Qty</Th>
          <Th right>Received</Th>
          <Th right>ETA</Th>
          <Th>Status</Th>
        </tr>
      </thead>
      <tbody>
        {drill.isLoading ? (
          <LoadingRows colSpan={7} />
        ) : rows.length === 0 ? (
          <EmptyRow colSpan={7}>{emptyText}</EmptyRow>
        ) : (
          <>
            {rows.map((r, i) => (
              <tr key={`${r.spo_number ?? 'unnumbered'}-${r.shipment_id}-${i}`} className="border-b last:border-0">
                <Td>{textCell(r.spo_number)}</Td>
                <Td>{r.shipment_id ? (r.shipment_number ?? 'Draft') : 'Not shipped'}</Td>
                <Td>{textCell(r.warehouse_code)}</Td>
                <Td right>{fmtInt(r.qty)}</Td>
                <Td right>{fmtInt(r.received)}</Td>
                <Td right>{fmtDate(r.eta)}</Td>
                <Td>{textCell(r.status)}</Td>
              </tr>
            ))}
            {withTotal ? (
              <TotalRow
                colSpan={3}
                label="Total"
                total={drill.data?.total ?? rows.reduce((s, r) => s + r.qty, 0)}
                trailing={3}
              />
            ) : null}
          </>
        )}
      </tbody>
    </DocTable>
  );

  return (
    <Tabs defaultValue="open">
      <TabsList>
        <TabsTrigger value="open">{`Open to pools (${fmtInt(open.length)})`}</TabsTrigger>
        <TabsTrigger value="history">{`History (${fmtInt(history.length)})`}</TabsTrigger>
      </TabsList>
      <TabsContent value="open">{body(open, NO_SPO_TO_POOL, true)}</TabsContent>
      <TabsContent value="history">
        {body(history, 'No shipping order has landed here for this product.', false)}
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// Incoming PL - packing lists on their way, reference only
// ---------------------------------------------------------------------------

/**
 * The packing lists behind the Incoming PL cell (AC-B4). One table, no tabs: a packing list
 * that has arrived is already the On hand dialog, so there is no landed half to show.
 */
export function IncomingPlTable({
  supplierId,
  productId,
  onOpenShipment,
}: {
  supplierId: string;
  productId: string;
  /** Opens the packing list. Absent = the number is plain text. */
  onOpenShipment?: (shipmentId: string) => void;
}) {
  const drill = useContainerRequestDrill(supplierId, productId, 'incoming_pl');
  const rows = (drill.data?.rows ?? []) as ContainerRequestDrillIncomingPlRow[];

  return (
    <DocTable>
      <thead>
        <tr className="border-b">
          <Th>Packing list</Th>
          <Th>Container</Th>
          <Th>Supplier</Th>
          <Th right>Qty</Th>
          <Th right>ETA</Th>
          <Th>Status</Th>
        </tr>
      </thead>
      <tbody>
        {drill.isLoading ? (
          <LoadingRows colSpan={6} />
        ) : rows.length === 0 ? (
          <EmptyRow colSpan={6}>Nothing is on its way on a packing list for this product.</EmptyRow>
        ) : (
          <>
            {rows.map((r) => (
              <tr key={r.shipment_id} className="border-b last:border-0">
                <Td>
                  {onOpenShipment ? (
                    <button
                      type="button"
                      className="underline-offset-2 hover:underline"
                      onClick={() => onOpenShipment(r.shipment_id)}
                    >
                      {r.shipment_number ?? 'Draft'}
                    </button>
                  ) : (
                    (r.shipment_number ?? 'Draft')
                  )}
                </Td>
                <Td>{textCell(r.container_number)}</Td>
                <Td title={r.supplier_name ?? undefined}>
                  <span className="block max-w-56 truncate">{textCell(r.supplier_name)}</span>
                </Td>
                <Td right>{fmtInt(r.qty)}</Td>
                <Td right>{fmtDate(r.eta)}</Td>
                <Td>{textCell(r.status)}</Td>
              </tr>
            ))}
            <TotalRow
              colSpan={3}
              label="Total"
              total={drill.data?.total ?? rows.reduce((s, r) => s + r.qty, 0)}
              trailing={2}
            />
          </>
        )}
      </tbody>
    </DocTable>
  );
}

// ---------------------------------------------------------------------------
// PO - what is already ordered, and what was ordered before
// ---------------------------------------------------------------------------

/** The purchase-order lines behind the PO cell (AC-B4): open first, then the last 12 months. */
export function PoTabs({ supplierId, productId }: { supplierId: string; productId: string }) {
  const drill = useContainerRequestDrill(supplierId, productId, 'po');
  const open = (drill.data?.rows ?? []) as ContainerRequestDrillPoRow[];
  const history = (drill.data?.history ?? []) as ContainerRequestDrillPoRow[];

  const body = (rows: ContainerRequestDrillPoRow[], emptyText: string, withTotal: boolean) => (
    <DocTable>
      <thead>
        <tr className="border-b">
          <Th>PO</Th>
          <Th>Supplier</Th>
          <Th right>Qty</Th>
          <Th right>Still to come</Th>
          <Th right>Unit price</Th>
          <Th right>Issued</Th>
          <Th right>ETA</Th>
          <Th>Status</Th>
        </tr>
      </thead>
      <tbody>
        {drill.isLoading ? (
          <LoadingRows colSpan={8} />
        ) : rows.length === 0 ? (
          <EmptyRow colSpan={8}>{emptyText}</EmptyRow>
        ) : (
          <>
            {rows.map((r, i) => (
              <tr key={`${r.purchase_order_id}-${i}`} className="border-b last:border-0">
                <Td>{textCell(r.po_number)}</Td>
                <Td title={r.supplier_name ?? undefined}>
                  <span className="block max-w-56 truncate">{textCell(r.supplier_name)}</span>
                </Td>
                <Td right>{fmtInt(r.qty_ordered)}</Td>
                <Td right>{fmtInt(r.still_to_come)}</Td>
                <Td right>
                  {r.unit_price === null ? (
                    <span className="text-muted-foreground">{EM_DASH}</span>
                  ) : (
                    fmtSupplierCost(r.unit_price, r.currency)
                  )}
                </Td>
                <Td right>{fmtDate(r.issued)}</Td>
                <Td right>{fmtDate(r.eta)}</Td>
                <Td>{textCell(r.status)}</Td>
              </tr>
            ))}
            {withTotal ? (
              <TotalRow
                colSpan={3}
                label="Total still to come"
                total={drill.data?.total ?? rows.reduce((s, r) => s + r.still_to_come, 0)}
                trailing={4}
              />
            ) : null}
          </>
        )}
      </tbody>
    </DocTable>
  );

  return (
    <Tabs defaultValue="open">
      <TabsList>
        <TabsTrigger value="open">{`Open (${fmtInt(open.length)})`}</TabsTrigger>
        <TabsTrigger value="history">{`History (${fmtInt(history.length)})`}</TabsTrigger>
      </TabsList>
      <TabsContent value="open">{body(open, 'Nothing is on order for this product.', true)}</TabsContent>
      <TabsContent value="history">
        {body(history, 'No purchase order in the last twelve months names this product.', false)}
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// SPO planner - the two pickers (R21, AC-G1/AC-G2)
// ---------------------------------------------------------------------------

/** One PO this SPO can draw from. Structurally the planner's own `SpoPoTake`. */
export interface PoTakeRow {
  po_line_id: string;
  po_number: string | null;
  supplier_name: string | null;
  /** The PO's own document date, distinct from `expected_date` (when the line is due). */
  po_date: string | null;
  expected_date: string | null;
  /** What the cascade took from this line. */
  qty: number;
  /** What the line has open, which is what it could give if a neighbour were unticked. */
  open_qty: number;
}

/**
 * Which POs this SPO draws from, oldest DOCUMENT first (Q8, AC-G1), each one tickable and
 * the suggested takes pre-ticked.
 *
 * Controlled and fetch-free on purpose: the SPO planner already holds `po_takes` in its
 * payload and owns the cascade that re-walks the takes when a tick changes. A picker that
 * fetched would be a second opinion about the same rows.
 */
export function PoTakesPicker({
  takes,
  tickedIds,
  onChange,
  coveredQty,
  packedQty,
}: {
  takes: PoTakeRow[];
  tickedIds: string[];
  onChange: (ids: string[]) => void;
  /** What the ticked takes cover, for the footer. */
  coveredQty: number;
  /** What the shipment line packs, for the footer. */
  packedQty: number;
}) {
  const toggle = (id: string, on: boolean) =>
    onChange(on ? [...tickedIds, id] : tickedIds.filter((x) => x !== id));

  return (
    <div className="space-y-2">
      <DocTable>
        <thead>
          <tr className="border-b">
            <Th> </Th>
            <Th>PO</Th>
            <Th>Supplier</Th>
            <Th right>Doc date</Th>
            <Th right>Due</Th>
            <Th right>Open</Th>
            <Th right>Taken</Th>
          </tr>
        </thead>
        <tbody>
          {takes.length === 0 ? (
            <EmptyRow colSpan={7}>No open PO can back this line.</EmptyRow>
          ) : (
            takes.map((t) => (
              <tr key={t.po_line_id} className="border-b last:border-0">
                <Td className="w-8">
                  <Checkbox
                    checked={tickedIds.includes(t.po_line_id)}
                    onCheckedChange={(checked) => toggle(t.po_line_id, !!checked)}
                    aria-label={`Draw from ${t.po_number ?? t.po_line_id}`}
                  />
                </Td>
                <Td>{textCell(t.po_number)}</Td>
                <Td title={t.supplier_name ?? undefined}>
                  <span className="block max-w-56 truncate">{textCell(t.supplier_name)}</span>
                </Td>
                <Td right>{fmtDate(t.po_date)}</Td>
                <Td right>{fmtDate(t.expected_date)}</Td>
                <Td right>{fmtInt(t.open_qty)}</Td>
                <Td right>{fmtInt(t.qty)}</Td>
              </tr>
            ))
          )}
        </tbody>
      </DocTable>
      <p className="border-t pt-2 text-2xs text-muted-foreground">
        {`${fmtInt(tickedIds.length)} of ${fmtInt(takes.length)} POs · covers ${fmtInt(coveredQty)} of packed ${fmtInt(packedQty)}`}
      </p>
    </div>
  );
}

/** One piece of demand this SPO could cover. Structurally the planner's `SpoCoverageLine`. */
export interface SoCoverageRow {
  key: string;
  kind: 'project' | 'retail';
  document: string | null;
  customer_name: string | null;
  required_date: string | null;
  qty: number;
  warehouse_code: string | null;
}

/**
 * Which demand this SPO is pointed at (Q4, AC-G2): project rows first, then retail, in the
 * order the server walked them, pre-ticked to the packed quantity.
 *
 * What no tick claims is stated as Unassigned rather than quietly attached to the first order
 * in the list. Controlled and fetch-free for the same reason as `PoTakesPicker`.
 */
export function SoCoveragePicker({
  coverage,
  tickedKeys,
  onChange,
  unassigned,
  takes,
}: {
  coverage: SoCoverageRow[];
  tickedKeys: string[];
  onChange: (keys: string[]) => void;
  unassigned: number;
  /** What each ticked row actually GETS out of this SPO, by `key` (AC-G2's Take column).
   *  Omitted by a caller that holds no walk - the column then does not render at all,
   *  rather than reading 0 for every row and being mistaken for one. */
  takes?: Record<string, number>;
}) {
  const toggle = (key: string, on: boolean) =>
    onChange(on ? [...tickedKeys, key] : tickedKeys.filter((x) => x !== key));
  const cols = takes ? 8 : 7;

  return (
    <div className="space-y-2">
      <DocTable>
        <thead>
          <tr className="border-b">
            <Th> </Th>
            <Th>Sales order</Th>
            <Th>Customer</Th>
            <Th>Class</Th>
            <Th right>Required</Th>
            <Th right>Open</Th>
            {takes ? <Th right>Take</Th> : null}
            <Th>Location</Th>
          </tr>
        </thead>
        <tbody>
          {coverage.length === 0 ? (
            <EmptyRow colSpan={cols}>No open demand this SPO could cover.</EmptyRow>
          ) : (
            coverage.map((c) => (
              <tr key={c.key} className="border-b last:border-0">
                <Td className="w-8">
                  <Checkbox
                    checked={tickedKeys.includes(c.key)}
                    onCheckedChange={(checked) => toggle(c.key, !!checked)}
                    aria-label={`Cover ${c.document ?? c.key}`}
                  />
                </Td>
                <Td>{textCell(c.document)}</Td>
                <Td title={c.customer_name ?? undefined}>
                  <span className="block max-w-56 truncate">{textCell(c.customer_name)}</span>
                </Td>
                <Td>{c.kind === 'project' ? 'Project' : 'Retail'}</Td>
                <Td right>{fmtDate(c.required_date)}</Td>
                <Td right>{fmtInt(c.qty)}</Td>
                {takes ? <Td right>{fmtInt(takes[c.key] ?? 0)}</Td> : null}
                <Td>{textCell(c.warehouse_code)}</Td>
              </tr>
            ))
          )}
        </tbody>
      </DocTable>
      <p className="border-t pt-2 text-2xs text-muted-foreground">
        {`Unassigned ${fmtInt(unassigned)}`}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The shell
// ---------------------------------------------------------------------------

/**
 * The one dialog a grid mounts, titled "<Kind> · <product code>" with the product name as its
 * description (Radix wants one, and a sentence explaining the dialog would be an on-screen
 * explanation, which the standards forbid).
 *
 * `context` is the figure and its qualifier - "2,876 before cut-off 30/09/2026", "117
 * arriving at site pools" - so the reader can see what the rows are supposed to add up to
 * without reading them.
 */
export function PlanRowDialog({
  kind,
  productCode,
  productName,
  context,
  open = true,
  onOpenChange,
  children,
}: {
  kind: PlanRowDialogKind;
  productCode: string;
  productName?: string | null;
  context?: string | null;
  open?: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]">
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">
            {`${PLAN_ROW_DIALOG_TITLES[kind]} · ${productCode}`}
            {context ? (
              <span className="ms-2 text-xs font-normal text-muted-foreground">{context}</span>
            ) : null}
          </DialogTitle>
          <DialogDescription className="truncate text-xs" title={productName ?? undefined}>
            {productName ?? productCode}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">{children}</DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default PlanRowDialog;
