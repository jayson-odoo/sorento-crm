/**
 * The Schedule matrix's own read (S3, PLAN-scm-oi-worklist-excel-parity.md).
 *
 * API CONTRACT (Phase 2 target, PLAN section 6):
 *
 *   GET {BASE}/order-inquiries/matrix?axis=product|sales_order|customer|agent
 *       &by=day|week|month|year&<every /order-inquiries list filter>
 *     -> { data: [{ axis_key, axis_label, period, qty, buy, po, spo, rows }] }
 *
 *   One GROUP BY over the same filtered set the list reads - `axis_key`/`axis_label` the
 *   row's value on the chosen axis, `period` the ISO date the bucket starts on (week
 *   buckets start Monday, month/year bucket on the first of the month/year), `qty` the
 *   summed still-owed quantity, `buy`/`po`/`spo` the R-F stage sums, `rows` the COUNT of
 *   worklist rows summed into the cell (never the rows themselves - the drilldown asks
 *   the list again, scoped to this cell's own axis + period). No row cap: the old
 *   client-side matrix built off an unpaged `limit=1000` list fetch, which a
 *   delivery-filtered worklist has already exceeded on prod (PLAN section 0).
 *
 * PHASE 1: no backend route exists yet, so this reads a small fixture and groups it
 * in-process - the SAME shape a real GROUP BY would answer, so `buildOrderInquiryMatrix`
 * and every component above it are built once, against the real contract, and only the
 * body of this one function changes in Phase 2.
 */
import { addDays, endOfMonth, endOfYear, format, startOfMonth, startOfWeek, startOfYear } from 'date-fns';
import type {
  OrderInquiryMatrixAxis,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryMatrixParams,
} from '../types/orderInquiry.types';

/** The bucket a delivery date lands in, at the chosen granularity - date-fns only, the
 * same rule the real GROUP BY states in words above. */
function periodOf(deliveryDate: string, by: OrderInquiryMatrixGranularity): string {
  const date = new Date(`${deliveryDate}T00:00:00`);
  if (by === 'day') return deliveryDate;
  if (by === 'week') return format(startOfWeek(date, { weekStartsOn: 1 }), 'yyyy-MM-dd');
  if (by === 'month') return format(startOfMonth(date), 'yyyy-MM-dd');
  return format(startOfYear(date), 'yyyy-MM-dd');
}

/** The last day a period covers - what a cell's drilldown asks the list for as
 * `delivery_to`. */
export function periodEnd(period: string, by: OrderInquiryMatrixGranularity): string {
  const date = new Date(`${period}T00:00:00`);
  if (by === 'day') return period;
  if (by === 'week') return format(addDays(date, 6), 'yyyy-MM-dd');
  if (by === 'month') return format(endOfMonth(date), 'yyyy-MM-dd');
  return format(endOfYear(date), 'yyyy-MM-dd');
}

interface FixtureRow {
  item_code: string;
  product_name: string;
  so_number: string;
  project_customer: string;
  agent_code: string;
  agent_label: string;
  delivery_date: string;
  qty: number;
  buy: number;
  po: number;
  spo: number;
}

/**
 * PHASE 1 MOCK. A small spread of synthetic rows across products, sales orders,
 * customers, agents and three delivery months (this month, next month, next year) -
 * enough to exercise every axis and every granularity without a backend. Deleted the
 * moment the real endpoint lands.
 */
function fixtureRows(): FixtureRow[] {
  const today = new Date();
  const thisMonth = format(today, 'yyyy-MM-15');
  const nextMonth = format(addDays(today, 35), 'yyyy-MM-15');
  const nextYear = format(addDays(today, 380), 'yyyy-MM-15');
  return [
    {
      item_code: 'CKSW015',
      product_name: 'Composite kitchen sink, white',
      so_number: '202609-S0041',
      project_customer: 'TUJU RESIDENCE',
      agent_code: 'AG01',
      agent_label: 'Nurul Aina',
      delivery_date: thisMonth,
      qty: 20,
      buy: 8,
      po: 7,
      spo: 5,
    },
    {
      item_code: 'CKSW015',
      product_name: 'Composite kitchen sink, white',
      so_number: '202609-S0055',
      project_customer: 'BUIMACO',
      agent_code: 'AG02',
      agent_label: 'Farid Rahman',
      delivery_date: nextMonth,
      qty: 12,
      buy: 12,
      po: 0,
      spo: 0,
    },
    {
      item_code: 'TW-1050',
      product_name: 'Thermostatic mixer valve',
      so_number: '202610-S0012',
      project_customer: 'SETIA GREEN',
      agent_code: 'AG01',
      agent_label: 'Nurul Aina',
      delivery_date: nextMonth,
      qty: 30,
      buy: 0,
      po: 30,
      spo: 0,
    },
    {
      item_code: 'TW-1050',
      product_name: 'Thermostatic mixer valve',
      so_number: '202611-S0003',
      project_customer: 'TUJU RESIDENCE',
      agent_code: 'AG03',
      agent_label: 'Wei Ling',
      delivery_date: nextYear,
      qty: 18,
      buy: 3,
      po: 0,
      spo: 15,
    },
    {
      item_code: 'SC-RL-BLK',
      product_name: 'Rail set, black',
      so_number: '202610-S0028',
      project_customer: 'BUIMACO',
      agent_code: 'AG02',
      agent_label: 'Farid Rahman',
      delivery_date: thisMonth,
      qty: 45,
      buy: 10,
      po: 20,
      spo: 15,
    },
  ];
}

/** How one row is keyed and labelled on each axis - the client's own read of the SAME
 * rule the real GROUP BY runs. */
function axisKeyOf(row: FixtureRow, axis: OrderInquiryMatrixAxis) {
  if (axis === 'sales_order') return { key: row.so_number, label: row.so_number };
  if (axis === 'customer') return { key: row.project_customer, label: row.project_customer };
  if (axis === 'agent') return { key: row.agent_code, label: row.agent_code };
  return { key: row.item_code, label: row.item_code };
}

function matchesQuery(row: FixtureRow, query?: string): boolean {
  if (!query) return true;
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [row.item_code, row.so_number, row.project_customer, row.agent_code, row.agent_label]
    .join(' ')
    .toLowerCase()
    .includes(needle);
}

/**
 * The matrix cells for one axis/granularity/filter set. `data` only - the same envelope
 * shape the real route will answer with, so the caller never has to know this is a
 * fixture.
 */
export async function getOrderInquiryMatrix(
  params: OrderInquiryMatrixParams,
): Promise<{ data: OrderInquiryMatrixCell[] }> {
  const rows = fixtureRows().filter((row) => matchesQuery(row, params.query));
  const cellMap = new Map<
    string,
    { axis_key: string; axis_label: string; period: string; qty: number; buy: number; po: number; spo: number; rows: number }
  >();
  for (const row of rows) {
    const { key, label } = axisKeyOf(row, params.axis);
    const period = periodOf(row.delivery_date, params.by);
    const cellKey = `${key}|${period}`;
    const existing = cellMap.get(cellKey);
    if (existing) {
      existing.qty += row.qty;
      existing.buy += row.buy;
      existing.po += row.po;
      existing.spo += row.spo;
      existing.rows += 1;
    } else {
      cellMap.set(cellKey, {
        axis_key: key,
        axis_label: label,
        period,
        qty: row.qty,
        buy: row.buy,
        po: row.po,
        spo: row.spo,
        rows: 1,
      });
    }
  }
  const data: OrderInquiryMatrixCell[] = [...cellMap.values()]
    .sort((a, b) => a.axis_label.localeCompare(b.axis_label) || a.period.localeCompare(b.period))
    .map((cell) => ({
      axis_key: cell.axis_key,
      axis_label: cell.axis_label,
      period: cell.period,
      qty: String(cell.qty),
      buy: String(cell.buy),
      po: String(cell.po),
      spo: String(cell.spo),
      rows: cell.rows,
    }));
  return { data };
}
