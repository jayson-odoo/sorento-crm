/**
 * The stock table, read against AutoCount (STOCK-STATUS round 6; owner OK of mock v6, 18 Oct
 * 07:56; UAC AC-31, AC-32).
 *
 * Today's rows and sets stay as they are. On hand, SO qty, PO qty and SPO qty read AutoCount's
 * figures (`GET /api/v1/inventory/stock-status`); Available, each set's net and a site pool's
 * Available for Project follow from them by today's arithmetic. Every location AutoCount holds
 * that the table does not list joins after today's rows as an "Other group" row, in AutoCount's
 * order. Display only: what the planner confirms against is still the server's own figures.
 */
import type { BoardCellLocation } from '../types/fulfilmentPlanning.types';
import type { StockStatus, StockStatusLocation } from '@/components/stock-status/stockStatus.types';
import { availableForProject, POOLS_SET } from './poolShare';
import { groupOfWarehouseCode } from './supplyVocabulary';
import { fromMinor, toMinor } from './supplyComposition';

/** On hand - SO + SPO, signed: today's Available (PO qty stays outside it). */
function availableOf(loc: Pick<StockStatusLocation, 'on_hand' | 'so_qty' | 'spo_qty'> | null): string {
  if (!loc) return '0';
  return fromMinor(toMinor(loc.on_hand) - toMinor(loc.so_qty) + toMinor(loc.spo_qty));
}

function figuresOf(loc: StockStatusLocation | null) {
  return {
    qty_on_hand: fromMinor(toMinor(loc?.on_hand ?? 0)),
    so_qty: fromMinor(toMinor(loc?.so_qty ?? 0)),
    po_open_qty: fromMinor(toMinor(loc?.po_qty ?? 0)),
    spo_qty: fromMinor(toMinor(loc?.spo_qty ?? 0)),
    available_qty: availableOf(loc),
  };
}

export function withAutoCount(
  rows: readonly BoardCellLocation[],
  status: StockStatus,
  poolSharePct?: number | null,
): BoardCellLocation[] {
  const byCode = new Map(status.locations.map((loc) => [loc.warehouse_code, loc]));
  const listed = new Set(rows.map((row) => row.location).filter(Boolean));
  const unlisted = status.locations.filter((loc) => !listed.has(loc.warehouse_code));

  // A location of a group the table already nets (an IB warehouse the rows left out) belongs
  // to that set: it joins once, after the set's LAST row (a set can arrive as two runs), and
  // the set's net counts it. Inactive ones stay out: the server's own set lists active
  // warehouses only, so its documents would not reach a folded-in inactive one.
  const lastOfSet = new Map<string, number>();
  rows.forEach((row, index) => {
    if (row.net_of && row.net_of !== POOLS_SET) lastOfSet.set(row.net_of, index);
  });
  const joinsSet = (loc: StockStatusLocation) => {
    const group = groupOfWarehouseCode(loc.warehouse_code);
    return loc.is_active !== false && group && lastOfSet.has(group) ? group : null;
  };
  const rowOf = (loc: StockStatusLocation, extra: Partial<BoardCellLocation>): BoardCellLocation => ({
    location: loc.warehouse_code,
    where: 'other_group',
    product_id: status.product_id,
    warehouse_id: loc.warehouse_id,
    qty: '0',
    ...extra,
    ...figuresOf(loc),
  });

  const overlaid: BoardCellLocation[] = [];
  rows.forEach((row, index) => {
    overlaid.push(row.location ? { ...row, ...figuresOf(byCode.get(row.location) ?? null) } : row);
    const set = row.net_of;
    if (!set || lastOfSet.get(set) !== index) return;
    for (const loc of unlisted) {
      if (joinsSet(loc) === set) overlaid.push(rowOf(loc, { where: 'group', net_of: set }));
    }
  });

  const netBySet = new Map<string, number>();
  for (const row of overlaid) {
    if (!row.location || !row.net_of) continue;
    netBySet.set(row.net_of, (netBySet.get(row.net_of) ?? 0) + toMinor(row.available_qty));
  }

  const restated = overlaid.map((row) => {
    if (!row.location || !row.net_of) return row;
    const net = fromMinor(netBySet.get(row.net_of) ?? 0);
    return row.where === 'site_pool'
      ? { ...row, net, available_for_project: availableForProject(row.available_qty, net, poolSharePct) ?? '0' }
      : { ...row, net };
  });

  // Everything else is outside every set the table nets: today's "Other group" rows. Beside
  // today's rows their set states its own net, so it carries an "Other group subtotal" even
  // when only one joins; alone (the stand-alone page) the table is AutoCount's list and Total.
  const outside = unlisted.filter((loc) => !joinsSet(loc));
  const othersNet =
    rows.length > 0 ? fromMinor(outside.reduce((total, loc) => total + toMinor(availableOf(loc)), 0)) : null;
  return [...restated, ...outside.map((loc) => rowOf(loc, othersNet === null ? {} : { net: othersNet }))];
}
