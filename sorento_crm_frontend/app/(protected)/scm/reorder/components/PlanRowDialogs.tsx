'use client';

import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { StockDocumentsPanel } from '../../../project-sales/fulfilment-planning/components/StockDocumentsPanel';
import { EM_DASH, fmtDate, fmtInt, fmtMoney, fmtSupplierCost } from '../../lib/format';
import { useLocationStock, useRecommendationDemand } from '../hooks/useReorderRun';
import { getPoHistoryToPool, getSpoHistory } from '../services/planEditsService';
import type { PoReceipt } from '../lib/poCover';
import type { PlanLine } from '../lib/planLine';
import { isGroupedLine } from '../lib/planLineGrouping';

/**
 * Six numbers, six lightboxes (plan 4.6).
 *
 * Every figure on the collapsed row that a buyer would want to argue with now opens a dialog
 * naming the DOCUMENTS behind it - the sales orders, the shipping orders, the purchase orders,
 * the stock rows. What this replaces was a hover popover per number: a mouse-only affordance,
 * six of them per row, each too narrow for a document table and each dismissed by the mouse
 * drifting off it.
 *
 * ONE dialog is mounted per grid, keyed by which number was pressed, so two can never be open
 * at once and the grid does not build six subtrees per row.
 */

export type PlanDialogKind = 'suggested' | 'project' | 'retail' | 'on_hand' | 'spo' | 'po';

export interface PlanDialogRequest {
  kind: PlanDialogKind;
  line: PlanLine;
}

/**
 * The SITE POOL location this row's supply is counted at (R15): the pool warehouse itself,
 * never its project bins (BRW-BB, BRW-AM).
 *
 * `pool_warehouse_code` is the answer (plan 5.11): the row's own pool, named by the backend.
 * A grouped product row carries the pool's ID but has no member sitting AT the pool to read
 * a code off - a run only writes recommendations for locations with demand, so on real data
 * (32MM TAIL PIECE COUPLING) there often is none, and naming the first member instead printed
 * "to BRW-BB", a project bin, beside a count that deliberately excludes it.
 *
 * The member scan below stays as the fallback for a run frozen before the field existed.
 * Null when it cannot be named at all, and the dialogs then drop the location from their
 * wording rather than name the wrong one.
 */
export function poolLocationLabel(line: PlanLine): string | null {
  if (line.rec.pool_warehouse_code) return line.rec.pool_warehouse_code;
  if (!isGroupedLine(line)) return line.rec.warehouse_code ?? null;
  const poolId = line.rec.pool_warehouse_id ?? null;
  const members = line.__group.members;
  // The member that IS the pool: by id, then by the rule that names one - a pool location's
  // own `pool_warehouse_id` points at itself.
  const atPool =
    (poolId ? members.find((m) => m.rec.pool_warehouse_code) : undefined)?.rec
      .pool_warehouse_code ??
    (poolId ? members.find((m) => m.warehouse_id === poolId) : undefined)?.rec
      .warehouse_code ??
    members.find((m) => m.warehouse_id && m.rec.pool_warehouse_id === m.warehouse_id)?.rec
      .warehouse_code;
  return atPool ?? null;
}

/** " to BRW", or nothing at all when the pool cannot be named. */
function toPool(pool: string | null): string {
  return pool ? ` to ${pool}` : '';
}

/** Any one member's recommendation id - the backend resolves product + run off it. */
function anyRecId(line: PlanLine): string | null {
  if (!isGroupedLine(line)) return line.rec.id;
  return line.__group.members[0]?.rec.id ?? null;
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
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

function Td({
  children,
  right,
  title,
  className,
}: {
  children: React.ReactNode;
  right?: boolean;
  title?: string;
  className?: string;
}) {
  return (
    <td
      className={cn('px-2 py-1.5', right && 'text-right tabular-nums', className)}
      title={title}
    >
      {children}
    </td>
  );
}

function EmptyRow({ colSpan, children }: { colSpan: number; children: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-2 py-6 text-center text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

function LoadingRows({ colSpan }: { colSpan: number }) {
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

function DocTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">{children}</table>
    </div>
  );
}

/** Price on a demand line - what the customer pays, in ringgit. */
function priceCell(value: number | null | undefined) {
  return value === null || value === undefined ? (
    <span className="text-muted-foreground">{EM_DASH}</span>
  ) : (
    fmtMoney(value)
  );
}

function textCell(value: string | null | undefined) {
  return value ? value : <span className="text-muted-foreground">{EM_DASH}</span>;
}

// ---------------------------------------------------------------------------
// Project / Retail - the orders behind a channel's number
// ---------------------------------------------------------------------------

/**
 * One channel's demand, twice: what is still open at this location, and what the product's
 * order history says over the channel's own window. Both come from the SAME endpoint the row
 * already used (`demand?channel=`); the open list is its default scope and the history list
 * is `scope=product`, which the backend already answers with `history_lines`.
 */
function DemandTabs({
  line,
  runId,
  channel,
}: {
  line: PlanLine;
  runId: string | null;
  channel: 'project' | 'retail';
}) {
  const recId = anyRecId(line);
  const open = useRecommendationDemand(runId, recId ?? '', Boolean(runId && recId), channel);
  const history = useRecommendationDemand(
    runId,
    recId ?? '',
    Boolean(runId && recId),
    channel,
    'product',
  );

  const openLines = open.data?.lines ?? [];
  const historyLines = history.data?.history_lines ?? [];
  const openLabel =
    channel === 'project'
      ? `Order inquiries (${fmtInt(openLines.length)} open)`
      : `Open sales orders (${fmtInt(openLines.length)})`;
  const docHeader = channel === 'project' ? 'Inquiry' : 'Sales order';
  const dateHeader = channel === 'project' ? 'Needed' : 'Required';

  return (
    <Tabs defaultValue="open">
      <TabsList>
        <TabsTrigger value="open">{openLabel}</TabsTrigger>
        <TabsTrigger value="history">
          {`SO history (${fmtInt(history.data?.history_total ?? historyLines.length)})`}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="open">
        <DocTable>
          <thead>
            <tr className="border-b">
              <Th>{docHeader}</Th>
              <Th>Customer</Th>
              <Th>Project</Th>
              <Th>Agent</Th>
              <Th right>Price</Th>
              <Th right>Qty</Th>
              <Th right>{dateHeader}</Th>
            </tr>
          </thead>
          <tbody>
            {open.isLoading ? (
              <LoadingRows colSpan={7} />
            ) : openLines.length === 0 ? (
              <EmptyRow colSpan={7}>Nothing open on this channel for this product.</EmptyRow>
            ) : (
              openLines.map((l, i) => (
                <tr key={`${l.so_number}-${i}`} className="border-b last:border-0">
                  <Td>{l.so_number}</Td>
                  <Td title={l.customer_label}>
                    <span className="block max-w-56 truncate">{l.customer_label}</span>
                  </Td>
                  <Td title={l.project_title ?? undefined}>
                    <span className="block max-w-56 truncate">
                      {textCell(l.project_title ?? null)}
                    </span>
                  </Td>
                  <Td>{textCell(l.agent_label)}</Td>
                  <Td right>{priceCell(l.unit_price)}</Td>
                  <Td right>{fmtInt(l.qty)}</Td>
                  <Td right>{fmtDate(l.required_date)}</Td>
                </tr>
              ))
            )}
          </tbody>
        </DocTable>
      </TabsContent>

      <TabsContent value="history">
        <DocTable>
          <thead>
            <tr className="border-b">
              <Th>Sales order</Th>
              <Th>Customer</Th>
              <Th>Project</Th>
              <Th>Agent</Th>
              <Th right>Price</Th>
              <Th right>Qty</Th>
              <Th right>Date</Th>
            </tr>
          </thead>
          <tbody>
            {history.isLoading ? (
              <LoadingRows colSpan={7} />
            ) : historyLines.length === 0 ? (
              <EmptyRow colSpan={7}>No orders on this channel in the window.</EmptyRow>
            ) : (
              historyLines.map((l, i) => (
                <tr key={`${l.so_number}-${i}`} className="border-b last:border-0">
                  <Td>{l.so_number}</Td>
                  <Td title={l.customer_label}>
                    <span className="block max-w-56 truncate">{l.customer_label}</span>
                  </Td>
                  <Td title={l.project_title ?? undefined}>
                    <span className="block max-w-56 truncate">
                      {textCell(l.project_title ?? null)}
                    </span>
                  </Td>
                  <Td>{textCell(l.agent_label)}</Td>
                  <Td right>{priceCell(l.unit_price)}</Td>
                  <Td right>{fmtInt(l.qty)}</Td>
                  <Td right>{fmtDate(l.order_date)}</Td>
                </tr>
              ))
            )}
          </tbody>
        </DocTable>
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// On hand - the site pool's stock, row by row, with the documents under each
// ---------------------------------------------------------------------------

function OnHandTable({ line }: { line: PlanLine }) {
  const productId = line.product_id;
  const stock = useLocationStock(productId, Boolean(productId));
  const [openRow, setOpenRow] = useState<string | null>(null);

  /**
   * The SITE POOL rows only (R12/R15) - never a project bin, which holds stock already
   * spoken for by an Order Inquiry and would double-count against the plan's own netting.
   *
   * A response with no pool row at all falls back to everything it was given, rather than
   * showing an empty table for a product that plainly has stock somewhere.
   */
  const rows = useMemo(() => {
    const locations = stock.data?.locations ?? [];
    const pools = locations.filter((l) => l.is_pool);
    return pools.length ? pools : locations;
  }, [stock.data]);

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
            rows.map((loc) => {
              const expanded = openRow === loc.warehouse_id;
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
                      {loc.po_qty === null || loc.po_qty === undefined ? (
                        <span className="text-muted-foreground">{EM_DASH}</span>
                      ) : (
                        fmtInt(loc.po_qty)
                      )}
                    </Td>
                  </tr>
                  {expanded && productId ? (
                    <tr>
                      <td colSpan={9} className="bg-muted/30 p-0">
                        <StockDocumentsPanel
                          productId={productId}
                          warehouseId={loc.warehouse_id}
                          itemCode={line.sku}
                          locationCode={loc.warehouse_code ?? EM_DASH}
                        />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })
          )}
        </tbody>
      </DocTable>
      {/* R7: the newest `stock.updated_at` for the product (or the last stock upload),
          never the moment this dialog asked. */}
      {stock.data?.as_of ? (
        <p className="text-2xs text-muted-foreground">
          Stock as of {formatDateTimeInMalaysia(stock.data.as_of)}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SPO - what is on the water for the pool
// ---------------------------------------------------------------------------

function SpoTabs({ line, runId }: { line: PlanLine; runId: string | null }) {
  const productId = line.product_id;
  const pool = poolLocationLabel(line);
  const spo = useQuery({
    queryKey: ['plan-lines', runId, 'spo-history', productId],
    queryFn: () => getSpoHistory(runId as string, productId as string),
    enabled: Boolean(runId && productId),
    retry: false,
  });

  const open = spo.data?.open ?? [];
  const history = spo.data?.history ?? [];

  const body = (shipments: typeof open, emptyText: string) => (
    <DocTable>
      <thead>
        <tr className="border-b">
          <Th>SPO</Th>
          <Th>Supplier</Th>
          <Th right>Qty</Th>
          <Th right>Received</Th>
          <Th right>ETA</Th>
          <Th right>Arrived</Th>
          <Th>Status</Th>
        </tr>
      </thead>
      <tbody>
        {spo.isLoading ? (
          <LoadingRows colSpan={7} />
        ) : shipments.length === 0 ? (
          <EmptyRow colSpan={7}>{emptyText}</EmptyRow>
        ) : (
          shipments.map((s) => (
            <tr key={s.spo_number} className="border-b last:border-0">
              <Td>{s.spo_number}</Td>
              <Td>{textCell(s.supplier_name)}</Td>
              <Td right>{fmtInt(s.qty)}</Td>
              <Td right>{fmtInt(s.received_qty)}</Td>
              <Td right>{fmtDate(s.eta)}</Td>
              <Td right>{fmtDate(s.arrived_at)}</Td>
              <Td>{s.status}</Td>
            </tr>
          ))
        )}
      </tbody>
    </DocTable>
  );

  return (
    <Tabs defaultValue="open">
      <TabsList>
        <TabsTrigger value="open">{`Open${toPool(pool)} (${fmtInt(open.length)})`}</TabsTrigger>
        <TabsTrigger value="history">
          {`History${toPool(pool)} (${fmtInt(history.length)})`}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="open">
        {body(open, `Nothing on the water${toPool(pool)}.`)}
      </TabsContent>
      <TabsContent value="history">
        {body(history, `No shipment has landed${toPool(pool)} for this product.`)}
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------
// PO - what is already ordered, and what we have ordered before
// ---------------------------------------------------------------------------

function PoTabs({
  line,
  runId,
  poReceipts,
}: {
  line: PlanLine;
  runId: string | null;
  poReceipts: PoReceipt[];
}) {
  const productId = line.product_id;
  const pool = poolLocationLabel(line);
  const history = useQuery({
    queryKey: ['plan-lines', runId, 'po-history', productId, pool],
    queryFn: () => getPoHistoryToPool(runId as string, productId as string, pool),
    enabled: Boolean(runId && productId),
    retry: false,
  });

  const historyLines = history.data?.history ?? [];

  return (
    <Tabs defaultValue="open">
      <TabsList>
        <TabsTrigger value="open">
          {`Open${toPool(pool)} (${fmtInt(poReceipts.length)})`}
        </TabsTrigger>
        <TabsTrigger value="history">
          {`History${toPool(pool)} (${fmtInt(historyLines.length)})`}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="open">
        {/* The open PO book carries the document, what is still to come and when - it is a
            netting source, not a price record, so it names no supplier or unit price. Those
            two columns belong to the History tab, which reads the purchase records. */}
        <DocTable>
          <thead>
            <tr className="border-b">
              <Th>PO</Th>
              <Th right>Still to come</Th>
              <Th right>ETA</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {poReceipts.length === 0 ? (
              <EmptyRow colSpan={4}>{`Nothing on order${toPool(pool)}.`}</EmptyRow>
            ) : (
              poReceipts.map((r, i) => (
                <tr key={`${r.po_number}-${i}`} className="border-b last:border-0">
                  <Td>{textCell(r.po_number)}</Td>
                  <Td right>{fmtInt(r.remaining)}</Td>
                  <Td right>{fmtDate(r.expected_date)}</Td>
                  <Td>{r.status}</Td>
                </tr>
              ))
            )}
          </tbody>
        </DocTable>
      </TabsContent>

      <TabsContent value="history">
        <DocTable>
          <thead>
            <tr className="border-b">
              <Th>PO</Th>
              <Th>Supplier</Th>
              <Th right>Qty</Th>
              <Th right>Unit price</Th>
              <Th right>Issued</Th>
              <Th right>ETA</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {history.isLoading ? (
              <LoadingRows colSpan={7} />
            ) : historyLines.length === 0 ? (
              <EmptyRow colSpan={7}>
                {pool
                  ? `No purchase order raised here names ${pool} as its destination.`
                  : 'No purchase order raised here names this product.'}
              </EmptyRow>
            ) : (
              historyLines.map((l) => (
                <tr key={l.po_number} className="border-b last:border-0">
                  <Td>{l.po_number}</Td>
                  <Td>{textCell(l.supplier_name)}</Td>
                  <Td right>{fmtInt(l.qty)}</Td>
                  <Td right>
                    {l.unit_cost === null ? (
                      <span className="text-muted-foreground">{EM_DASH}</span>
                    ) : (
                      fmtSupplierCost(l.unit_cost, l.currency)
                    )}
                  </Td>
                  <Td right>{fmtDate(l.issued_at)}</Td>
                  <Td right>{fmtDate(l.eta)}</Td>
                  <Td>{l.status}</Td>
                </tr>
              ))
            )}
          </tbody>
        </DocTable>
      </TabsContent>
    </Tabs>
  );
}

// ---------------------------------------------------------------------------

const TITLES: Record<PlanDialogKind, string> = {
  suggested: 'Suggested qty',
  project: 'Project demand',
  retail: 'Retail demand',
  on_hand: 'On hand',
  spo: 'SPO',
  po: 'PO',
};

/**
 * The one dialog the grid mounts. `request` names which number was pressed and on which
 * row; closing it clears the request.
 *
 * `ledger` is passed in rather than built here: the Suggested-qty body is the existing
 * `OrderQtyLedger`, which needs the whole plan context (cover, PO book, economics, trend)
 * that only the grid holds. One body, two containers - it was a popover, it is a dialog.
 */
export function PlanRowDialog({
  request,
  onOpenChange,
  runId,
  ledger,
  poReceipts = [],
}: {
  request: PlanDialogRequest | null;
  onOpenChange: (open: boolean) => void;
  runId: string | null;
  ledger?: React.ReactNode;
  poReceipts?: PoReceipt[];
}) {
  if (!request) return null;
  const { kind, line } = request;
  const pool = poolLocationLabel(line);
  const title =
    (kind === 'po' || kind === 'spo') && pool
      ? `${TITLES[kind]} - ${line.sku} - to ${pool}`
      : `${TITLES[kind]} - ${line.sku}`;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-[95vw]">
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">{title}</DialogTitle>
          {/* The product name IS the description - Radix wants one, and a second sentence
              explaining the dialog would be an on-screen explanation. */}
          <DialogDescription className="truncate text-xs" title={line.product_name}>
            {line.product_name}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {kind === 'suggested' ? (
            ledger ?? <p className="text-sm text-muted-foreground">Nothing to explain here.</p>
          ) : kind === 'project' || kind === 'retail' ? (
            <DemandTabs line={line} runId={runId} channel={kind} />
          ) : kind === 'on_hand' ? (
            <OnHandTable line={line} />
          ) : kind === 'spo' ? (
            <SpoTabs line={line} runId={runId} />
          ) : (
            <PoTabs line={line} runId={runId} poReceipts={poReceipts} />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
