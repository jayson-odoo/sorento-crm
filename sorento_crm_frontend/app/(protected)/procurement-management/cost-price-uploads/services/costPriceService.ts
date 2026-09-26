/**
 * Cost price change sets (Lane A, S1 + S2, #1288) - service boundary.
 *
 * PHASE 1 MOCK. The expected API contract this mirrors is
 * `documentation/plans/purchasing/cost-price-api-contract.md` - every export below is named
 * and shaped after a section there (quoted in each function's own comment) so Phase 2 can
 * swap the body for a real `apiFetch` call, one function at a time, with the call site
 * (hooks/useCostPriceChangeSets.ts) untouched.
 *
 * The change-set world (list, detail, lines, history) is a self-contained in-memory store
 * seeded below - a brand new entity with no backend yet, so nothing here reads the real API.
 * The supplier Prices tab and the product Suppliers tab instead call the REAL, already-shipped
 * `product-suppliers` endpoints and synthesize the new `costs[]` field client-side
 * (`synthesizeCostRows`) - see that function's own comment for why.
 *
 * `MOCK_VERIFICATION_ENABLED` is the "module constant" the contract's mock-data section
 * names: ONE shared flag, read by the change-set detail's `actions`/`verification_enabled`
 * and read+written by the System Settings switch - flipping the switch is how Phase 1 shows
 * the verification-on views, no separate query-param toggle.
 */

import type {
  ChangeSetChannel,
  ChangeSetStatus,
  CostPriceChangeLine,
  CostPriceChangeSetActions,
  CostPriceChangeSetCounts,
  CostPriceChangeSetDetail,
  CostPriceChangeSetListItem,
  CostPriceHistoryEvent,
  CostPriceProbeResult,
  CostRowStatus,
  LineDecision,
  ProductSupplierCostRow,
  SheetSummary,
  SupplierRef,
} from '../types/costPrice.types';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

// ---------------------------------------------------------------------------
// The verification switch (contract section 3 / section 5)
// ---------------------------------------------------------------------------

let MOCK_VERIFICATION_ENABLED = false;

export async function getCostPriceVerificationSetting(): Promise<{ enabled: boolean }> {
  await delay();
  return { enabled: MOCK_VERIFICATION_ENABLED };
}

export async function updateCostPriceVerificationSetting(enabled: boolean): Promise<{ enabled: boolean }> {
  await delay();
  MOCK_VERIFICATION_ENABLED = enabled;
  return { enabled: MOCK_VERIFICATION_ENABLED };
}

// ---------------------------------------------------------------------------
// In-memory store
// ---------------------------------------------------------------------------

function delay(ms = 150): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

const TAIYANG: SupplierRef = {
  id: 'mock-supplier-taiyang',
  supplier_code: 'TAIYANG',
  supplier_name: 'XIAMEN TAIYANG TECHNOLOGY',
};
const HAIYUE: SupplierRef = {
  id: 'mock-supplier-haiyue',
  supplier_code: 'HAIYUE',
  supplier_name: 'NINGBO HAIYUE SANITARY',
};
const KAILI: SupplierRef = {
  id: 'mock-supplier-kaili',
  supplier_code: 'KAILI',
  supplier_name: 'FOSHAN KAILI CERAMICS',
};

type Line = CostPriceChangeLine;

interface ChangeSet {
  id: string;
  code: string;
  status: ChangeSetStatus;
  channel: ChangeSetChannel;
  supplier: SupplierRef;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  file_name: string | null;
  sheets: SheetSummary[];
  uploaded_by_name: string | null;
  created_at: string;
  submitted_by_name: string | null;
  submitted_at: string | null;
  returned_reason: string | null;
  returned_by_name: string | null;
  returned_at: string | null;
  applied_by_name: string | null;
  applied_at: string | null;
  verified: boolean | null;
  lines: Line[];
  history: CostPriceHistoryEvent[];
}

function seedTaiyangLines(): Line[] {
  return [
    {
      id: uid('line'),
      sheet: '19 series',
      row_no: 7,
      line_no: '1',
      supplier_code_raw: ' SRTWT1900-BL-DIY ',
      supplier_code: 'SRTWT1900-BL-DIY',
      code_note: null,
      configuration: '304不锈钢 单把 冷热',
      flags: ['configuration_from_merge'],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-srtwt1900', product_code: 'SRTWT1900-BL-DIY', description: 'ANGLE VALVE BLUE DIY' },
      current_unit_cost: 86.0,
      current_currency: 'CNY',
      new_unit_cost: 92.0,
      change_pct: 7.0,
      line_state: 'changed',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    {
      id: uid('line'),
      sheet: '25 series',
      row_no: 9,
      line_no: '3',
      supplier_code_raw: 'CB2500SS-BL（彩盒）',
      supplier_code: 'CB2500SS-BL',
      code_note: '彩盒',
      configuration: '不锈钢 拉丝 蓝',
      flags: [],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb2500ss-bl', product_code: 'CB2500SS-BL', description: 'BASIN MIXER BLUE' },
      current_unit_cost: 498.0,
      current_currency: 'CNY',
      new_unit_cost: 512.0,
      change_pct: 2.8,
      line_state: 'changed',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    {
      id: uid('line'),
      sheet: '25 series',
      row_no: 12,
      line_no: '4',
      supplier_code_raw: 'CB2500SS GY',
      supplier_code: 'CB2500SS GY',
      code_note: null,
      configuration: '不锈钢 拉丝 灰',
      flags: [],
      match_outcome: 'ladder',
      match_rung: 'separator',
      product: { id: 'mock-product-cb2500ss-gy', product_code: 'CB2500SS-GY', description: 'BASIN MIXER GREY' },
      current_unit_cost: 498.0,
      current_currency: 'CNY',
      new_unit_cost: 489.0,
      change_pct: -1.8,
      line_state: 'changed',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    {
      id: uid('line'),
      sheet: '22 series',
      row_no: 15,
      line_no: '2',
      supplier_code_raw: 'CB2200-WH',
      supplier_code: 'CB2200-WH',
      code_note: null,
      configuration: '陶瓷 白',
      flags: [],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb2200-wh', product_code: 'CB2200-WH', description: 'BASIN MIXER WHITE' },
      current_unit_cost: null,
      current_currency: null,
      new_unit_cost: 210.0,
      change_pct: null,
      line_state: 'new_link',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    {
      id: uid('line'),
      sheet: '28 series',
      row_no: 31,
      line_no: '9',
      supplier_code_raw: 'CB2800SS-BK-NEW',
      supplier_code: 'CB2800SS-BK-NEW',
      code_note: null,
      configuration: '不锈钢 黑 新款',
      flags: [],
      match_outcome: 'unmatched',
      match_rung: null,
      product: null,
      current_unit_cost: null,
      current_currency: null,
      new_unit_cost: 455.0,
      change_pct: null,
      line_state: 'needs_attention',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    // Duplicate code pair (AC-S1-10): both bind to CB2210-GY, one has to be skipped.
    // A distinct product from the CB2500SS-BL line above - two lines binding to ONE
    // product is exactly what "duplicate" means, and reusing the same product a third
    // way here would make the pair a trio instead of the pair AC-S1-10 describes.
    {
      id: uid('line'),
      sheet: '22 series',
      row_no: 20,
      line_no: '5',
      supplier_code_raw: 'CB2210-GY（彩盒）',
      supplier_code: 'CB2210-GY',
      code_note: '彩盒',
      configuration: '陶瓷 灰',
      flags: ['duplicate_code'],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb2210-gy', product_code: 'CB2210-GY', description: 'BASIN MIXER GREY (CERAMIC)' },
      current_unit_cost: 220.0,
      current_currency: 'CNY',
      new_unit_cost: 232.0,
      change_pct: 5.5,
      line_state: 'needs_attention',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    {
      id: uid('line'),
      sheet: '22 series',
      row_no: 21,
      line_no: '6',
      supplier_code_raw: 'CB2210-GY',
      supplier_code: 'CB2210-GY',
      code_note: null,
      configuration: '陶瓷 灰',
      flags: ['duplicate_code'],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb2210-gy', product_code: 'CB2210-GY', description: 'BASIN MIXER GREY (CERAMIC)' },
      current_unit_cost: 220.0,
      current_currency: 'CNY',
      new_unit_cost: 228.0,
      change_pct: 3.6,
      line_state: 'needs_attention',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    // A new link with no lead time on file for this supplier yet (AC-S2-05).
    {
      id: uid('line'),
      sheet: '12 series',
      row_no: 18,
      line_no: '6',
      supplier_code_raw: 'CB1200-GY',
      supplier_code: 'CB1200-GY',
      code_note: null,
      configuration: '陶瓷 灰',
      flags: [],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb1200-gy', product_code: 'CB1200-GY', description: 'SHOWER SET GREY' },
      current_unit_cost: null,
      current_currency: null,
      new_unit_cost: 178.0,
      change_pct: null,
      line_state: 'new_link',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    // Unchanged: the file quotes the same price already in force.
    {
      id: uid('line'),
      sheet: '19 series',
      row_no: 8,
      line_no: '2',
      supplier_code_raw: 'SRTWT1900-DIY',
      supplier_code: 'SRTWT1900-DIY',
      code_note: null,
      configuration: '304不锈钢 单把 冷热 标准款',
      flags: [],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-srtwt1900-diy', product_code: 'SRTWT1900-DIY', description: 'ANGLE VALVE DIY' },
      current_unit_cost: 79.0,
      current_currency: 'CNY',
      new_unit_cost: 79.0,
      change_pct: 0,
      line_state: 'unchanged',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
    // A price cell with no readable number (AC-S1-05).
    {
      id: uid('line'),
      sheet: '28 series',
      row_no: 40,
      line_no: '12',
      supplier_code_raw: 'CB2810SS-BK',
      supplier_code: 'CB2810SS-BK',
      code_note: null,
      configuration: '不锈钢 黑',
      flags: [],
      match_outcome: 'exact',
      match_rung: null,
      product: { id: 'mock-product-cb2810ss-bk', product_code: 'CB2810SS-BK', description: 'BASIN MIXER BLACK' },
      current_unit_cost: 430.0,
      current_currency: 'CNY',
      new_unit_cost: null,
      change_pct: null,
      line_state: 'needs_attention',
      skipped: false,
      skip_reason: null,
      new_link_lead_time_days: null,
      decision: null,
      decision_reason: null,
      decided_by_name: null,
      stale: null,
    },
  ];
}

function sheetsFrom(lines: Line[], fileDate: string | null): SheetSummary[] {
  const bySheet = new Map<string, number>();
  for (const line of lines) bySheet.set(line.sheet, (bySheet.get(line.sheet) ?? 0) + 1);
  const order = ['19 series', '12 series', '22 series', '28 series', '25 series'];
  return order
    .filter((name) => bySheet.has(name))
    .map((name) => ({ name, header_row: 6, rows: bySheet.get(name) ?? 0, skipped_reason: null }));
  // fileDate is display-only, carried by the set itself, not per sheet.
  void fileDate;
}

let codeSeq = 8;
function nextCode(): string {
  return `CPC-${String(codeSeq++).padStart(4, '0')}`;
}

function nowIso(): string {
  return new Date().toISOString().slice(0, 19);
}

const store: ChangeSet[] = [
  {
    id: 'mock-set-0007',
    code: 'CPC-0007',
    status: 'draft',
    channel: 'staff_upload',
    supplier: TAIYANG,
    currency: 'CNY',
    start_date: '2026-10-01',
    end_date: null,
    file_name: 'TO SORENTO-19&12&22&28&25 series price list 20260917.xlsx',
    sheets: sheetsFrom(seedTaiyangLines(), '2026-09-17'),
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-09-27T10:05:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    lines: seedTaiyangLines(),
    history: [
      {
        action: 'COST_SET_UPLOAD',
        actor_name: 'Mei Ling',
        at: '2026-09-27T10:05:00',
        summary: 'Uploaded 10 rows from TO SORENTO-19&12&22&28&25 series price list 20260917.xlsx',
      },
    ],
  },
  {
    id: 'mock-set-0004',
    code: 'CPC-0004',
    status: 'applied',
    channel: 'staff_upload',
    supplier: TAIYANG,
    currency: 'CNY',
    start_date: null,
    end_date: null,
    file_name: 'series 19 price.xlsx',
    sheets: [{ name: '19 series', header_row: 6, rows: 3, skipped_reason: null }],
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-09-02T09:00:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: 'Mei Ling',
    applied_at: '2026-09-02T09:20:00',
    verified: false,
    lines: [
      {
        id: uid('line'),
        sheet: '19 series',
        row_no: 7,
        line_no: '1',
        supplier_code_raw: 'SRTWT1900-BL-DIY',
        supplier_code: 'SRTWT1900-BL-DIY',
        code_note: null,
        configuration: '304不锈钢 单把 冷热',
        flags: [],
        match_outcome: 'exact',
        match_rung: null,
        product: { id: 'mock-product-srtwt1900', product_code: 'SRTWT1900-BL-DIY', description: 'ANGLE VALVE BLUE DIY' },
        current_unit_cost: 80.0,
        current_currency: 'CNY',
        new_unit_cost: 86.0,
        change_pct: 7.5,
        line_state: 'changed',
        skipped: false,
        skip_reason: null,
        new_link_lead_time_days: null,
        decision: null,
        decision_reason: null,
        decided_by_name: null,
        stale: null,
      },
    ],
    history: [
      {
        action: 'COST_SET_UPLOAD',
        actor_name: 'Mei Ling',
        at: '2026-09-02T09:00:00',
        summary: 'Uploaded 1 row from series 19 price.xlsx',
      },
      {
        action: 'COST_SET_APPLY',
        actor_name: 'Mei Ling',
        at: '2026-09-02T09:20:00',
        summary: 'Applied 1 change (not verified): SRTWT1900-BL-DIY 80.00 -> 86.00 CNY',
      },
    ],
  },
  {
    id: 'mock-set-0006',
    code: 'CPC-0006',
    status: 'applied',
    channel: 'staff_upload',
    supplier: HAIYUE,
    currency: 'USD',
    start_date: null,
    end_date: null,
    file_name: 'HY price 2026.xlsx',
    sheets: [{ name: 'Sheet1', header_row: 1, rows: 1, skipped_reason: null }],
    uploaded_by_name: 'Kelvin',
    created_at: '2026-08-20T14:00:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: 'Kelvin',
    applied_at: '2026-08-20T14:10:00',
    verified: false,
    lines: [],
    history: [
      { action: 'COST_SET_UPLOAD', actor_name: 'Kelvin', at: '2026-08-20T14:00:00', summary: 'Uploaded 1 row from HY price 2026.xlsx' },
      { action: 'COST_SET_APPLY', actor_name: 'Kelvin', at: '2026-08-20T14:10:00', summary: 'Applied 1 change (not verified)' },
    ],
  },
  {
    id: 'mock-set-0005',
    code: 'CPC-0005',
    status: 'applied',
    channel: 'staff_upload',
    supplier: KAILI,
    currency: 'CNY',
    start_date: null,
    end_date: null,
    file_name: 'Price update Q4.xlsx',
    sheets: [{ name: 'Sheet1', header_row: 1, rows: 1, skipped_reason: null }],
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-08-15T11:00:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: 'Mei Ling',
    applied_at: '2026-08-15T11:15:00',
    verified: false,
    lines: [],
    history: [
      { action: 'COST_SET_UPLOAD', actor_name: 'Mei Ling', at: '2026-08-15T11:00:00', summary: 'Uploaded 1 row from Price update Q4.xlsx' },
      { action: 'COST_SET_APPLY', actor_name: 'Mei Ling', at: '2026-08-15T11:15:00', summary: 'Applied 1 change (not verified)' },
    ],
  },
];

function findSet(id: string): ChangeSet {
  const set = store.find((s) => s.id === id);
  if (!set) throw new Error('Cost price change set not found');
  return set;
}

function deriveCounts(lines: Line[]): CostPriceChangeSetCounts {
  const counts: CostPriceChangeSetCounts = {
    changed: 0,
    unchanged: 0,
    new_link: 0,
    unmatched: 0,
    duplicate_code: 0,
    needs_attention: 0,
    skipped: 0,
    accepted: 0,
    rejected: 0,
    undecided: 0,
  };
  for (const line of lines) {
    if (line.skipped) {
      counts.skipped += 1;
      continue;
    }
    if (line.match_outcome === 'unmatched') counts.unmatched += 1;
    if (line.flags.includes('duplicate_code')) counts.duplicate_code += 1;
    if (line.line_state === 'changed') counts.changed += 1;
    else if (line.line_state === 'unchanged') counts.unchanged += 1;
    else if (line.line_state === 'new_link') counts.new_link += 1;
    else if (line.line_state === 'needs_attention') counts.needs_attention += 1;
    if (line.line_state === 'changed' || line.line_state === 'new_link') {
      if (line.decision === 'accepted') counts.accepted += 1;
      else if (line.decision === 'rejected') counts.rejected += 1;
      else counts.undecided += 1;
    }
  }
  return counts;
}

function unresolvedCount(lines: Line[]): number {
  return lines.filter(
    (l) => !l.skipped && (l.match_outcome === 'unmatched' || l.flags.includes('duplicate_code') || l.line_state === 'needs_attention'),
  ).length;
}

function largestRise(lines: Line[]): { supplier_code: string; change_pct: number } | null {
  const candidates = lines.filter((l) => !l.skipped && l.change_pct != null && l.change_pct > 0);
  if (!candidates.length) return null;
  const top = candidates.reduce((a, b) => ((b.change_pct ?? 0) > (a.change_pct ?? 0) ? b : a));
  return { supplier_code: top.supplier_code, change_pct: top.change_pct ?? 0 };
}

function computeActions(set: ChangeSet): CostPriceChangeSetActions {
  const unresolved = unresolvedCount(set.lines);
  const undecided = set.lines.filter(
    (l) => !l.skipped && (l.line_state === 'changed' || l.line_state === 'new_link') && !l.decision,
  ).length;
  const applyCount = set.lines.filter((l) => !l.skipped && (l.line_state === 'changed' || l.line_state === 'new_link')).length;
  const missingLeadTime = set.lines.some((l) => !l.skipped && l.line_state === 'new_link' && l.new_link_lead_time_days == null);

  if (set.status === 'applied') {
    return {
      can_apply: false,
      apply_blocked_reason: 'Already applied.',
      apply_count: 0,
      can_submit: false,
      can_decide: false,
      can_return: false,
      can_discard: false,
      decide_blocked_reason: null,
    };
  }

  if (!MOCK_VERIFICATION_ENABLED && set.status === 'draft' && set.channel === 'staff_upload') {
    const blocked = unresolved > 0 ? `${unresolved} row${unresolved === 1 ? '' : 's'} still need${unresolved === 1 ? 's' : ''} you` : missingLeadTime ? 'A new link needs a lead time first' : null;
    return {
      can_apply: !blocked,
      apply_blocked_reason: blocked,
      apply_count: applyCount,
      can_submit: false,
      can_decide: false,
      can_return: false,
      can_discard: true,
      decide_blocked_reason: null,
    };
  }

  if (set.status === 'draft') {
    // Verification on, staff set: Submit replaces Apply. The blocked reason is the
    // same "rows still need you" whether it is blocking Submit (here) or Apply
    // (verification off, above) - the FE shows it under whichever button is live.
    const blocked = unresolved > 0 ? `${unresolved} row${unresolved === 1 ? '' : 's'} still need${unresolved === 1 ? 's' : ''} you` : null;
    return {
      can_apply: false,
      apply_blocked_reason: blocked ?? 'Submit for verification first.',
      apply_count: applyCount,
      can_submit: !blocked,
      can_decide: false,
      can_return: false,
      can_discard: true,
      decide_blocked_reason: blocked,
    };
  }

  // pending_verification
  const blocked =
    undecided > 0
      ? `${undecided} line${undecided === 1 ? '' : 's'} still undecided`
      : missingLeadTime
        ? 'A new link needs a lead time first'
        : null;
  return {
    can_apply: !blocked,
    apply_blocked_reason: blocked,
    apply_count: set.lines.filter((l) => !l.skipped && l.decision === 'accepted').length,
    can_submit: false,
    can_decide: true,
    can_return: true,
    can_discard: false,
    decide_blocked_reason: null,
  };
}

function toListItem(set: ChangeSet): CostPriceChangeSetListItem {
  const counts = deriveCounts(set.lines);
  return {
    id: set.id,
    code: set.code,
    status: set.status,
    supplier: set.supplier,
    channel: set.channel,
    file_name: set.file_name,
    currency: set.currency,
    start_date: set.start_date,
    end_date: set.end_date,
    lines_changed: counts.changed + counts.new_link,
    uploaded_by_name: set.uploaded_by_name,
    created_at: set.created_at,
    applied_at: set.applied_at,
    verified: set.verified,
    verified_by_name: set.applied_by_name && set.verified ? set.applied_by_name : null,
  };
}

function toDetail(set: ChangeSet): CostPriceChangeSetDetail {
  return {
    id: set.id,
    code: set.code,
    status: set.status,
    channel: set.channel,
    supplier: set.supplier,
    currency: set.currency,
    start_date: set.start_date,
    end_date: set.end_date,
    file_name: set.file_name,
    has_source_file: Boolean(set.file_name),
    sheets: set.sheets,
    total_rows: set.sheets.reduce((sum, s) => sum + s.rows, 0),
    uploaded_by_name: set.uploaded_by_name,
    created_at: set.created_at,
    submitted_by_name: set.submitted_by_name,
    submitted_at: set.submitted_at,
    returned_reason: set.returned_reason,
    returned_by_name: set.returned_by_name,
    returned_at: set.returned_at,
    applied_by_name: set.applied_by_name,
    applied_at: set.applied_at,
    verified: set.verified,
    verification_enabled: MOCK_VERIFICATION_ENABLED,
    counts: deriveCounts(set.lines),
    largest_rise: largestRise(set.lines),
    actions: computeActions(set),
  };
}

// ---------------------------------------------------------------------------
// 1.1 probe, 1.2 upload
// ---------------------------------------------------------------------------

export async function probeCostPriceFile(file: File): Promise<CostPriceProbeResult> {
  await delay(400);
  const dateMatch = file.name.match(/(\d{8})/);
  const fileDate = dateMatch
    ? `${dateMatch[1].slice(0, 4)}-${dateMatch[1].slice(4, 6)}-${dateMatch[1].slice(6, 8)}`
    : null;
  return {
    file_name: file.name,
    file_date: fileDate,
    sheets: [
      { name: '19 series', header_row: 6, rows: 40, skipped_reason: null },
      { name: '12 series', header_row: 6, rows: 24, skipped_reason: null },
      { name: '22 series', header_row: 6, rows: 18, skipped_reason: null },
      { name: '28 series', header_row: 6, rows: 58, skipped_reason: null },
      { name: '25 series', header_row: 6, rows: 118, skipped_reason: null },
    ],
    total_rows: 258,
    suggested_supplier: TAIYANG,
    currency: { code: 'CNY', source: 'header' },
  };
}

export interface UploadCostPriceFileInput {
  file: File;
  supplier: SupplierRef;
  currency: string;
  start_date: string | null;
  end_date: string | null;
}

/** 409 `open_set_exists`, thrown with the open set attached, mirroring the contract's body. */
export class OpenSetExistsError extends Error {
  open_set: { id: string; code: string };
  constructor(open_set: { id: string; code: string }) {
    super(`${open_set.code} is still open for this supplier.`);
    this.open_set = open_set;
  }
}

export async function uploadCostPriceFile(input: UploadCostPriceFileInput): Promise<CostPriceChangeSetDetail> {
  await delay(500);
  const open = store.find(
    (s) => s.supplier.id === input.supplier.id && (s.status === 'draft' || s.status === 'pending_verification'),
  );
  if (open) throw new OpenSetExistsError({ id: open.id, code: open.code });

  const lines = seedTaiyangLines().map((line) => ({ ...line, id: uid('line') }));
  const set: ChangeSet = {
    id: uid('set'),
    code: nextCode(),
    status: 'draft',
    channel: 'staff_upload',
    supplier: input.supplier,
    currency: input.currency,
    start_date: input.start_date,
    end_date: input.end_date,
    file_name: input.file.name,
    sheets: sheetsFrom(lines, input.start_date),
    uploaded_by_name: 'You',
    created_at: nowIso(),
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    lines,
    history: [
      {
        action: 'COST_SET_UPLOAD',
        actor_name: 'You',
        at: nowIso(),
        summary: `Uploaded ${lines.length} rows from ${input.file.name}`,
      },
    ],
  };
  store.unshift(set);
  return toDetail(set);
}

// ---------------------------------------------------------------------------
// 1.3 list, 1.4 detail, 1.5 lines
// ---------------------------------------------------------------------------

export interface CostPriceListParams {
  page: number;
  limit: number;
  query?: string;
  status?: string[];
  supplier_id?: string;
}

export async function getCostPriceChangeSets(
  params: CostPriceListParams,
): Promise<{ data: CostPriceChangeSetListItem[]; total: number; page: number; limit: number }> {
  await delay();
  let rows = store.slice();
  if (params.query) {
    const q = params.query.toLowerCase();
    rows = rows.filter(
      (s) =>
        s.code.toLowerCase().includes(q) ||
        s.supplier.supplier_name.toLowerCase().includes(q) ||
        s.supplier.supplier_code.toLowerCase().includes(q) ||
        (s.file_name ?? '').toLowerCase().includes(q),
    );
  }
  if (params.status?.length) rows = rows.filter((s) => params.status!.includes(s.status));
  if (params.supplier_id) rows = rows.filter((s) => s.supplier.id === params.supplier_id);
  rows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  const total = rows.length;
  const start = (params.page - 1) * params.limit;
  const page = rows.slice(start, start + params.limit).map(toListItem);
  return { data: page, total, page: params.page, limit: params.limit };
}

export async function getCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  await delay();
  return toDetail(findSet(id));
}

export async function getCostPriceChangeLines(id: string): Promise<{ data: CostPriceChangeLine[] }> {
  await delay();
  const set = findSet(id);
  const order = ['19 series', '12 series', '22 series', '28 series', '25 series'];
  const sorted = set.lines.slice().sort((a, b) => {
    const sd = order.indexOf(a.sheet) - order.indexOf(b.sheet);
    return sd !== 0 ? sd : a.row_no - b.row_no;
  });
  return { data: sorted };
}

// ---------------------------------------------------------------------------
// 1.6 map / skip / lead time
// ---------------------------------------------------------------------------

export interface PatchLineInput {
  product_id?: string | null;
  skipped?: boolean;
  skip_reason?: string;
  new_link_lead_time_days?: number;
}

function recomputeLineState(set: ChangeSet, line: Line): void {
  if (line.skipped) {
    line.line_state = 'skipped';
    return;
  }
  const dup = set.lines.filter((l) => !l.skipped && l.product?.id && l.product.id === line.product?.id).length > 1;
  line.flags = dup ? Array.from(new Set([...line.flags, 'duplicate_code'])) : line.flags.filter((f) => f !== 'duplicate_code');
  if (line.match_outcome === 'unmatched') {
    line.line_state = 'needs_attention';
    return;
  }
  if (dup) {
    line.line_state = 'needs_attention';
    return;
  }
  if (line.new_unit_cost == null) {
    line.line_state = 'needs_attention';
    return;
  }
  if (line.current_unit_cost == null) {
    line.line_state = 'new_link';
    return;
  }
  const noDates = !set.start_date && !set.end_date;
  if (noDates && line.current_unit_cost === line.new_unit_cost) {
    line.line_state = 'unchanged';
  } else {
    line.line_state = 'changed';
  }
}

export async function patchCostPriceChangeLine(
  setId: string,
  lineId: string,
  patch: PatchLineInput,
): Promise<{ line: CostPriceChangeLine; counts: CostPriceChangeSetCounts; actions: CostPriceChangeSetActions }> {
  await delay(200);
  const set = findSet(setId);
  if (set.status !== 'draft') throw new Error('Only a draft set can be mapped or skipped.');
  const line = set.lines.find((l) => l.id === lineId);
  if (!line) throw new Error('Line not found');

  if (patch.product_id !== undefined) {
    if (patch.product_id) {
      const option = MOCK_PRODUCTS.find((p) => p.id === patch.product_id);
      line.product = option ? { id: option.id, product_code: option.product_code, description: option.description } : null;
      line.match_outcome = 'manual';
      set.history.push({
        action: 'COST_LINE_MAP',
        actor_name: 'You',
        at: nowIso(),
        summary: `Mapped ${line.supplier_code} to ${option?.product_code ?? 'a product'}`,
      });
    } else {
      line.product = null;
      line.match_outcome = 'unmatched';
    }
  }
  if (patch.skipped !== undefined) {
    line.skipped = patch.skipped;
    line.skip_reason = patch.skipped ? (patch.skip_reason ?? 'Skipped') : null;
    if (patch.skipped) {
      set.history.push({ action: 'COST_LINE_SKIP', actor_name: 'You', at: nowIso(), summary: `Skipped ${line.supplier_code}` });
    }
  }
  if (patch.new_link_lead_time_days !== undefined) {
    line.new_link_lead_time_days = patch.new_link_lead_time_days;
  }
  recomputeLineState(set, line);
  // A duplicate sibling has to be re-evaluated too, since resolving one changes the pair.
  for (const other of set.lines) {
    if (other.id !== line.id) recomputeLineState(set, other);
  }
  return { line, counts: deriveCounts(set.lines), actions: computeActions(set) };
}

// ---------------------------------------------------------------------------
// 1.7 verification
// ---------------------------------------------------------------------------

export async function submitCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  await delay(300);
  const set = findSet(id);
  if (!MOCK_VERIFICATION_ENABLED) throw new Error('Verification is off; apply directly.');
  if (set.status !== 'draft') throw new Error('Only a draft set can be submitted.');
  if (unresolvedCount(set.lines) > 0) throw new Error('Resolve every row before submitting.');
  set.status = 'pending_verification';
  set.submitted_by_name = 'You';
  set.submitted_at = nowIso();
  set.history.push({ action: 'COST_SET_SUBMIT', actor_name: 'You', at: nowIso(), summary: 'Submitted for verification' });
  return toDetail(set);
}

export async function decideCostPriceLine(
  setId: string,
  lineId: string,
  decision: LineDecision,
  reason?: string,
): Promise<{ line: CostPriceChangeLine; counts: CostPriceChangeSetCounts; actions: CostPriceChangeSetActions }> {
  await delay(200);
  const set = findSet(setId);
  const line = set.lines.find((l) => l.id === lineId);
  if (!line) throw new Error('Line not found');
  line.decision = decision;
  line.decision_reason = reason ?? null;
  line.decided_by_name = decision ? 'You' : null;
  return { line, counts: deriveCounts(set.lines), actions: computeActions(set) };
}

export async function decideAllCostPriceLines(id: string, decision: 'accepted' | 'rejected'): Promise<CostPriceChangeSetDetail> {
  await delay(300);
  const set = findSet(id);
  for (const line of set.lines) {
    if (line.skipped) continue;
    if (line.line_state !== 'changed' && line.line_state !== 'new_link') continue;
    if (line.decision) continue;
    line.decision = decision;
    line.decided_by_name = 'You';
  }
  set.history.push({ action: 'COST_LINE_MAP', actor_name: 'You', at: nowIso(), summary: `Accepted every undecided line` });
  return toDetail(set);
}

export async function returnCostPriceChangeSet(id: string, reason: string): Promise<CostPriceChangeSetDetail> {
  await delay(300);
  const set = findSet(id);
  set.status = 'draft';
  set.returned_reason = reason;
  set.returned_by_name = 'You';
  set.returned_at = nowIso();
  for (const line of set.lines) {
    line.decision = null;
    line.decision_reason = null;
    line.decided_by_name = null;
  }
  set.history.push({ action: 'COST_SET_RETURN', actor_name: 'You', at: nowIso(), summary: `Returned to submitter: ${reason}` });
  return toDetail(set);
}

// ---------------------------------------------------------------------------
// 1.8 apply
// ---------------------------------------------------------------------------

export async function applyCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  await delay(400);
  const set = findSet(id);
  const actions = computeActions(set);
  if (!actions.can_apply) throw new Error(actions.apply_blocked_reason ?? 'This set cannot be applied yet.');
  const verified = MOCK_VERIFICATION_ENABLED && set.status === 'pending_verification';
  set.status = 'applied';
  set.applied_by_name = 'You';
  set.applied_at = nowIso();
  set.verified = verified;
  const changed = set.lines.filter((l) => !l.skipped && (l.line_state === 'changed' || l.line_state === 'new_link'));
  set.history.push({
    action: 'COST_SET_APPLY',
    actor_name: 'You',
    at: nowIso(),
    summary: `Applied ${changed.length} change${changed.length === 1 ? '' : 's'} (${verified ? 'verified' : 'not verified'}): ${changed
      .slice(0, 3)
      .map((l) => l.supplier_code)
      .join(', ')}${changed.length > 3 ? '...' : ''}`,
  });
  return toDetail(set);
}

// ---------------------------------------------------------------------------
// 1.9 discard, 1.10 source file, 1.11 history
// ---------------------------------------------------------------------------

export async function discardCostPriceChangeSet(id: string): Promise<void> {
  await delay(300);
  const set = findSet(id);
  if (set.status !== 'draft') throw new Error('Only a draft set can be discarded.');
  const index = store.findIndex((s) => s.id === id);
  if (index >= 0) store.splice(index, 1);
}

export async function downloadCostPriceSourceFile(id: string): Promise<void> {
  const set = findSet(id);
  const blob = new Blob([`Mock source file for ${set.code} (${set.file_name ?? 'no file'})`], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = set.file_name ?? `${set.code}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function getCostPriceChangeSetHistory(id: string): Promise<{ data: CostPriceHistoryEvent[] }> {
  await delay();
  const set = findSet(id);
  return { data: set.history.slice().reverse() };
}

// ---------------------------------------------------------------------------
// Product picker for "Not found" lines (Section 6; mirrors
// `scmOptionsService.searchProductOptions`'s shape - swap target in Phase 2)
// ---------------------------------------------------------------------------

const MOCK_PRODUCTS = [
  { id: 'mock-product-cb2800ss-bk', product_code: 'CB2800SS-BK', description: 'BASIN MIXER BLACK' },
  { id: 'mock-product-cb2800ss-bl', product_code: 'CB2800SS-BL', description: 'BASIN MIXER BLUE' },
  { id: 'mock-product-cb2800-wh', product_code: 'CB2800-WH', description: 'BASIN MIXER WHITE' },
  { id: 'mock-product-srtwt1900', product_code: 'SRTWT1900-BL-DIY', description: 'ANGLE VALVE BLUE DIY' },
  { id: 'mock-product-srtwt1900-diy', product_code: 'SRTWT1900-DIY', description: 'ANGLE VALVE DIY' },
  { id: 'mock-product-cb2500ss-bl', product_code: 'CB2500SS-BL', description: 'BASIN MIXER BLUE' },
  { id: 'mock-product-cb2500ss-gy', product_code: 'CB2500SS-GY', description: 'BASIN MIXER GREY' },
  { id: 'mock-product-cb2200-wh', product_code: 'CB2200-WH', description: 'BASIN MIXER WHITE' },
  { id: 'mock-product-cb1200-gy', product_code: 'CB1200-GY', description: 'SHOWER SET GREY' },
  { id: 'mock-product-cb2810ss-bk', product_code: 'CB2810SS-BK', description: 'BASIN MIXER BLACK' },
];

export async function searchCostPriceProductOptions(query: string): Promise<SearchableSelectOption[]> {
  await delay(150);
  const q = query.trim().toLowerCase();
  const rows = q
    ? MOCK_PRODUCTS.filter((p) => p.product_code.toLowerCase().includes(q) || p.description.toLowerCase().includes(q))
    : MOCK_PRODUCTS;
  return rows.map((p) => ({ value: p.id, label: p.product_code, description: p.description, searchText: `${p.product_code} ${p.description}` }));
}

// ---------------------------------------------------------------------------
// Cost lists (section 2) - synthesized on top of the REAL product-suppliers
// endpoint, not the change-set store above.
//
// A product-supplier link already carries `unit_cost` + `currency` (the price
// in force) via the real, already-shipped API; the cost-list ROWS behind it
// (`product_supplier_costs`) do not exist until Phase 2's migration lands. This
// derives a plausible history from the link's own id, deterministically (same
// link always renders the same rows), so the Supplier Prices tab and the
// product Suppliers tab are fully demonstrable against whatever real
// suppliers/products/links already exist on this stack - not a fixed fake id
// that only lines up with this file's own seed data.
// ---------------------------------------------------------------------------

function hashString(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) h = (h * 31 + input.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function isoDaysFromToday(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function synthesizeCostRows(
  linkId: string,
  unitCost: number | string | null | undefined,
  currency: string | null | undefined,
): ProductSupplierCostRow[] {
  const cost = unitCost == null || unitCost === '' ? null : Number(unitCost);
  if (cost == null || Number.isNaN(cost)) return [];
  const h = hashString(linkId);
  const rows: ProductSupplierCostRow[] = [];
  const cur = currency || 'MYR';

  if (h % 3 === 0) {
    const older = Math.round(cost * 0.9 * 100) / 100;
    rows.push({
      id: `${linkId}-ended`,
      unit_cost: older,
      currency: cur,
      start_date: isoDaysFromToday(-400),
      end_date: isoDaysFromToday(-30),
      status: 'ended' as CostRowStatus,
      source: { change_set_id: 'mock-set-old', code: 'CPC-0002' },
      created_at: isoDaysFromToday(-400),
    });
  }

  rows.push({
    id: `${linkId}-current`,
    unit_cost: cost,
    currency: cur,
    start_date: null,
    end_date: null,
    status: 'in_force' as CostRowStatus,
    source: null,
    created_at: isoDaysFromToday(-14),
  });

  if (h % 2 === 0) {
    const higher = Math.round(cost * 1.05 * 100) / 100;
    rows.push({
      id: `${linkId}-scheduled`,
      unit_cost: higher,
      currency: cur,
      start_date: isoDaysFromToday(30),
      end_date: null,
      status: 'scheduled' as CostRowStatus,
      source: { change_set_id: 'mock-set-0007', code: 'CPC-0007' },
      created_at: isoDaysFromToday(-1),
    });
  }

  return rows.sort((a, b) => (a.start_date ?? '').localeCompare(b.start_date ?? ''));
}

// ---------------------------------------------------------------------------
// Cost list hand edits (section 2.3) - `procurement.product_suppliers.edit`.
//
// Layered over `synthesizeCostRows`: an add/edit/delete writes into these two
// per-link overlays rather than a real table (there is none yet), so a click
// through the Prices tab or the Suppliers tab is fully interactive without
// pretending the synthesized history itself is durable.
// ---------------------------------------------------------------------------

const handAddedRows = new Map<string, ProductSupplierCostRow[]>();
const handDeletedIds = new Map<string, Set<string>>();

function today(): string {
  return isoDaysFromToday(0);
}

/** Recomputed the same way `price_in_force` is specified (plan section 4.1): among the
 *  rows covering today, the latest start wins (null start counts as earliest); a tie goes
 *  to the newest `created_at`. Everything else is `scheduled` (start in the future),
 *  `ended` (end in the past) or `overridden` (covers today but loses the tie-break). */
function statusesFor(rows: ProductSupplierCostRow[]): ProductSupplierCostRow[] {
  const day = today();
  const covering = rows.filter((r) => (!r.start_date || r.start_date <= day) && (!r.end_date || r.end_date >= day));
  let inForce: ProductSupplierCostRow | null = null;
  for (const row of covering) {
    if (!inForce) {
      inForce = row;
      continue;
    }
    const a = row.start_date ?? '';
    const b = inForce.start_date ?? '';
    if (a > b || (a === b && row.created_at > inForce.created_at)) inForce = row;
  }
  return rows.map((row) => {
    let status: CostRowStatus;
    if (inForce && row.id === inForce.id) status = 'in_force';
    else if (row.start_date && row.start_date > day) status = 'scheduled';
    else if (row.end_date && row.end_date < day) status = 'ended';
    else if (!row.start_date && !row.end_date) status = 'always';
    else status = 'overridden';
    return { ...row, status };
  });
}

/** Every cost row for one product-supplier link: synthesized history plus whatever this
 *  visit has added, edited or removed by hand. */
export function getCostRowsForLink(
  linkId: string,
  unitCost: number | string | null | undefined,
  currency: string | null | undefined,
): ProductSupplierCostRow[] {
  const base = synthesizeCostRows(linkId, unitCost, currency);
  const added = handAddedRows.get(linkId) ?? [];
  const deleted = handDeletedIds.get(linkId);
  const merged = [...base, ...added].filter((r) => !deleted?.has(r.id));
  return statusesFor(merged).sort((a, b) => (a.start_date ?? '').localeCompare(b.start_date ?? ''));
}

export interface CostRowInput {
  unit_cost: number;
  currency: string;
  start_date: string | null;
  end_date: string | null;
}

function assertValidCostRow(input: CostRowInput): void {
  if (input.unit_cost < 0) throw new Error('The price cannot be negative.');
  if (input.start_date && input.end_date && input.end_date < input.start_date) {
    throw new Error('Valid to cannot be before Valid from.');
  }
}

export async function createProductSupplierCost(linkId: string, input: CostRowInput): Promise<ProductSupplierCostRow> {
  await delay(250);
  assertValidCostRow(input);
  const row: ProductSupplierCostRow = {
    id: uid('cost'),
    unit_cost: input.unit_cost,
    currency: input.currency,
    start_date: input.start_date,
    end_date: input.end_date,
    status: 'always',
    source: null,
    created_at: nowIso(),
  };
  const list = handAddedRows.get(linkId) ?? [];
  list.push(row);
  handAddedRows.set(linkId, list);
  return row;
}

export async function updateProductSupplierCost(
  linkId: string,
  costId: string,
  input: CostRowInput,
): Promise<ProductSupplierCostRow> {
  await delay(250);
  assertValidCostRow(input);
  const list = handAddedRows.get(linkId) ?? [];
  const existing = list.find((r) => r.id === costId);
  const updated: ProductSupplierCostRow = {
    id: costId,
    unit_cost: input.unit_cost,
    currency: input.currency,
    start_date: input.start_date,
    end_date: input.end_date,
    status: existing?.status ?? 'always',
    source: existing?.source ?? null,
    created_at: existing?.created_at ?? nowIso(),
  };
  if (existing) {
    list[list.indexOf(existing)] = updated;
  } else {
    // Editing a synthesized (not yet hand-added) row: promote it into the overlay and
    // remove the synthesized original so it is not shown twice.
    list.push(updated);
    const deleted = handDeletedIds.get(linkId) ?? new Set<string>();
    deleted.add(costId);
    handDeletedIds.set(linkId, deleted);
  }
  handAddedRows.set(linkId, list);
  return updated;
}

export async function deleteProductSupplierCost(linkId: string, costId: string): Promise<void> {
  await delay(250);
  const deleted = handDeletedIds.get(linkId) ?? new Set<string>();
  deleted.add(costId);
  handDeletedIds.set(linkId, deleted);
}
