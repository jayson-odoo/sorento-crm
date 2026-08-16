/**
 * PHASE 1 MOCK - the whole file is deleted in Phase 2, when the service calls apiFetch.
 *
 * It stands in for `/verification/*`, which does not exist yet, so the worklist,
 * the pills, the row actions and the bulk strip can be judged as UX before a
 * table is migrated. The shapes are the contract the backend is held to: if a
 * field is awkward to render here, it is the wrong field, and this is the cheap
 * moment to find that out.
 *
 * Two worlds, because one set of fixtures cannot be honest about both things the
 * plan asks to be reviewed:
 *
 *  - the DEFAULT world is day one, measured: 11,415 codes of which 8,812 are
 *    live, none verified, none needing re-verification. The progress line
 *    therefore reads "Verified 0 of 8,812 live codes", and `needs_reverify` is
 *    genuinely unreachable until somebody makes the first edit.
 *  - searching `states` swaps in a small world that carries all three pills, a
 *    three-key diff and a withdrawn stamp, so the states can be reviewed on
 *    screen without pretending day one looks like that.
 *
 * Search-box switches (all exact, case-insensitive):
 *    states   -> the mixed-state world
 *    empty    -> no rows (the empty state)
 *    error    -> the query rejects (the error state)
 *    loading  -> never resolves (the loading state)
 *
 * Verify and Unverify mutate an in-memory overlay, so a stamp applied here
 * survives paging and filtering for the life of the tab.
 */
import type {
  SpecVerificationRow,
  SpecVerificationWorklistParams,
  SpecVerificationWorklistResponse,
  UnverifyBulkResult,
  VerificationBlock,
  VerificationState,
  VerifyBulkResult,
  VerifyItem,
} from '../types/specVerification.types';

/** Enough latency that the skeleton is visible, little enough to click through. */
export const MOCK_LATENCY_MS = 280;

/** Who the mock records as the actor. The real one is the signed-in user. */
const MOCK_ACTOR = 'You';

export const MOCK_CLASS_OPTIONS = [
  'Basin',
  'Kitchen Sink',
  'Shower',
  'Tap',
  'Water Closet',
];

const CLASS_PREFIX: Record<string, string> = {
  Basin: 'BS',
  'Kitchen Sink': 'SK',
  Shower: 'SH',
  Tap: 'TP',
  'Water Closet': 'WC',
};

/** The registry is 52 keys, 7 of them gated behind a class (M8). */
function applicableFor(classLabel: string | null): number {
  return classLabel === 'Kitchen Sink' ? 52 : 45;
}

const UNVERIFIED: VerificationBlock = {
  state: 'unverified',
  verified_by_name: null,
  verified_at: null,
  invalidated_at: null,
  invalidated_reason: null,
  invalidated_by_name: null,
  invalidated_diff: null,
};

type SeedRow = Omit<SpecVerificationRow, 'product_id' | 'values_hash'> & {
  /** The mock moves this code's values the first time it is verified, so the
   *  `values_changed` refusal can be seen from the list. */
  driftsOnVerify?: boolean;
};

function seedToRow(seed: SeedRow, index: number): SpecVerificationRow {
  return {
    product_id: mockProductId(index),
    product_code: seed.product_code,
    product_name: seed.product_name,
    class_label: seed.class_label,
    brand_name: seed.brand_name,
    is_discontinued: seed.is_discontinued,
    coverage: seed.coverage,
    open_exceptions: seed.open_exceptions,
    values_hash: `h${index.toString(16).padStart(8, '0')}`,
    verification: seed.verification,
  };
}

/** Never rendered - the row click needs an id for the product detail route. */
function mockProductId(index: number): string {
  return `00000000-0000-4000-8000-${index.toString().padStart(12, '0')}`;
}

/**
 * Day one, page one. Every state here is one that really occurs on a catalogue
 * where nothing has been verified: mixed coverage (one code holds nothing, one
 * holds 14), open exceptions on three codes, and one code whose values move
 * under the reviewer.
 */
const DAY_ONE_SEEDS: SeedRow[] = [
  {
    product_code: 'WC-1500-SQ',
    product_name: 'Water Closet One Piece 1500mm',
    class_label: 'Water Closet',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 9, applicable: 45 },
    open_exceptions: 1,
    verification: UNVERIFIED,
  },
  {
    product_code: 'BS-0460-SQ',
    product_name: 'Basin Countertop 460mm Square',
    class_label: 'Basin',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 5, applicable: 45 },
    open_exceptions: 2,
    verification: UNVERIFIED,
  },
  {
    product_code: 'SK-7600-UM',
    product_name: 'Undermount Kitchen Sink 760mm',
    class_label: 'Kitchen Sink',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 14, applicable: 52 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'TP-0001-CH',
    product_name: 'Pillar Tap Chrome',
    class_label: 'Tap',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 0, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'TP-0044-BK',
    product_name: 'Basin Mixer Matte Black',
    class_label: 'Tap',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 3, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
    driftsOnVerify: true,
  },
  {
    product_code: 'SH-2100-RN',
    product_name: 'Rain Shower Set 210mm',
    class_label: 'Shower',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 8, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'WC-1200-EL',
    product_name: 'Water Closet Elongated 1200mm',
    class_label: 'Water Closet',
    brand_name: 'TP Enterprise',
    is_discontinued: false,
    coverage: { have: 11, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'BS-0415-SQ',
    product_name: 'Basin Semi Recessed 415mm',
    class_label: 'Basin',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 4, applicable: 45 },
    open_exceptions: 1,
    verification: UNVERIFIED,
  },
  {
    product_code: 'SK-0800-DB',
    product_name: 'Double Bowl Kitchen Sink 800mm',
    class_label: 'Kitchen Sink',
    brand_name: 'TP Enterprise',
    is_discontinued: false,
    coverage: { have: 6, applicable: 52 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'SH-0900-HS',
    product_name: 'Hand Shower Set 3 Function',
    class_label: 'Shower',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 2, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'WC-0420-RD',
    product_name: 'Water Closet Round 420mm',
    class_label: 'Water Closet',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 7, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'TP-0210-SN',
    product_name: 'Sink Mixer Brushed Nickel',
    class_label: null,
    brand_name: null,
    is_discontinued: false,
    coverage: { have: 5, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
];

/** Measured baseline (M6): 11,415 codes, 8,812 of them live. */
const TOTAL_CODES = 11415;
const LIVE_CODES = 8812;

function fillerRow(index: number): SpecVerificationRow {
  const classLabel = MOCK_CLASS_OPTIONS[index % MOCK_CLASS_OPTIONS.length];
  const prefix = CLASS_PREFIX[classLabel];
  const serial = 10000 + index;
  return {
    product_id: mockProductId(index),
    product_code: `${prefix}-${serial}`,
    product_name: `${classLabel} Model ${serial}`,
    class_label: classLabel,
    brand_name: index % 7 === 0 ? 'TP Enterprise' : 'Sorento',
    is_discontinued: index >= LIVE_CODES,
    coverage: { have: (index * 7) % 15, applicable: applicableFor(classLabel) },
    open_exceptions: index % 41 === 0 ? 1 : 0,
    values_hash: `h${index.toString(16).padStart(8, '0')}`,
    verification: UNVERIFIED,
  };
}

let dayOneWorld: SpecVerificationRow[] | null = null;

function getDayOneWorld(): SpecVerificationRow[] {
  if (dayOneWorld) return dayOneWorld;
  const rows = DAY_ONE_SEEDS.map((seed, i) => seedToRow(seed, i));
  for (let i = DAY_ONE_SEEDS.length; i < TOTAL_CODES; i += 1) {
    rows.push(fillerRow(i));
  }
  dayOneWorld = rows;
  return rows;
}

function verified(by: string, at: string): VerificationBlock {
  return {
    state: 'verified',
    verified_by_name: by,
    verified_at: at,
    invalidated_at: null,
    invalidated_reason: null,
    invalidated_by_name: null,
    invalidated_diff: null,
  };
}

function needsReverify(
  by: string,
  at: string,
  invalidatedAt: string,
  changed: { spec_key: string; was: string | null; now: string | null }[],
): VerificationBlock {
  return {
    state: 'needs_reverify',
    verified_by_name: by,
    verified_at: at,
    invalidated_at: invalidatedAt,
    invalidated_reason: 'values_changed',
    invalidated_by_name: null,
    invalidated_diff: { changed },
  };
}

/** The `states` world: every pill, a three-key diff, and a withdrawn stamp. */
const MIXED_STATE_SEEDS: SeedRow[] = [
  {
    product_code: 'WC-1600-SQ',
    product_name: 'Water Closet One Piece 1600mm',
    class_label: 'Water Closet',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 9, applicable: 45 },
    open_exceptions: 0,
    verification: verified('Aina Rahim', '2026-08-14T09:12:00'),
  },
  {
    product_code: 'SH-2400-RN',
    product_name: 'Rain Shower Set 240mm',
    class_label: 'Shower',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 8, applicable: 45 },
    open_exceptions: 0,
    verification: verified('Chan Wei Lun', '2026-08-15T15:40:00'),
  },
  {
    product_code: 'BS-0500-OV',
    product_name: 'Basin Countertop 500mm Oval',
    class_label: 'Basin',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 7, applicable: 45 },
    open_exceptions: 0,
    verification: needsReverify(
      'Aina Rahim',
      '2026-08-12T11:05:00',
      '2026-08-15T08:30:00',
      [
        { spec_key: 'shape', was: 'round', now: 'oval' },
        { spec_key: 'dim_width', was: '460', now: '500' },
        { spec_key: 'brand', was: 'SORENTO', now: 'SORENTO, TP ENTERPRISE' },
      ],
    ),
  },
  {
    product_code: 'SK-8600-UM',
    product_name: 'Undermount Kitchen Sink 860mm',
    class_label: 'Kitchen Sink',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 14, applicable: 52 },
    open_exceptions: 0,
    verification: needsReverify(
      'Nurul Hakim',
      '2026-08-11T16:20:00',
      '2026-08-16T07:55:00',
      [{ spec_key: 'dim_length', was: '760', now: '860' }],
    ),
  },
  {
    product_code: 'TP-0090-CH',
    product_name: 'Bib Tap Chrome',
    class_label: 'Tap',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 0, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
  },
  {
    product_code: 'WC-1300-EL',
    product_name: 'Water Closet Elongated 1300mm',
    class_label: 'Water Closet',
    brand_name: 'TP Enterprise',
    is_discontinued: false,
    coverage: { have: 6, applicable: 45 },
    open_exceptions: 2,
    verification: UNVERIFIED,
  },
  {
    product_code: 'SK-0900-DB',
    product_name: 'Double Bowl Kitchen Sink 900mm',
    class_label: 'Kitchen Sink',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 5, applicable: 52 },
    open_exceptions: 0,
    // Withdrawn by a person: reads unverified, and the history keeps both facts.
    verification: {
      state: 'unverified',
      verified_by_name: 'Aina Rahim',
      verified_at: '2026-08-10T10:00:00',
      invalidated_at: '2026-08-15T13:15:00',
      invalidated_reason: 'manual_unverify',
      invalidated_by_name: 'Nurul Hakim',
      invalidated_diff: null,
    },
  },
  {
    product_code: 'TP-0055-BK',
    product_name: 'Wall Mixer Matte Black',
    class_label: 'Tap',
    brand_name: 'Sorento',
    is_discontinued: false,
    coverage: { have: 3, applicable: 45 },
    open_exceptions: 0,
    verification: UNVERIFIED,
    driftsOnVerify: true,
  },
];

let mixedStateWorld: SpecVerificationRow[] | null = null;

function getMixedStateWorld(): SpecVerificationRow[] {
  if (mixedStateWorld) return mixedStateWorld;
  mixedStateWorld = MIXED_STATE_SEEDS.map((seed, i) => seedToRow(seed, 100000 + i));
  return mixedStateWorld;
}

/** Stamps applied in this tab, overlaying the seeded state. */
const stampOverlay = new Map<string, VerificationBlock>();
/** Hashes the mock has moved, so a re-verify after a refresh succeeds. */
const hashOverlay = new Map<string, string>();
const drifting = new Set<string>(
  [...DAY_ONE_SEEDS, ...MIXED_STATE_SEEDS]
    .filter((seed) => seed.driftsOnVerify)
    .map((seed) => seed.product_code),
);

function effective(row: SpecVerificationRow): SpecVerificationRow {
  const stamp = stampOverlay.get(row.product_code);
  const hash = hashOverlay.get(row.product_code);
  if (!stamp && !hash) return row;
  return {
    ...row,
    ...(stamp ? { verification: stamp } : {}),
    ...(hash ? { values_hash: hash } : {}),
  };
}

function findRow(productCode: string): SpecVerificationRow | undefined {
  const base =
    getMixedStateWorld().find((r) => r.product_code === productCode) ??
    getDayOneWorld().find((r) => r.product_code === productCode);
  return base ? effective(base) : undefined;
}

const STATE_RANK: Record<VerificationState, number> = {
  needs_reverify: 0,
  unverified: 1,
  verified: 2,
};

/** The work order (C6): needs re-verify first, then unverified by class then code. */
function compareDefault(a: SpecVerificationRow, b: SpecVerificationRow): number {
  const byState = STATE_RANK[a.verification.state] - STATE_RANK[b.verification.state];
  if (byState !== 0) return byState;
  const byClass = (a.class_label ?? '').localeCompare(b.class_label ?? '');
  if (byClass !== 0) return byClass;
  return a.product_code.localeCompare(b.product_code);
}

export function fetchMockWorklist(
  params: SpecVerificationWorklistParams,
): SpecVerificationWorklistResponse {
  const query = (params.searchQuery ?? '').trim();
  const switchKey = query.toLowerCase();
  const world = switchKey === 'states' ? getMixedStateWorld() : getDayOneWorld();
  const isSwitch = ['states', 'empty', 'error', 'loading'].includes(switchKey);

  let rows = world.map(effective);
  if (!params.include_discontinued) {
    rows = rows.filter((r) => !r.is_discontinued);
  }
  if (params.class_label) {
    rows = rows.filter((r) => r.class_label === params.class_label);
  }
  if (query && !isSwitch) {
    const needle = query.toLowerCase();
    rows = rows.filter(
      (r) =>
        r.product_code.toLowerCase().includes(needle) ||
        r.product_name.toLowerCase().includes(needle),
    );
  }
  if (switchKey === 'empty') {
    rows = [];
  }

  // The summary counts the same set the list does, minus the state filter, so
  // "Verified N of M" stays honest while a state filter is applied.
  const summary = {
    total: rows.length,
    verified: rows.filter((r) => r.verification.state === 'verified').length,
    needs_reverify: rows.filter((r) => r.verification.state === 'needs_reverify').length,
    unverified: rows.filter((r) => r.verification.state === 'unverified').length,
  };

  if (params.state) {
    rows = rows.filter((r) => r.verification.state === params.state);
  }

  const sortField = params.sorting?.[0]?.id ?? '';
  const descending = Boolean(params.sorting?.[0]?.desc);
  if (sortField === 'coverage') {
    rows = [...rows].sort(
      (a, b) => a.coverage.have - b.coverage.have || a.product_code.localeCompare(b.product_code),
    );
  } else if (sortField === 'code') {
    rows = [...rows].sort((a, b) => a.product_code.localeCompare(b.product_code));
  } else {
    rows = [...rows].sort(compareDefault);
  }
  if (sortField && descending) rows.reverse();

  const start = params.pageIndex * params.pageSize;
  return {
    data: rows.slice(start, start + params.pageSize),
    pagination: { total: rows.length, page: params.pageIndex + 1, limit: params.pageSize },
    summary,
  };
}

export function applyMockVerify(items: VerifyItem[]): VerifyBulkResult[] {
  const now = new Date().toISOString().slice(0, 19);
  return items.map(({ product_code }) => {
    const row = findRow(product_code);
    if (!row) return { product_code, outcome: 'not_found' as const };
    if (row.open_exceptions > 0) {
      return { product_code, outcome: 'exceptions_open' as const, verification: row.verification };
    }
    if (drifting.has(product_code)) {
      drifting.delete(product_code);
      const moved = `h${Math.random().toString(16).slice(2, 10)}`;
      hashOverlay.set(product_code, moved);
      return {
        product_code,
        outcome: 'values_changed' as const,
        values_hash: moved,
        verification: row.verification,
      };
    }
    if (row.verification.state === 'verified') {
      return {
        product_code,
        outcome: 'already_verified' as const,
        verification: row.verification,
      };
    }
    const stamp = verified(MOCK_ACTOR, now);
    stampOverlay.set(product_code, stamp);
    return {
      product_code,
      outcome: 'verified' as const,
      values_hash: row.values_hash,
      verification: stamp,
    };
  });
}

export function applyMockUnverify(productCodes: string[]): UnverifyBulkResult[] {
  const now = new Date().toISOString().slice(0, 19);
  return productCodes.map((product_code) => {
    const row = findRow(product_code);
    if (!row) return { product_code, outcome: 'no_change' as const };
    const current = row.verification;
    const alreadyWithdrawn =
      current.state === 'unverified' && current.invalidated_reason === 'manual_unverify';
    if (current.state === 'unverified' && (alreadyWithdrawn || !current.verified_at)) {
      return { product_code, outcome: 'no_change' as const, verification: current };
    }
    // The original credit stays on the row; the diff is cleared, because a
    // withdrawal has nothing to re-check.
    const stamp: VerificationBlock = {
      state: 'unverified',
      verified_by_name: current.verified_by_name,
      verified_at: current.verified_at,
      invalidated_at: now,
      invalidated_reason: 'manual_unverify',
      invalidated_by_name: MOCK_ACTOR,
      invalidated_diff: null,
    };
    stampOverlay.set(product_code, stamp);
    return { product_code, outcome: 'unverified' as const, verification: stamp };
  });
}
