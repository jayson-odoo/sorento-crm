'use client';

/**
 * A toggleable fixture so every state of this screen can be looked at without a backend.
 *
 * Add `?demo=<state>` to the URL. Nothing here runs unless that param is present, and the
 * real hooks stay wired underneath: the components ask for the demo override first and fall
 * back to the live query, so removing the param is the only thing needed to see live data.
 *
 * The fixture is shaped on the client's own `delivery-schedule-buimaco-r1.pdf`: 12 TOWER
 * phases plus 3 unlabeled COMMON AREA rows, six product columns in the customer's `BUI-HB-*`
 * codes, four of which reconcile on the first pass. That ratio is the point of the screen.
 */
import { useSearchParams } from 'next/navigation';
import type {
  DeliverySchedule,
  DeliveryScheduleCell,
  DeliverySchedulePhase,
  DeliveryScheduleProduct,
  DeliveryScheduleVersion,
  DeliveryScheduleVersionSummary,
} from '../../../_shared/types/deliverySchedule.types';

export const DEMO_PARAM = 'demo';

export const DEMO_STATES = [
  'loading',
  'empty',
  'error',
  'queued',
  'running',
  'partial',
  'failed',
  'data',
  'confirmed',
] as const;

export type DemoState = (typeof DEMO_STATES)[number];

export function useDemoScheduleState(): DemoState | null {
  const searchParams = useSearchParams();
  const raw = searchParams?.get(DEMO_PARAM);
  if (!raw) return null;
  return (DEMO_STATES as readonly string[]).includes(raw) ? (raw as DemoState) : null;
}

// ------------------------------------------------------------------ fixtures

const TOWER_LABELS = [
  'Level 2 & 7',
  'Level 8 & 10',
  'Level 11 to 13',
  'Level 14 to 16',
  'Level 17 to 19',
  'Level 20 to 22',
  'Level 23 to 25',
  'Level 26 to 28',
  'Level 29 to 31',
  'Level 32 to 34',
  'Level 35 to 37',
  'Level 38 to 40',
];

const TOWER_DATES = [
  '2026-07-01',
  '2026-08-03',
  '2026-09-01',
  '2026-10-01',
  '2026-11-02',
  '2026-12-01',
  '2027-01-04',
  '2027-02-01',
  '2027-03-01',
  '2027-04-05',
  '2027-05-03',
  '2027-06-01',
];

function demoPhases(): DeliverySchedulePhase[] {
  const tower: DeliverySchedulePhase[] = TOWER_LABELS.map((label, i) => ({
    id: `demo-phase-t${i + 1}`,
    area_group: 'TOWER',
    sequence: i + 1,
    label,
    delivery_date: TOWER_DATES[i],
  }));
  // No label at all, exactly as the document has them (finding G6).
  const common: DeliverySchedulePhase[] = [
    { id: 'demo-phase-c1', area_group: 'COMMON AREA', sequence: 1, label: null, delivery_date: '2026-07-01' },
    { id: 'demo-phase-c2', area_group: 'COMMON AREA', sequence: 2, label: null, delivery_date: '2026-10-01' },
    { id: 'demo-phase-c3', area_group: 'COMMON AREA', sequence: 3, label: null, delivery_date: '2027-06-01' },
  ];
  return [...tower, ...common];
}

function demoProducts(): DeliveryScheduleProduct[] {
  return [
    {
      product_id: 'demo-prod-1',
      product_code: 'SRTWC8613-RL',
      product_name: 'One-Piece WC, Dual Flush 6/3L',
      customer_code_raw: 'BUI-HB-SRTWC8613-RL',
      resolution_source: 'code',
      column_total: '927',
      reported_total: '927',
      po_qty: '927',
      reconciled: true,
      product_index: 0,
    },
    {
      product_id: 'demo-prod-2',
      product_code: 'SRTWC8608-RL',
      product_name: 'Close-Coupled WC, Dual Flush 6/3L',
      customer_code_raw: 'BUI-HB-SRTWC8608-RL',
      resolution_source: 'map',
      column_total: '894',
      reported_total: '894',
      po_qty: '894',
      reconciled: true,
      product_index: 1,
    },
    {
      product_id: 'demo-prod-3',
      product_code: 'SRTWC8840-RL',
      product_name: 'Rimless Close-Coupled WC',
      customer_code_raw: 'BUI-HB-SRTWC8840-RL',
      resolution_source: 'map',
      column_total: '9',
      reported_total: '9',
      po_qty: '9',
      reconciled: true,
      product_index: 2,
    },
    {
      product_id: 'demo-prod-4',
      product_code: 'SRTUB206-BI',
      product_name: 'Wall Hung Urinal, Back Inlet',
      customer_code_raw: 'BUI-HB-SRTUB206-BI',
      resolution_source: 'code',
      column_total: '16',
      reported_total: '16',
      po_qty: '16',
      reconciled: true,
      product_index: 3,
    },
    // Misread by the extractor: 8 where the document says 16. The checksum catches it and
    // this is the column a person actually fixes.
    {
      product_id: 'demo-prod-5',
      product_code: 'SRTFV1001',
      product_name: 'Sensor Urinal Flush Valve',
      customer_code_raw: 'BUI-HB-SRTFV1001',
      resolution_source: 'code',
      column_total: '8',
      reported_total: '16',
      po_qty: '16',
      reconciled: false,
      product_index: 4,
    },
    // Never matched to our catalogue, so it has no PO quantity to check against either.
    {
      product_id: null,
      product_code: null,
      product_name: null,
      customer_code_raw: 'BUI-HB-SRTWB7055',
      resolution_source: null,
      column_total: '927',
      reported_total: '927',
      po_qty: null,
      reconciled: false,
      product_index: 5,
    },
  ];
}

function demoCells(): DeliveryScheduleCell[] {
  const cells: DeliveryScheduleCell[] = [];
  const push = (
    phaseId: string,
    productId: string | null,
    productIndex: number,
    qty: string,
  ) => cells.push({ phase_id: phaseId, product_id: productId, product_index: productIndex, qty });

  TOWER_LABELS.forEach((_, i) => {
    const phaseId = `demo-phase-t${i + 1}`;
    push(phaseId, 'demo-prod-1', 0, i === 0 ? '135' : '72');
    push(phaseId, 'demo-prod-2', 1, i === 0 ? '124' : '66');
    push(phaseId, null, 5, i === 0 ? '135' : '72');
  });

  push('demo-phase-c1', 'demo-prod-4', 3, '16');
  push('demo-phase-c3', 'demo-prod-2', 1, '44');
  push('demo-phase-c3', 'demo-prod-3', 2, '9');
  push('demo-phase-c3', 'demo-prod-5', 4, '8');

  return cells;
}

function demoVersion(overrides: Partial<DeliveryScheduleVersion> = {}): DeliveryScheduleVersion {
  return {
    id: 'demo-version-2',
    delivery_schedule_id: 'demo-schedule-1',
    version_no: 2,
    revision_label: 'REVISED 1 - 23/7/2026',
    issuer_party_label: 'SLG Construction Sdn Bhd',
    po_version_id: 'demo-po-version-1',
    po_version_no: 1,
    extraction_state: 'done',
    document_url: null,
    schedule_date: '2026-07-23',
    phases: demoPhases(),
    products: demoProducts(),
    cells: demoCells(),
    reconciliation: { reconciled_columns: 4, total_columns: 6 },
    confirmed_at: null,
    page_count: 7,
    pages_extracted: 7,
    po_number: 'HQ/26/01/121',
    purchase_order_id: 'demo-po-1',
    uploaded_by_name: 'Maryam Yusof',
    created_at: '2026-07-23T02:11:00',
    ...overrides,
  };
}

function demoSchedules(): DeliverySchedule[] {
  return [
    {
      id: 'demo-schedule-1',
      purchase_order_id: 'demo-po-1',
      po_number: 'HQ/26/01/121',
      version_count: 2,
      latest_version_id: 'demo-version-2',
      latest_version_no: 2,
      latest_revision_label: 'REVISED 1 - 23/7/2026',
      issuer_party_label: 'SLG Construction Sdn Bhd',
      schedule_date: '2026-07-23',
      extraction_state: 'done',
      reconciled_columns: 4,
      total_columns: 6,
      confirmed_at: null,
      created_at: '2026-07-23T02:11:00',
    },
    {
      id: 'demo-schedule-2',
      purchase_order_id: 'demo-po-2',
      po_number: 'HQ/25/11/084',
      version_count: 1,
      latest_version_id: 'demo-version-9',
      latest_version_no: 1,
      latest_revision_label: null,
      issuer_party_label: 'Buimaco Sdn Bhd',
      schedule_date: '2025-11-07',
      extraction_state: 'done',
      reconciled_columns: 4,
      total_columns: 4,
      confirmed_at: '2025-11-08T01:20:00',
      created_at: '2025-11-07T08:30:00',
    },
  ];
}

export function demoVersionSummaries(): DeliveryScheduleVersionSummary[] {
  return [
    {
      id: 'demo-version-2',
      delivery_schedule_id: 'demo-schedule-1',
      version_no: 2,
      revision_label: 'REVISED 1 - 23/7/2026',
      issuer_party_label: 'SLG Construction Sdn Bhd',
      schedule_date: '2026-07-23',
      extraction_state: 'done',
      reconciled_columns: 4,
      total_columns: 6,
      confirmed_at: null,
      created_at: '2026-07-23T02:11:00',
      uploaded_by_name: 'Maryam Yusof',
    },
    {
      id: 'demo-version-1',
      delivery_schedule_id: 'demo-schedule-1',
      version_no: 1,
      revision_label: 'DATE : 4 MARCH 2026',
      issuer_party_label: 'Buimaco Sdn Bhd',
      schedule_date: '2026-03-04',
      extraction_state: 'done',
      reconciled_columns: 6,
      total_columns: 6,
      confirmed_at: '2026-03-05T01:40:00',
      created_at: '2026-03-04T09:02:00',
      uploaded_by_name: 'Maryam Yusof',
    },
  ];
}

// ------------------------------------------------------------- state adapters

export interface DemoQueryState<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

const LOADING = { data: undefined, isLoading: true, isError: false, error: null };
const FAILED_LOAD = {
  data: undefined,
  isLoading: false,
  isError: true,
  error: new Error('The service did not answer. Try again shortly.'),
};

export function demoScheduleListState(
  state: DemoState,
): DemoQueryState<DeliverySchedule[]> {
  if (state === 'loading') return LOADING;
  if (state === 'error') return FAILED_LOAD;
  if (state === 'empty') {
    return { data: [], isLoading: false, isError: false, error: null };
  }
  return { data: demoSchedules(), isLoading: false, isError: false, error: null };
}

export function demoScheduleVersionState(
  state: DemoState,
): DemoQueryState<DeliveryScheduleVersion> {
  if (state === 'loading' || state === 'empty') return LOADING;
  if (state === 'error') return FAILED_LOAD;

  const ready = (version: DeliveryScheduleVersion) => ({
    data: version,
    isLoading: false,
    isError: false,
    error: null,
  });

  switch (state) {
    case 'queued':
      return ready(
        demoVersion({
          extraction_state: 'queued',
          pages_extracted: 0,
          phases: [],
          products: [],
          cells: [],
          reconciliation: { reconciled_columns: 0, total_columns: 0 },
        }),
      );
    case 'running':
      return ready(
        demoVersion({
          extraction_state: 'running',
          pages_extracted: 3,
          phases: [],
          products: [],
          cells: [],
          reconciliation: { reconciled_columns: 0, total_columns: 0 },
        }),
      );
    case 'partial':
      return ready(
        demoVersion({
          extraction_state: 'partial',
          pages_extracted: 5,
          extraction_error: 'Pages 6 and 7 could not be read.',
        }),
      );
    case 'failed':
      return ready(
        demoVersion({
          extraction_state: 'failed',
          pages_extracted: 0,
          extraction_error: 'The file is not a readable PDF or image.',
          phases: [],
          products: [],
          cells: [],
          reconciliation: { reconciled_columns: 0, total_columns: 0 },
        }),
      );
    case 'confirmed': {
      // Everything agrees here, cells included: the reviewer corrected the misread valve
      // column and identified the basin column before confirming.
      const products = demoProducts().map((product, index) => {
        if (index === 4) return { ...product, column_total: '16', reconciled: true };
        if (index === 5) {
          return {
            ...product,
            product_id: 'demo-prod-6',
            product_code: 'SRTWB7055',
            product_name: 'Counter-Top / Wall Hung Basin',
            resolution_source: 'manual' as const,
            po_qty: '927',
            reconciled: true,
          };
        }
        return { ...product, reconciled: true };
      });
      const cells = demoCells().map((cell) =>
        cell.product_index === 4 ? { ...cell, qty: '16' } : cell,
      );
      return ready(
        demoVersion({
          products,
          cells: cells.map((cell) =>
            cell.product_index === 5 ? { ...cell, product_id: 'demo-prod-6' } : cell,
          ),
          reconciliation: { reconciled_columns: 6, total_columns: 6 },
          confirmed_at: '2026-07-24T01:05:00',
          confirmed_by_name: 'Eling Tan',
        }),
      );
    }
    default:
      return ready(demoVersion());
  }
}
