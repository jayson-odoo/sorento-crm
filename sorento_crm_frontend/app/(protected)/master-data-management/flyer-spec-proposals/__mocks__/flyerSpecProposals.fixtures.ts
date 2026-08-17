/**
 * PHASE 1 ONLY. The whole feature, in memory, so the screens can be built and
 * judged before a single backend row exists (PRINCIPLES phase 3).
 *
 * This file and the `USE_MOCK` constant in the service are the debt Phase 2
 * deletes (plan slice S3). Nothing above the service boundary imports it.
 *
 * It is a small STORE rather than four frozen objects, because the states that
 * matter most here are the transitions: none -> proposing -> proposed, and the
 * second apply of a batch that was already applied (AC-C.6, which is the whole
 * argument for showing `unchanged` rows at all). A frozen fixture can show the
 * end states and none of the moves between them.
 *
 * Every state is reachable two ways:
 *
 *  - by READING ID, for the Master Data list: five readings are seeded, one per
 *    state, and the id says which (`flyer-mixed`, `flyer-empty`, `flyer-failed`,
 *    `flyer-proposing`, `flyer-none`). A suffix match, so a real UUID ending in
 *    `-empty` lands on the same fixture.
 *  - by PRESSING PROPOSE on any other reading, which is how the dealer kit page
 *    reaches them: an unknown reading is `none`, proposing it shows `proposing`
 *    for a few seconds and then settles on the mixed batch.
 */
import type {
  FlyerSpecApplyResult,
  FlyerSpecBatch,
  FlyerSpecOutcome,
  FlyerSpecProductGroup,
  FlyerSpecProposal,
  FlyerSpecProposals,
  RefusedFlyerSpec,
} from '../services/flyerSpecProposalService';

/** Long enough that the 3 s poll ticks at least once before it settles. */
const PROPOSE_MS = 4000;
/** Enough to see a spinner, not enough to be a wait. */
const READ_MS = 250;
const WRITE_MS = 450;

function delay<T>(value: T, ms: number): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function nowStamp(): string {
  // Naive, no zone: exactly what the backend stores and what
  // `formatDateTimeInMalaysia` is given everywhere else.
  return new Date().toISOString().slice(0, 19);
}

/**
 * The one row that refuses, so the refusal half of the result table is not
 * theatre.
 *
 * `trap_length` on the bathtub comes back as a value the registry will not take.
 * It is a `change`, so it is unticked by default and the golden path applies
 * cleanly; ticking it is how a reviewer sees what AC-C.4 does - the whole
 * PRODUCT's selected rows are refused together, because one product is one
 * `apply_spec_values` call.
 */
const BAD_VALUE_KEY = 'trap_length';
const BAD_VALUE_MESSAGE =
  'The registry does not accept 200 for Trap outlet length';

let sequence = 0;
function nextId(prefix: string): string {
  sequence += 1;
  return `${prefix}-${sequence}`;
}

function proposal(
  row: Omit<FlyerSpecProposal, 'id' | 'outcome' | 'applied_at'>,
): FlyerSpecProposal {
  return { ...row, id: nextId('proposal'), outcome: null, applied_at: null };
}

/** The three products, mixed kinds, one of them holding nothing but `unchanged`. */
function mixedGroups(): FlyerSpecProductGroup[] {
  return [
    {
      product_id: 'product-wc-8066',
      product_code: 'SRTWC8066',
      product_name: 'Sorento Wall Hung Water Closet',
      pages: [3],
      proposals: [
        proposal({
          spec_key: 'seat_material',
          label: 'Seat cover material',
          data_type: 'text',
          value: 'pp',
          unit: null,
          evidence: '*PP Seat Cover With Soft Close',
          kind: 'new',
          stored_value: null,
          stored_unit: null,
          stored_source: null,
        }),
        proposal({
          spec_key: 'is_rimless',
          label: 'Rimless',
          data_type: 'boolean',
          value: true,
          unit: null,
          evidence: 'Washdown With Rimless Design',
          kind: 'new',
          stored_value: null,
          stored_unit: null,
          stored_source: null,
        }),
        proposal({
          spec_key: 'dim_height',
          label: 'Height',
          data_type: 'numeric',
          value: 770,
          unit: 'mm',
          evidence: 'D: L680 x W375 x H770mm',
          kind: 'change',
          stored_value: 750,
          stored_unit: 'mm',
          stored_source: 'derived',
        }),
        proposal({
          spec_key: 'finish',
          label: 'Finish or colour',
          data_type: 'text',
          value: 'matt_black',
          unit: null,
          evidence: 'Matt Black / Chrome',
          kind: 'conflict',
          stored_value: 'chrome',
          stored_unit: null,
          stored_source: 'human',
        }),
        proposal({
          spec_key: 'flush_type',
          label: 'Flush type',
          data_type: 'text',
          value: 'dual',
          unit: null,
          evidence: 'Dual Flush 3L / 4.5L',
          kind: 'suppressed',
          stored_value: null,
          stored_unit: null,
          stored_source: 'human',
        }),
      ],
    },
    {
      product_id: 'product-bt-1700',
      product_code: 'SRTBT1700',
      product_name: 'Sorento Freestanding Bathtub 1700',
      pages: [7, 11],
      proposals: [
        proposal({
          spec_key: 'dim_length',
          label: 'Length',
          data_type: 'numeric',
          value: 1700,
          unit: 'mm',
          evidence: 'L1700 x W800 x H590mm',
          kind: 'new',
          stored_value: null,
          stored_unit: null,
          stored_source: null,
        }),
        proposal({
          spec_key: 'material',
          label: 'Material',
          data_type: 'text',
          value: 'acrylic',
          unit: null,
          evidence: 'High Gloss Acrylic With Reinforced Base',
          kind: 'new',
          stored_value: null,
          stored_unit: null,
          stored_source: null,
        }),
        proposal({
          spec_key: BAD_VALUE_KEY,
          label: 'Trap outlet length',
          data_type: 'numeric',
          value: 200,
          unit: 'mm',
          evidence: 'Trap 200mm',
          kind: 'change',
          stored_value: 180,
          stored_unit: 'mm',
          stored_source: 'derived',
        }),
        proposal({
          spec_key: 'dim_width',
          label: 'Width',
          data_type: 'numeric',
          value: 800,
          unit: 'mm',
          evidence: 'L1700 x W800 x H590mm',
          kind: 'unchanged',
          stored_value: 800,
          stored_unit: 'mm',
          stored_source: 'derived',
        }),
        proposal({
          spec_key: 'has_overflow',
          label: 'Overflow',
          data_type: 'boolean',
          value: true,
          unit: null,
          evidence: 'With Overflow And Pop Up Waste',
          kind: 'suppressed',
          stored_value: null,
          stored_unit: null,
          stored_source: 'human',
        }),
      ],
    },
    {
      // The product the flyer says nothing new about. It is listed rather than
      // dropped, because "this page changed nothing" is the answer a second
      // ingest of the same flyer has to be able to give.
      product_id: 'product-bs-600',
      product_code: 'SRTBS600',
      product_name: 'Sorento Counter Top Basin 600',
      pages: [14],
      proposals: [
        proposal({
          spec_key: 'dim_width',
          label: 'Width',
          data_type: 'numeric',
          value: 600,
          unit: 'mm',
          evidence: 'W600 x D420 x H145mm',
          kind: 'unchanged',
          stored_value: 600,
          stored_unit: 'mm',
          stored_source: 'derived',
        }),
        proposal({
          spec_key: 'finish',
          label: 'Finish or colour',
          data_type: 'text',
          value: 'white',
          unit: null,
          evidence: 'Glossy White',
          kind: 'unchanged',
          stored_value: 'white',
          stored_unit: null,
          stored_source: 'human',
        }),
      ],
    },
  ];
}

/** Counts are never typed by hand: they would drift from the rows on the first edit. */
function withCounts(batch: FlyerSpecProposals): FlyerSpecProposals {
  const rows = batch.groups.flatMap((group) => group.proposals);
  const of = (kind: string) => rows.filter((row) => row.kind === kind).length;
  return {
    ...batch,
    product_count: batch.groups.length,
    proposal_count: rows.length,
    new_count: of('new'),
    change_count: of('change'),
    conflict_count: of('conflict'),
    unchanged_count: of('unchanged'),
    suppressed_count: of('suppressed'),
    applied_count: rows.filter((row) => row.outcome === 'applied').length,
  };
}

function baseBatch(readingId: string, filename: string): FlyerSpecProposals {
  return {
    id: null,
    reading_id: readingId,
    filename,
    status: 'none',
    error_message: null,
    product_count: 0,
    proposal_count: 0,
    new_count: 0,
    change_count: 0,
    conflict_count: 0,
    unchanged_count: 0,
    suppressed_count: 0,
    applied_count: 0,
    read_at: '2026-08-16T09:12:00',
    created_at: null,
    finished_at: null,
    applied_at: null,
    created_by_name: null,
    applied_by_name: null,
    groups: [],
  };
}

function proposedBatch(
  readingId: string,
  filename: string,
  groups: FlyerSpecProductGroup[],
): FlyerSpecProposals {
  return withCounts({
    ...baseBatch(readingId, filename),
    id: nextId('batch'),
    status: 'proposed',
    created_at: '2026-08-16T10:02:00',
    finished_at: '2026-08-16T10:02:41',
    created_by_name: 'Aisyah Rahman',
    groups,
  });
}

/** Which settled shape a reading of this name lands on when Propose finishes. */
function settledFor(readingId: string, filename: string): FlyerSpecProposals {
  const id = readingId.toLowerCase();
  if (id.endsWith('empty')) {
    return proposedBatch(readingId, filename, []);
  }
  if (id.endsWith('failed')) {
    return {
      ...baseBatch(readingId, filename),
      id: nextId('batch'),
      status: 'failed',
      error_message:
        'The specification rules could not be loaded while reading this flyer',
      created_at: '2026-08-16T10:02:00',
      finished_at: '2026-08-16T10:02:08',
      created_by_name: 'Aisyah Rahman',
    };
  }
  return proposedBatch(readingId, filename, mixedGroups());
}

/** The seeded readings, one per state. The list page is these rows. */
const SEEDS: [string, string][] = [
  ['flyer-mixed', 'Sorento Bathroom Collection 2026 A3.pdf'],
  ['flyer-empty', 'Kitchen Sinks Reprint March.pdf'],
  ['flyer-failed', 'Showroom Poster Set.pdf'],
  ['flyer-proposing', 'Sanitary Ware Season 2 Draft.pdf'],
  ['flyer-none', 'Tapware Leaflet A5.pdf'],
];

const store = new Map<string, FlyerSpecProposals>();

function seed(): void {
  if (store.size > 0) return;
  for (const [readingId, filename] of SEEDS) {
    if (readingId === 'flyer-none') {
      store.set(readingId, baseBatch(readingId, filename));
      continue;
    }
    if (readingId === 'flyer-proposing') {
      store.set(readingId, {
        ...baseBatch(readingId, filename),
        id: nextId('batch'),
        status: 'proposing',
        created_at: '2026-08-17T08:40:00',
        created_by_name: 'Aisyah Rahman',
      });
      continue;
    }
    store.set(readingId, settledFor(readingId, filename));
  }
}

function entry(readingId: string): FlyerSpecProposals {
  seed();
  const held = store.get(readingId);
  if (held) return held;
  const suffixed = SEEDS.find(([id]) => readingId.toLowerCase().endsWith(id));
  if (suffixed) return store.get(suffixed[0]) as FlyerSpecProposals;
  // Any other reading - the real ones the dealer kit page opens - starts with
  // nothing proposed, which is the state that screen is built to open in.
  const fresh = baseBatch(readingId, 'This flyer');
  store.set(readingId, fresh);
  return fresh;
}

/**
 * The batch without its rows, which is what the list and the 202 answer with.
 *
 * Dropped rather than left on: a fixture that hands back rows where the real
 * endpoint sends none is a fixture the screens can accidentally rely on.
 */
function summaryOf(batch: FlyerSpecProposals): FlyerSpecBatch {
  const summary: Partial<FlyerSpecProposals> = { ...batch };
  delete summary.groups;
  return summary as FlyerSpecBatch;
}

/** A deep-enough copy that a screen holding the answer cannot mutate the store. */
function clone(batch: FlyerSpecProposals): FlyerSpecProposals {
  return {
    ...batch,
    groups: batch.groups.map((group) => ({
      ...group,
      proposals: group.proposals.map((row) => ({ ...row })),
    })),
  };
}

export function mockGetFlyerSpecProposals(
  readingId: string,
): Promise<FlyerSpecProposals> {
  return delay(clone(entry(readingId)), READ_MS);
}

export function mockListFlyerSpecBatches(): Promise<FlyerSpecBatch[]> {
  seed();
  const rows = [...store.values()]
    .filter((batch) => batch.status !== 'none')
    .map(summaryOf)
    .sort((left, right) =>
      (right.created_at ?? '').localeCompare(left.created_at ?? ''),
    );
  return delay(rows, READ_MS);
}

export function mockProposeFlyerSpecs(
  readingId: string,
): Promise<FlyerSpecBatch> {
  const current = entry(readingId);
  const running: FlyerSpecProposals = {
    ...baseBatch(readingId, current.filename),
    id: nextId('batch'),
    status: 'proposing',
    read_at: current.read_at,
    created_at: nowStamp(),
    created_by_name: 'Aisyah Rahman',
  };
  store.set(readingId, running);

  // The pass is a queued job, so it settles on its own and the screen finds out
  // by polling - exactly the shape the real one has.
  setTimeout(() => {
    const settled = settledFor(readingId, current.filename);
    store.set(readingId, {
      ...settled,
      id: running.id,
      created_at: running.created_at,
    });
  }, PROPOSE_MS);

  return delay(summaryOf(running), WRITE_MS);
}

function outcomeFor(kind: FlyerSpecProposal['kind']): FlyerSpecOutcome {
  if (kind === 'unchanged') return 'already_matches';
  if (kind === 'new' || kind === 'change') return 'applied';
  return 'conflict_not_confirmed';
}

const REFUSAL_MESSAGE: Record<string, string> = {
  already_matches: 'The product already holds this value',
  conflict_not_confirmed:
    'A person set this value, so a bulk apply will not replace it. Change it on the product itself.',
  product_spec_bad_value: BAD_VALUE_MESSAGE,
  not_in_batch: 'This proposal is not part of this batch',
};

export function mockApplyFlyerSpecProposals(
  readingId: string,
  proposalIds: string[],
): Promise<FlyerSpecApplyResult> {
  const batch = entry(readingId);
  const selected = new Set(proposalIds);
  const applied: FlyerSpecApplyResult['applied'] = [];
  const refused: RefusedFlyerSpec[] = [];
  const seen = new Set<string>();

  for (const group of batch.groups) {
    const rows = group.proposals.filter((row) => selected.has(row.id));
    // One product is one write, so one bad value refuses the whole product's
    // selection - the shape AC-C.4 asks the screen to render.
    const productFails = rows.some((row) => row.spec_key === BAD_VALUE_KEY);

    for (const row of rows) {
      seen.add(row.id);
      const outcome: FlyerSpecOutcome = productFails
        ? 'product_spec_bad_value'
        : outcomeFor(row.kind);
      row.outcome = outcome;
      row.applied_at = nowStamp();

      if (outcome === 'applied') {
        applied.push({
          proposal_id: row.id,
          product_code: group.product_code,
          spec_key: row.spec_key,
          value: row.value,
        });
        // What the product holds has moved, so the row now reads as what a
        // re-propose would produce. This is what makes a second apply of the
        // same selection answer `already_matches` (AC-C.6).
        row.kind = 'unchanged';
        row.stored_value = row.value;
        row.stored_unit = row.unit;
        row.stored_source = 'flyer';
        continue;
      }
      refused.push({
        proposal_id: row.id,
        product_code: group.product_code,
        spec_key: row.spec_key,
        reason: outcome,
        message: REFUSAL_MESSAGE[outcome] ?? 'This row was not written',
      });
    }
  }

  for (const id of proposalIds) {
    if (seen.has(id)) continue;
    refused.push({
      proposal_id: id,
      product_code: '',
      spec_key: '',
      reason: 'not_in_batch',
      message: REFUSAL_MESSAGE.not_in_batch,
    });
  }

  const stamped = nowStamp();
  store.set(
    readingId,
    withCounts({
      ...batch,
      applied_at: applied.length > 0 ? stamped : batch.applied_at,
      applied_by_name:
        applied.length > 0 ? 'Aisyah Rahman' : batch.applied_by_name,
    }),
  );

  return delay({ applied, refused }, WRITE_MS);
}
