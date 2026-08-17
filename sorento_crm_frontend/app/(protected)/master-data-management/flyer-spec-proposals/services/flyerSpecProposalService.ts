/**
 * ============================================================================
 * API CONTRACT - flyer / catalogue ingestion into product specifications (PR 5)
 * ============================================================================
 *
 * Written HERE, before any of it exists, because this is Phase 1: the screens
 * below were built against `__mocks__/flyerSpecProposals.fixtures.ts` and the
 * backend of Phase 2 is held to what is written in this block. A deviation is
 * allowed only by changing this block and the two sides in the same commit.
 *
 * Plan: `documentation/plans/master-data/PLAN-flyer-spec-ingestion.md` §3.4.
 * Contract: `flyer-spec-ingestion-acceptance-criteria.md`, sections A, B and C.
 *
 * Everything is under `/api/v1/dealer-kit`, because the flyer is the dealer
 * kit's object - the routes live beside `dimensions/apply`, which is the same
 * shape of act (read the kit, write the master). Every one of them requires
 * `dealer_kit.page.view` AND `master_data.products.edit`, declared in that
 * order, no API-key variant (AC-A.7 / L9).
 *
 * BODIES ARE snake_case, unlike the dealer kit's other routes.
 * These payloads carry `spec_key` / `stored_value` / `data_type` rows straight
 * into `components/spec-proposals`, which is the product-specification domain's
 * shared review component and speaks snake_case, as does every other spec
 * endpoint (`productSpecService.ts`). Two conventions inside one response - a
 * camelCase batch wrapping snake_case rows - is worse than one, and the UAC
 * names these fields in snake_case throughout (AC-B.1, AC-B.2, AC-C.1).
 *
 * READS
 *
 *   GET /flyer-readings/spec-proposal-batches
 *     -> FlyerSpecBatch[], newest first, within the caller's company scope.
 *        Declared BEFORE the `{reading_id}` routes so the static path wins.
 *        Never `status: 'none'` - a row in this list is a batch that exists.
 *
 *   GET /flyer-readings/{reading_id}/spec-proposals
 *     -> FlyerSpecProposals = the batch summary + `groups`.
 *        A reading with no batch answers 200 with `status: 'none'`, `id: null`,
 *        zero counts and no groups - NEVER a 404, because "not proposed yet" is
 *        an answer the screen has to render (AC-B.1).
 *        `groups` is filled only when `status` is `proposed`, in flyer page
 *        order, and each group names its product by CODE and NAME. The only
 *        UUIDs on the wire are `id` (the apply payload names them) and
 *        `product_id` (the link to the product record) - AC-B.3.
 *
 * WRITES
 *
 *   POST /flyer-readings/{reading_id}/spec-proposals            (no body)
 *     -> 202 FlyerSpecBatch with `status: 'proposing'`. The pass is an RQ job on
 *        the existing `flyer_read` queue, so this returns before it starts and
 *        the screen polls the GET above every 3 s until it settles.
 *        409 FLYER_NOT_READ_YET   - the reading is still processing, or failed.
 *        409 FLYER_SPEC_PROPOSING - a pass is already running for this reading.
 *        Re-proposing a settled batch deletes its proposals and runs again
 *        against the master as it is NOW (AC-A.5).
 *
 *   POST /flyer-readings/{reading_id}/spec-proposals/apply
 *        body { proposal_ids: string[] }   (1..5000, `extra="forbid"`)
 *     -> 200 FlyerSpecApplyResult
 *        IDS ONLY, never values (L8): the values come off the stored proposal,
 *        which came off the reading, so nothing on this path can put a number of
 *        its own into the product master. A body carrying `values` is a 422.
 *        Every selected row is re-classified against the LIVE spec row before it
 *        is written (AC-C.2), so a batch proposed yesterday cannot overwrite what
 *        somebody set this morning: `unchanged` -> `already_matches`, `conflict`
 *        or `suppressed` -> `conflict_not_confirmed`, and only `new` / `change`
 *        are written, as `source: 'flyer'` with the printed words as evidence.
 *        200 with refusals, never a 4xx for a refused row - a refusal is an
 *        answer, and the caller must read `refused`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { SpecProposal } from '@/components/spec-proposals';

import {
  mockApplyFlyerSpecProposals,
  mockGetFlyerSpecProposals,
  mockListFlyerSpecBatches,
  mockProposeFlyerSpecs,
} from '../__mocks__/flyerSpecProposals.fixtures';

/**
 * PHASE 1. Every call below answers from `__mocks__` while this is true.
 *
 * This is DEBT, and it is the one line Phase 2 flips (plan slice S3): the
 * fixtures go, this constant goes, and the four functions keep their signatures
 * so nothing above the service boundary moves.
 */
const USE_MOCK = true;

const BASE = '/api/v1/dealer-kit/flyer-readings';

/**
 * Where a proposal pass is.
 *
 * `none` is not a stored status - it is what the GET answers for a reading
 * nobody has proposed from yet, so the screen has one field to switch on rather
 * than a null check wrapped round four states.
 */
export type FlyerSpecBatchStatus = 'none' | 'proposing' | 'proposed' | 'failed';

/** Why a selected row was not written. Each one sends the reviewer somewhere else. */
export type FlyerSpecOutcome =
  | 'applied'
  | 'already_matches'
  | 'conflict_not_confirmed'
  | 'product_spec_bad_value'
  | 'product_not_found'
  | 'not_in_batch';

/** One proposal pass over one flyer reading. */
export interface FlyerSpecBatch {
  /** Null when `status` is `none`, and only then. */
  id: string | null;
  reading_id: string;
  /** The flyer's own name, so a list of batches needs no second call. */
  filename: string;
  status: FlyerSpecBatchStatus;
  /** Why the pass failed, in the words the job recorded. Null unless failed. */
  error_message: string | null;
  product_count: number;
  proposal_count: number;
  new_count: number;
  change_count: number;
  conflict_count: number;
  unchanged_count: number;
  suppressed_count: number;
  /** How many rows of this batch have ever been written. */
  applied_count: number;
  /** When the flyer itself was read. Null on a reading with no upload stamp. */
  read_at: string | null;
  /** When Propose was pressed. Null when `status` is `none`. */
  created_at: string | null;
  /** When the pass settled, whichever way. Null while it is still running. */
  finished_at: string | null;
  /** The latest apply. Null until something has been written. */
  applied_at: string | null;
  /** By NAME, never an id (AC-B.3). Null when nobody is recorded. */
  created_by_name: string | null;
  applied_by_name: string | null;
}

/**
 * One proposal row: the shared review's shape, plus what a STORED proposal has
 * that a freshly-extracted one does not - an id to name it by, and the outcome
 * of the last time somebody applied it.
 */
export interface FlyerSpecProposal extends SpecProposal {
  id: string;
  /** Null until this row has been through an apply. */
  outcome: FlyerSpecOutcome | null;
  applied_at: string | null;
}

/** Every proposal for one product, in the order the flyer prints it. */
export interface FlyerSpecProductGroup {
  product_id: string;
  product_code: string;
  product_name: string;
  /** Which flyer pages this product was printed on. */
  pages: number[];
  proposals: FlyerSpecProposal[];
}

export interface FlyerSpecProposals extends FlyerSpecBatch {
  /** Empty unless `status` is `proposed`. */
  groups: FlyerSpecProductGroup[];
}

export interface AppliedFlyerSpec {
  proposal_id: string;
  product_code: string;
  spec_key: string;
  value: SpecProposal['value'];
}

export interface RefusedFlyerSpec {
  proposal_id: string;
  product_code: string;
  spec_key: string;
  reason: FlyerSpecOutcome;
  /** The sentence to show. Never a code the reader has to look up. */
  message: string;
}

export interface FlyerSpecApplyResult {
  applied: AppliedFlyerSpec[];
  refused: RefusedFlyerSpec[];
}

/** An absent list is an empty one; an absent batch would hide the whole answer. */
function toBatch(
  wire: Partial<FlyerSpecBatch>,
  readingId = '',
): FlyerSpecBatch {
  return {
    id: wire.id ?? null,
    reading_id: wire.reading_id ?? readingId,
    filename: wire.filename ?? 'Untitled flyer',
    // Absent means nobody has proposed from this reading, which is the state the
    // screen opens in. Guessing `proposing` would poll forever for a job nobody
    // queued - the same rule `flyerReadingService.toStatus` follows.
    status: wire.status ?? 'none',
    error_message: wire.error_message ?? null,
    product_count: wire.product_count ?? 0,
    proposal_count: wire.proposal_count ?? 0,
    new_count: wire.new_count ?? 0,
    change_count: wire.change_count ?? 0,
    conflict_count: wire.conflict_count ?? 0,
    unchanged_count: wire.unchanged_count ?? 0,
    suppressed_count: wire.suppressed_count ?? 0,
    applied_count: wire.applied_count ?? 0,
    read_at: wire.read_at ?? null,
    created_at: wire.created_at ?? null,
    finished_at: wire.finished_at ?? null,
    applied_at: wire.applied_at ?? null,
    created_by_name: wire.created_by_name ?? null,
    applied_by_name: wire.applied_by_name ?? null,
  };
}

function toProposals(
  wire: Partial<FlyerSpecProposals>,
  readingId: string,
): FlyerSpecProposals {
  return { ...toBatch(wire, readingId), groups: wire.groups ?? [] };
}

/** Every proposal pass, newest first. The Master Data list is this call. */
export async function listFlyerSpecBatches(): Promise<FlyerSpecBatch[]> {
  if (USE_MOCK) return mockListFlyerSpecBatches();

  const response = await apiFetch(`${BASE}/spec-proposal-batches`);
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not load the flyer proposals'),
    );
  }
  const rows = (await response.json()) as Partial<FlyerSpecBatch>[];
  return (Array.isArray(rows) ? rows : []).map((row) => toBatch(row));
}

/**
 * The batch for one reading, and its rows when there are any.
 *
 * Answers on every state, including "nobody has proposed from this flyer",
 * because the reading page renders this section whatever the answer is.
 */
export async function getFlyerSpecProposals(
  readingId: string,
): Promise<FlyerSpecProposals> {
  if (USE_MOCK) return mockGetFlyerSpecProposals(readingId);

  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals`,
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not load the flyer proposals'),
    );
  }
  return toProposals(await response.json(), readingId);
}

/**
 * Read this flyer onto the products it names, and propose - never write.
 *
 * 202 with the batch in `proposing`: the pass is a queued job, so what comes
 * back is the row that will hold the answer, and the caller polls for it.
 */
export async function proposeFlyerSpecs(
  readingId: string,
): Promise<FlyerSpecBatch> {
  if (USE_MOCK) return mockProposeFlyerSpecs(readingId);

  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(
        response,
        'Could not read specifications from this flyer',
      ),
    );
  }
  return toBatch(await response.json(), readingId);
}

/**
 * Write the ticked rows to the product master.
 *
 * The request carries IDS and nothing else. 200 with a body rather than 207: a
 * refusal is an answer, and the caller renders `refused` beside `applied` so a
 * screen cannot report a success over three rows that silently did not land.
 */
export async function applyFlyerSpecProposals(
  readingId: string,
  proposalIds: string[],
): Promise<FlyerSpecApplyResult> {
  if (USE_MOCK) return mockApplyFlyerSpecProposals(readingId, proposalIds);

  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals/apply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_ids: proposalIds }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not apply these specifications'),
    );
  }

  const wire = (await response.json()) as Partial<FlyerSpecApplyResult>;
  return {
    applied: wire.applied ?? [],
    // Never defaulted away silently: an absent `refused` read as "nothing was
    // refused" is exactly the silence this endpoint exists to break.
    refused: wire.refused ?? [],
  };
}
