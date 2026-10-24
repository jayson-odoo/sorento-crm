/**
 * The stock table's Group by (STOCK-GROUPBY): the lines AutoCount's read is made of, the six
 * dimensions they group by, the four measures the group rows sum, and the level list the
 * browser remembers. Display only; the read itself is unchanged.
 */
import type { StockStatus } from '@/components/stock-status/stockStatus.types';
import type { GroupByOption } from '@/components/common/group-by/GroupByMenu';
import type { GroupDimension, GroupNode, Measure } from '@/components/common/group-by/groupByLevels';
import { spoDetailHref } from '@/lib/spo-detail';
import { fromMinor, toMinor } from './supplyComposition';

export type StockLineType = 'On hand' | 'S/O' | 'PO' | 'SPO';

export interface StockLine {
  key: string;
  type: StockLineType;
  location: string;
  customer: string | null;
  project: string | null;
  agent: string | null;
  supplier: string | null;
  docNo: string | null;
  href: string | null;
  date: string | null;
  onHand: string;
  so: string;
  spo: string;
  po: string;
}

/** On hand, S/O, SPO, PO: the order the table's columns read in. */
const TYPE_ORDER: StockLineType[] = ['On hand', 'S/O', 'SPO', 'PO'];

const clean = (value: string | null | undefined): string | null => value?.trim() || null;
const qty = (value: number | string): string => fromMinor(toMinor(value));

/** One line per document row and per non-zero on hand location; Incoming PL is never a line. */
export function stockLinesOf(status: StockStatus, locationOrder: readonly string[]): StockLine[] {
  const codeOf = new Map(status.locations.map((loc) => [loc.warehouse_id, loc.warehouse_code]));
  const blank = { customer: null, project: null, agent: null, supplier: null, docNo: null, href: null, date: null };
  const zero = { onHand: '0', so: '0', spo: '0', po: '0' };
  const lines: StockLine[] = [];
  for (const loc of status.locations) {
    if (toMinor(loc.on_hand) === 0) continue;
    lines.push({
      ...blank,
      ...zero,
      key: `on-hand:${loc.warehouse_id}`,
      type: 'On hand',
      location: loc.warehouse_code,
      onHand: qty(loc.on_hand),
    });
  }
  for (const so of status.sales_orders) {
    lines.push({
      ...blank,
      ...zero,
      key: `so:${so.line_id}`,
      type: 'S/O',
      location: codeOf.get(so.warehouse_id) ?? '',
      customer: clean(so.debtor_name) ?? clean(so.debtor_code),
      project: clean(so.project_label),
      agent: clean(so.salesperson),
      docNo: so.so_number,
      href: `/scm/sales-orders/${so.sales_order_id}`,
      date: so.due_date,
      so: qty(so.qty),
    });
  }
  for (const po of status.purchase_orders) {
    lines.push({
      ...blank,
      ...zero,
      key: `po:${po.line_id}`,
      type: 'PO',
      location: codeOf.get(po.warehouse_id) ?? '',
      supplier: clean(po.supplier_name) ?? clean(po.supplier_code),
      docNo: po.po_number,
      href: `/scm/purchase-orders/${po.purchase_order_id}`,
      date: po.expected_date,
      po: qty(po.qty),
    });
  }
  for (const spo of status.spos) {
    lines.push({
      ...blank,
      ...zero,
      key: `spo:${spo.allocation_id}`,
      type: 'SPO',
      location: codeOf.get(spo.warehouse_id) ?? '',
      supplier: clean(spo.supplier_name) ?? clean(spo.supplier_code),
      docNo: spo.spo_number,
      href: spoDetailHref(spo.spo_number),
      date: spo.arrival_date,
      spo: qty(spo.qty),
    });
  }
  const rank = locationRank(locationOrder);
  // Array.sort is stable, so ties keep the read's own (due / expected date) order.
  return lines.sort((a, b) => {
    const ra = rank(a.location);
    const rb = rank(b.location);
    if (ra !== rb) return ra < rb ? -1 : 1;
    if (a.location !== b.location) return a.location < b.location ? -1 : 1;
    return TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type);
  });
}

/** A location's place in the table's own order; one the table does not list goes after. */
function locationRank(order: readonly string[]) {
  return (code: string) => {
    const at = order.indexOf(code);
    return at < 0 ? Number.POSITIVE_INFINITY : at;
  };
}

export const STOCK_GROUP_OPTIONS: GroupByOption[] = [
  { id: 'location', label: 'Location' },
  { id: 'customer', label: 'Customer' },
  { id: 'project', label: 'Project' },
  { id: 'agent', label: 'Agent' },
  { id: 'supplier', label: 'Supplier' },
  { id: 'type', label: 'Type' },
];

export function stockGroupDimensions(locationOrder: readonly string[]): Record<string, GroupDimension<StockLine>> {
  const inLocationOrder = locationRank(locationOrder);
  const dimension = (
    id: string,
    label: string,
    valueOf: (line: StockLine) => string | null,
    rank?: (value: string) => number,
  ): GroupDimension<StockLine> => ({
    id,
    label,
    noneLabel: `No ${label.toLowerCase()}`,
    valueOf,
    rank,
  });
  return {
    location: dimension('location', 'Location', (l) => l.location, (v) => inLocationOrder(v)),
    customer: dimension('customer', 'Customer', (l) => l.customer),
    project: dimension('project', 'Project', (l) => l.project),
    agent: dimension('agent', 'Agent', (l) => l.agent),
    supplier: dimension('supplier', 'Supplier', (l) => l.supplier),
    type: dimension('type', 'Type', (l) => l.type, (v) => TYPE_ORDER.indexOf(v as StockLineType)),
  };
}

/** Keyed by the table's column keys. */
export const STOCK_LINE_MEASURES: Record<'on-hand' | 'so' | 'spo' | 'po', Measure<StockLine>> = {
  'on-hand': (l) => l.onHand,
  so: (l) => l.so,
  spo: (l) => l.spo,
  po: (l) => l.po,
};

/** Re-roots a subtree under a parent row (`location=BRW-BB/`, `set=IB/`) so keys stay unique. */
export function prefixGroupKeys<T>(nodes: GroupNode<T>[], prefix: string): GroupNode<T>[] {
  return nodes.map((node) => ({
    ...node,
    key: `${prefix}${node.key}`,
    children: prefixGroupKeys(node.children, prefix),
  }));
}

/** Keys of every group (and sub-group) whose lines pass `keep`; all of them when omitted. */
export function groupKeysOf<T>(nodes: GroupNode<T>[], keep?: (line: T) => boolean): string[] {
  return nodes.flatMap((node) =>
    !keep || node.lines.some(keep) ? [node.key, ...groupKeysOf(node.children, keep)] : [],
  );
}

export const STOCK_GROUP_STORAGE_KEY = 'cellStockTable.groupBy';
export const DEFAULT_STOCK_GROUP_LEVELS: readonly string[] = ['location'];

function browserStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** The remembered levels; anything missing, unreadable or invalid is Location alone. */
export function readStockGroupLevels(storage: Storage | null = browserStorage()): string[] {
  try {
    const raw = storage?.getItem(STOCK_GROUP_STORAGE_KEY);
    if (!raw) return [...DEFAULT_STOCK_GROUP_LEVELS];
    const parsed: unknown = JSON.parse(raw);
    const known = new Set(STOCK_GROUP_OPTIONS.map((option) => option.id));
    if (
      Array.isArray(parsed) &&
      parsed.every((id) => typeof id === 'string' && known.has(id)) &&
      new Set(parsed).size === parsed.length
    ) {
      return parsed as string[];
    }
  } catch {
    // Storage disabled or the value is not JSON: fall through to the default.
  }
  return [...DEFAULT_STOCK_GROUP_LEVELS];
}

export function writeStockGroupLevels(
  levels: readonly string[],
  storage: Storage | null = browserStorage(),
): void {
  try {
    storage?.setItem(STOCK_GROUP_STORAGE_KEY, JSON.stringify(levels));
  } catch {
    // Storage disabled: the choice still applies for this session.
  }
}
