/**
 * SCM S4 - Phase 1 fixture for the PO creation worklist.
 *
 * Phase 2 flips `USE_PO_WORKLIST_MOCKS` to false and DELETES this file. Nothing
 * imports it except `poWorklistService` and its own tests.
 *
 * Every figure is shaped after the real database rather than invented: product codes
 * (`C-FH24`, `SRTWC8613-RL`, `SRTWB1514-FULL GLAZE`), the suppliers that actually
 * carry them, and the costs those links hold. Two facts from the live book are
 * deliberately reproduced because they are the states the screen has to handle and
 * the ones a made-up fixture would never contain:
 *
 * - **Most rows have no need-by date.** The committed order book is 17 sales
 *     orders, so almost nothing is dated-short: the buy is a policy replenishment.
 *     A fixture where every row has a need-by would let the null path ship untested.
 * - **On-time rate and lead time are frequently unknown**, because
 *     `scm.supplier_performance` is empty. Lead time then falls back to the supplier
 *     link's standard figure, and where even that is missing the place-by date cannot
 *     be derived at all.
 *
 * The rows are chosen so every state in Group E2 is reachable by clicking:
 *
 * - `SRTWC8613-RL`   keyed already, by a named person at a time.
 * - `C-FH24`         not keyed, no need-by (policy buy), so no place-by either.
 * - `SRTWB1514-FULL GLAZE`  LATE: dated short next week against a 45-day lead, so
 *                      the place-by date is a month in the past.
 * - `SRTWT7408`      chosen ZERO - the use-pool decision, present and saying no PO
 *                      is needed (AC-E2.5).
 * - `ACC6002`        keying, mid-flight, which is what stops two people keying it.
 * - `SRT367-GM`      no lead time recorded anywhere, so place-by is null even though
 *                      need-by is not.
 */
import { frontPlanningScenario, runGrainFields } from './frontPlanningMockStore';
import type {
  KeyedStatus,
  KeyedStatusInput,
  KeyedStatusResult,
  PoWorklist,
  PoWorklistRow,
} from '../types/poWorklist.types';

/**
 * Phase-2: OFF. The service reads the real `/api/v1/scm/po-worklist` routes; the
 * fixtures below stay as the data the vitest specs are written against.
 */
export const USE_PO_WORKLIST_MOCKS = false;

/** The date every ageing and lateness figure below is counted to. */
const AS_OF = '2026-08-04';
const RUN_ID = 'run-2026-w32';

function iso(daysFromAsOf: number): string {
  const d = new Date(`${AS_OF}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + daysFromAsOf);
  return d.toISOString().slice(0, 10);
}

const ROWS: PoWorklistRow[] = [
  {
    product_code: 'SRTWC8613-RL',
    product_name: 'Wall hung WC, rimless',
    uom: 'UNIT',
    chosen_qty: 224,
    suggested_qty: 224,
    chosen_supplier_code: 'FOSHAN-CF',
    chosen_supplier_name: 'Foshan Ceramic Fixtures Co Ltd',
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:14:00`,
    need_by: iso(70),
    place_by: iso(25),
    lead_time_days: 45,
    is_late: false,
    last_po_cost: 1011,
    last_po_currency: 'MYR',
    cash_committed: 226464,
    keyed_status: 'keyed',
    keyed_by: 'Joey',
    keyed_at: `${AS_OF}T10:02:00`,
    uom_decimal_places: 0,
    // The product decision's split back to locations (AC-F08). Sums to 224.
    location_allocations: [
      { warehouse_code: 'BRW', warehouse_name: 'Bandar Baru Warehouse', allocated_qty: 160 },
      { warehouse_code: 'JB', warehouse_name: 'Johor Bahru Branch', allocated_qty: 64 },
    ],
  },
  {
    product_code: 'C-FH24',
    product_name: 'Flush handle, chrome',
    uom: 'L',
    chosen_qty: 1820,
    suggested_qty: 1820,
    chosen_supplier_code: 'SEL-SW',
    chosen_supplier_name: 'Selangor Sanitaryware Trading',
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:20:00`,
    // No committed order is uncovered, so there is no date the stock is needed BY.
    // The buy is the reorder policy replenishing against forecast history.
    need_by: null,
    place_by: null,
    lead_time_days: 14,
    is_late: false,
    last_po_cost: 10.2,
    last_po_currency: 'MYR',
    cash_committed: 18564,
    keyed_status: 'not_keyed',
    keyed_by: null,
    keyed_at: null,
  },
  {
    product_code: 'SRTWB1514-FULL GLAZE',
    product_name: 'Wash basin 1514, full glaze',
    uom: 'UNIT',
    chosen_qty: 908,
    suggested_qty: 908,
    chosen_supplier_code: 'JOHOR-BD',
    chosen_supplier_name: 'Johor Bathware Distributors Sdn Bhd',
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:31:00`,
    // Needed in a week against a 45-day lead: the order had to be placed five weeks
    // ago. Flagged, not silently listed alongside the ones that are still in time.
    need_by: iso(7),
    place_by: iso(-38),
    lead_time_days: 45,
    is_late: true,
    last_po_cost: 390,
    last_po_currency: 'MYR',
    cash_committed: 354120,
    keyed_status: 'not_keyed',
    keyed_by: null,
    keyed_at: null,
    uom_decimal_places: 0,
    location_allocations: [
      { warehouse_code: 'BRW', warehouse_name: 'Bandar Baru Warehouse', allocated_qty: 700 },
      { warehouse_code: 'IPH', warehouse_name: 'Ipoh Branch', allocated_qty: 208 },
    ],
  },
  {
    product_code: 'SRTWT7408',
    product_name: 'WC tank 7408',
    uom: 'UNIT',
    // The use-pool decision (AC-E2.5). 4,397 units sit in the BRW pool against demand
    // of 67, so buying is the wrong answer. The row EXISTS saying so: filtered out, it
    // would be indistinguishable from a decision nobody made.
    chosen_qty: 0,
    suggested_qty: 67,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:38:00`,
    need_by: iso(21),
    place_by: null,
    lead_time_days: null,
    is_late: false,
    last_po_cost: null,
    last_po_currency: null,
    cash_committed: null,
    keyed_status: 'not_keyed',
    keyed_by: null,
    keyed_at: null,
  },
  {
    product_code: 'ACC6002',
    product_name: 'Accessory pack 6002',
    uom: 'UNIT',
    chosen_qty: 839,
    suggested_qty: 839,
    chosen_supplier_code: 'GZ-SI',
    chosen_supplier_name: 'Guangzhou Sanitary Imports Ltd',
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:44:00`,
    need_by: null,
    place_by: null,
    lead_time_days: 45,
    is_late: false,
    last_po_cost: 12.5,
    last_po_currency: 'CNY',
    cash_committed: 10487.5,
    // Mid-flight. The whole point of a third value: it stops two people keying the
    // same purchase order.
    keyed_status: 'keying',
    keyed_by: 'Joey',
    keyed_at: `${AS_OF}T11:15:00`,
  },
  {
    product_code: 'SRT367-GM',
    product_name: 'Trap 367, gunmetal',
    uom: 'UNIT',
    chosen_qty: 22,
    suggested_qty: 22,
    chosen_supplier_code: 'KLANG-KS',
    chosen_supplier_name: 'Kilang Seramik Klang Sdn Bhd',
    decided_by: 'Mr Loo',
    decided_at: `${AS_OF}T09:51:00`,
    need_by: iso(30),
    // Dated short, but no lead time is recorded anywhere for this supplier and item,
    // so the place-by date cannot be derived. Guessing one would be acted on.
    place_by: null,
    lead_time_days: null,
    is_late: false,
    last_po_cost: 42,
    last_po_currency: 'MYR',
    cash_committed: 924,
    keyed_status: 'not_keyed',
    keyed_by: null,
    keyed_at: null,
  },
];

/**
 * Mutated by the mock keyed-status write so the prototype behaves like the real thing.
 * Keyed by product AND location, because a location-grain row is its own purchase
 * order and keying one location must leave the product's other locations alone.
 */
const state = new Map<string, Pick<PoWorklistRow, 'keyed_status' | 'keyed_by' | 'keyed_at'>>(
  ROWS.map((r) => [
    stateKey(r.product_code, null),
    { keyed_status: r.keyed_status, keyed_by: r.keyed_by, keyed_at: r.keyed_at },
  ]),
);

function stateKey(productCode: string, warehouseCode: string | null | undefined): string {
  return warehouseCode ? `${productCode}:${warehouseCode}` : productCode;
}

function delay<T>(value: T): Promise<T> {
  return Promise.resolve(value);
}

/**
 * The worklist reads ONE grain, the run's own (AC-F09).
 *
 * Under `product` the rows are the product decisions and each carries its split
 * back to locations. Under `location` the same decisions arrive as per-location
 * recommendation rows instead - one row per location, named by warehouse - and no
 * split, because the location IS the row. Neither shape carries a channel key.
 */
function scenarioRows(): PoWorklistRow[] {
  return shapeRows().map((r) => ({
    ...r,
    ...(state.get(stateKey(r.product_code, r.warehouse_code)) ?? {}),
  }));
}

function shapeRows(): PoWorklistRow[] {
  const rows = ROWS.map((r) => ({ ...r }));
  const grain = runGrainFields().decision_grain;
  if (frontPlanningScenario() === 'legacy') {
    return rows.map((r) => ({ ...r, location_allocations: null }));
  }
  if (grain !== 'location') return rows;
  return rows.flatMap((r) => {
    const split = r.location_allocations ?? [];
    if (split.length === 0) {
      return [
        {
          ...r,
          warehouse_code: 'BRW',
          warehouse_name: 'Bandar Baru Warehouse',
          location_allocations: null,
        },
      ];
    }
    return split.map((a) => ({
      ...r,
      chosen_qty: a.allocated_qty,
      suggested_qty: a.allocated_qty,
      warehouse_code: a.warehouse_code,
      warehouse_name: a.warehouse_name,
      location_allocations: null,
    }));
  });
}

export function mockPoWorklist(): Promise<PoWorklist> {
  const grain = runGrainFields();
  return delay({
    run_id: RUN_ID,
    as_of: AS_OF,
    decision_grain: grain.decision_grain,
    front_planning_contract_version: grain.front_planning_contract_version,
    rows: scenarioRows(),
  });
}

export function mockSetKeyedStatus(
  productCode: string,
  input: KeyedStatusInput,
): Promise<KeyedStatusResult> {
  const at = `${AS_OF}T12:00:00`;
  state.set(stateKey(productCode, input.warehouse_code), {
    keyed_status: input.keyed_status,
    keyed_by: 'Joey',
    keyed_at: at,
  });
  return delay({
    product_code: productCode,
    warehouse_code: input.warehouse_code ?? null,
    keyed_status: input.keyed_status,
    keyed_by: 'Joey',
    keyed_at: at,
  });
}

/** How many decided rows are still to be keyed, for the tile. */
export const MOCK_PO_WORKLIST_PENDING = ROWS.filter(
  (r) => r.keyed_status !== 'keyed',
).length;

export const MOCK_KEYED_STATUSES: KeyedStatus[] = ['not_keyed', 'keying', 'keyed'];
