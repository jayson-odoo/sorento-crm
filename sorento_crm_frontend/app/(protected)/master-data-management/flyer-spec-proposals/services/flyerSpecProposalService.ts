/**
 * ============================================================================
 * API CONTRACT - flyer / catalogue ingestion into product specifications (PR 5)
 * ============================================================================
 *
 * Written HERE before any of it existed, in Phase 1, when the screens below
 * answered from an in-memory mock. Phase 2 built the backend to this block and
 * this service now calls it; the block stays because it is the contract, and a
 * deviation is allowed only by changing it and the two sides in one commit.
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
 *        order, base before its own siblings - the FE never re-sorts this.
 *        Each group names its product by CODE and NAME. The only UUIDs on the
 *        wire are `id` (the apply payload names them) and `product_id` (the
 *        link to the product record) - AC-B.3.
 *
 *        `via_product_code` (PLAN-flyer-family-proposals.md, R1): null on a
 *        group proposed from its own printed code; the base's printed code
 *        (e.g. `SRTWC8152-SH`) on a group that got its reading from that
 *        card because its own code is `<that code>-<suffix>` and it was never
 *        printed itself. `via_count` on the batch is how many groups that is.
 *        Read as `viaProductCode` / `viaCount` below.
 *
 * WRITES
 *
 *   POST /flyer-readings/{reading_id}/spec-proposals            (no body)
 *     -> 202 FlyerSpecBatch with `status: 'proposing'`. The pass is an RQ job on
 *        the existing `flyer_read` queue, so this returns before it starts and
 *        the screen polls the GET above every 3 s until it settles.
 *        409 FLYER_NOT_READ_YET - the reading is still processing, or failed.
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
 *        somebody set this morning: `unchanged` -> `already_matches`,
 *        `suppressed` -> `conflict_not_confirmed`, and `new` / `change` /
 *        `conflict` are written (AC-F.1: a ticked conflict IS the confirmation,
 *        which is why the dialog names the count first). A row the flyer stated
 *        writes as `source: 'flyer'` with the printed words as evidence; a row a
 *        person added writes as `source: 'human'` with "set during flyer review"
 *        (AC-G.2).
 *        200 with refusals, never a 4xx for a refused row - a refusal is an
 *        answer, and the caller must read `refused`.
 *
 *   PATCH /flyer-readings/{reading_id}/spec-proposals/{proposal_id}
 *        body { value }   (`extra="forbid"`)
 *     -> 200 FlyerSpecProposal, the whole row back (AC-F.2). The value is
 *        validated against the registry, stored on the PROPOSAL with an edit
 *        stamp, and the row's `kind` is recomputed against the LIVE spec row -
 *        so correcting a value to what the product already holds turns the row
 *        `unchanged` and the screen stops offering to write it. The apply still
 *        names ids only (L8).
 *        400 product_spec_bad_value - the registry's own words.
 *        409 FLYER_SPEC_NOT_PROPOSED / FLYER_SPEC_ALREADY_APPLIED.
 *
 *   POST /flyer-readings/{reading_id}/spec-proposals/rows
 *        body { product_id, spec_key, value }   (`extra="forbid"`)
 *     -> 201 FlyerSpecProposal with `origin: 'manual'` and `kind` computed live
 *        (AC-G.1). The product must already be in this batch and the key must be
 *        one the registry defines AND one this product's class can carry - the
 *        same scope gate the propose pass applies.
 *        404 flyer_spec_unknown_key / not_in_batch.
 *        400 product_spec_bad_value / flyer_spec_key_not_applicable.
 *        409 flyer_spec_duplicate_row - the flyer already proposed this key for
 *        this product, and editing that row is the answer.
 *
 *   DELETE /flyer-readings/{reading_id}/spec-proposals/{proposal_id}
 *     -> 200 FlyerSpecBatch, the summary with its counts already moved (AC-G.3).
 *        A HARD delete of a proposal nobody accepted. 409 when the row has
 *        already been written - that value is changed on the product itself.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { SpecProposal } from '@/components/spec-proposals';

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

/** Who put a proposal row on the batch. The paper, or a person reviewing it. */
export type FlyerSpecOrigin = 'flyer' | 'manual';

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
  /**
   * How many of `product_count` are a sibling picked up via a family card
   * (PLAN-flyer-family-proposals.md, R1) rather than their own printed code.
   * Zero on a batch with no families, and on any batch proposed before the
   * feature existed.
   */
  viaCount: number;
}

/**
 * One proposal row: the shared review's shape, plus what a STORED proposal has
 * that a freshly-extracted one does not - an id to name it by, and the outcome
 * of the last time somebody applied it.
 */
export interface FlyerSpecProposal extends SpecProposal {
  id: string;
  /**
   * `flyer` when the pass read it off the paper, `manual` when a person added it
   * on the review screen. It decides the SOURCE the value is written under, so
   * it is carried rather than inferred from the edit stamp (AC-G.2).
   */
  origin: FlyerSpecOrigin;
  /** True once somebody has corrected this row's value in place (AC-F.2). */
  edited: boolean;
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
  /**
   * The printed code whose card filled this group's gaps, when this product
   * was never itself printed on the flyer - e.g. `SRTWC8152-SH` on the group
   * for `SRTWC8152-SH-UF-300` (PLAN-flyer-family-proposals.md, R1). Null on
   * the base itself and on any product proposed from its own card.
   */
  viaProductCode: string | null;
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

/**
 * The wire shapes below stay snake_case, matching the backend's response
 * bodies exactly (see the module docstring) - `via_count` / `via_product_code`
 * are the two exceptions mapped to camelCase, because the review screen and
 * `countsSentence` already read `viaCount` / `viaProductCode`.
 */
type FlyerSpecBatchWire = Partial<FlyerSpecBatch> & { via_count?: number };

type FlyerSpecProductGroupWire = Partial<FlyerSpecProductGroup> & {
  via_product_code?: string | null;
};

/** An absent list is an empty one; an absent batch would hide the whole answer. */
function toBatch(
  wire: FlyerSpecBatchWire,
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
    viaCount: wire.via_count ?? 0,
  };
}

function toGroup(wire: FlyerSpecProductGroupWire): FlyerSpecProductGroup {
  return {
    product_id: wire.product_id ?? '',
    product_code: wire.product_code ?? '',
    product_name: wire.product_name ?? '',
    pages: wire.pages ?? [],
    viaProductCode: wire.via_product_code ?? null,
    proposals: wire.proposals ?? [],
  };
}

function toProposals(
  wire: FlyerSpecBatchWire & { groups?: FlyerSpecProductGroupWire[] },
  readingId: string,
): FlyerSpecProposals {
  return {
    ...toBatch(wire, readingId),
    groups: (wire.groups ?? []).map(toGroup),
  };
}

/** Every proposal pass, newest first. The Master Data list is this call. */
export async function listFlyerSpecBatches(): Promise<FlyerSpecBatch[]> {
  const response = await apiFetch(`${BASE}/spec-proposal-batches`);
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not load the flyer proposals'),
    );
  }
  const rows = (await response.json()) as FlyerSpecBatchWire[];
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

/**
 * Correct one proposal's value before it is applied (AC-F.2).
 *
 * The value goes to the PROPOSAL, never to the product: the apply is still the
 * only write, and it still names ids. The whole row comes back because its
 * `kind` may have moved - a value corrected to what the product already holds is
 * `unchanged`, and the screen must stop offering to write it.
 */
export async function editFlyerSpecProposal(
  readingId: string,
  proposalId: string,
  value: SpecProposal['value'],
): Promise<FlyerSpecProposal> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals/${encodeURIComponent(proposalId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not save that value'),
    );
  }
  return (await response.json()) as FlyerSpecProposal;
}

/**
 * Add a specification the flyer states in a way no rule caught (AC-G.1).
 *
 * The product has to be one this batch already names. Adding a key to a product
 * the flyer never mentioned is a job for that product's own Specifications tab.
 */
export async function addFlyerSpecProposalRow(
  readingId: string,
  input: { product_id: string; spec_key: string; value: SpecProposal['value'] },
): Promise<FlyerSpecProposal> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals/rows`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not add that specification'),
    );
  }
  return (await response.json()) as FlyerSpecProposal;
}

/**
 * Take a proposal off the batch (AC-G.3).
 *
 * A hard delete of something nobody accepted. The batch summary comes back so
 * the counts move with the row.
 */
export async function dismissFlyerSpecProposal(
  readingId: string,
  proposalId: string,
): Promise<FlyerSpecBatch> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/spec-proposals/${encodeURIComponent(proposalId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not dismiss that proposal'),
    );
  }
  return toBatch(await response.json(), readingId);
}
