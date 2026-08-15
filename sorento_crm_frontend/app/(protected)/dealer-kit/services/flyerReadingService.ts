/**
 * Reading a printed flyer, and seeding a brochure from it (S7.3 / S7.4).
 *
 * ---------------------------------------------------------------------------
 * CONTRACT - `app/api/v1/dealer_kit/flyer_readings.py`, all under
 * `/api/v1/dealer-kit`. Writes carry `dealer_kit.page.edit`, reads carry
 * `dealer_kit.page.view`. Another company's reading is a 404, never a 403.
 * ---------------------------------------------------------------------------
 *
 * POST   /flyer-readings                     multipart `file`, `?promotionId=`
 *          -> 201 FlyerReading (summary + report)
 *          Read INSIDE the request. Measured on the real 36 page A3 flyer
 *          (20.1 MB, 998 codes): 17 to 18 s on a quiet machine, 39 to 62 s on
 *          a loaded one. The caller waits for all of it, so this is a slow
 *          call, not a fast one - see the plan's Backlog for the queue.
 *          400 when the file is not a PDF, 413 over 50 MB, and both say so in
 *          words - a designer who uploaded the wrong file must be told.
 * POST   /flyer-readings/from-attachment  {attachmentId, promotionId?}
 *          -> 201 FlyerReading, identical in every respect to an upload.
 *          Same permission, same limits, same words on a refusal. An
 *          attachment outside the caller's company scope is a 404, never a
 *          403, so the id's existence is not confirmed.
 * GET    /flyer-readings                     -> FlyerReadingSummary[], newest
 *          first, WITHOUT reports: one report per row is one match run per row.
 * GET    /flyer-readings/{id}?promotionId=   -> FlyerReading
 * POST   /flyer-readings/{id}/seed  {pageId | name+slug, promotionId?,
 *          commitMessage?}                   -> 201 FlyerSeedResult
 * POST   /flyer-readings/{id}/dimensions/apply {codes[], overwriteConflicts?}
 *          -> 200 DimensionApplyResult
 *          The ONE route here that writes outside the Kit. It needs
 *          `dealer_kit.page.view` AND `master_data.products.edit`, both: see
 *          `applyDimensions` below.
 * DELETE /flyer-readings/{id}                -> 204, hard
 *
 * ## What the report is, and what it is not
 *
 * **The report is never stored.** It is recomputed against the product master
 * on every read, so a code listed as missing stops being listed the moment
 * somebody creates it. That is why `promotionId` is asked on the READ as well
 * as on the upload: "what does this promotion not carry" is a question about
 * the report rather than a property of the file, and a reviewer tries it
 * against two promotions without uploading twice.
 *
 * **`unmatched` is a list of products that will NOT be in the brochure.** The
 * seed drops them, deliberately (PLAN D8): a collection pins product ids, so a
 * code the master does not have cannot be pinned, and inventing a product for
 * one would put a SKU nobody stocks in front of a customer. The suggestion is a
 * trigram nearest match and is never applied by anything here.
 *
 * **`dimensionCandidates` are reported, and applied only one explicit click at
 * a time** (PLAN D9, S7.6). Reading a flyer still writes nothing to `products`
 * (AC-D4); `applyDimensions` is a separate act, needs the master-data
 * permission, names the codes it is applying, and refuses to overwrite a value
 * the master already holds unless it is told to.
 *
 * **`headings` is what the READER found, not what the paper says.** Detection is
 * a heuristic - it reads "Transforming Your" where the paper says "BATHTUB
 * COLLECTION" - and the wrong value is shown deliberately, because a reviewer
 * can only correct what they can see. It comes off the stored reading rather
 * than the report, so unlike everything else here it does not move when a
 * product is created, and the seed writes these same values as its section
 * names.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/dealer-kit/flyer-readings';

/** `verdict` on a dimension candidate. `conflicts` is the one that matters. */
export type DimensionVerdict = 'missing' | 'agrees' | 'conflicts';

export interface CodeSuggestion {
  productId: string;
  productCode: string;
  productName: string;
  /** 0..1. Shown because a suggestion with no number behind it reads as a fact. */
  similarity: number;
}

export interface MatchedCode {
  code: string;
  productId: string;
  productCode: string;
  productName: string;
  /** Every page it was printed on. A reviewer is holding the paper. */
  pages: number[];
}

export interface UnmatchedCode {
  code: string;
  pages: number[];
  /** The nearest existing code. Never the answer, and never applied silently. */
  suggestion: CodeSuggestion | null;
}

export interface DimensionCandidate {
  code: string;
  productId: string;
  pages: number[];
  printedLengthMm: number;
  printedWidthMm: number;
  printedHeightMm: number;
  currentLengthMm: number | null;
  currentWidthMm: number | null;
  currentHeightMm: number | null;
  verdict: DimensionVerdict;
}

export interface MatchReport {
  matched: MatchedCode[];
  unmatched: UnmatchedCode[];
  notPromoted: MatchedCode[];
  dimensionCandidates: DimensionCandidate[];
  /** Code -> every page it was printed on, for codes printed more than once. */
  duplicates: Record<string, number[]>;
  /** Which promotion the report was computed against, if any. */
  promotionId: string | null;
}

export interface FlyerReadingSummary {
  id: string;
  filename: string;
  byteSize: number;
  pageCount: number;
  codeCount: number;
  uploadedAt: string;
}

/** What the reader thinks one flyer page is called. */
export interface PageHeading {
  page: number;
  /** Null where the reader found no heading. The page is still listed. */
  text: string | null;
}

export interface FlyerReading extends FlyerReadingSummary {
  report: MatchReport;
  /** Every page, in printed order, so the list reads beside the paper. */
  headings: PageHeading[];
}

/** Why a named code was not written. Each one sends a reviewer somewhere else. */
export type DimensionRefusalReason =
  | 'conflict_not_confirmed'
  | 'already_matches'
  | 'product_not_found'
  | 'not_a_candidate';

export interface DimensionApplyInput {
  /** The codes to write. Never empty: there is no "apply everything you found". */
  codes: string[];
  /**
   * Permission to replace a value somebody entered, for the named codes ONLY.
   * The server refuses a conflicting row without it, which is also what catches
   * a row somebody else filled in while this screen was open.
   */
  overwriteConflicts?: boolean;
}

export interface AppliedDimension {
  code: string;
  productCode: string;
  productName: string;
  pages: number[];
  lengthMm: number;
  widthMm: number;
  heightMm: number;
  /** What the master held before. The only place the replaced value survives. */
  previousLengthMm: number | null;
  previousWidthMm: number | null;
  previousHeightMm: number | null;
  wasConflict: boolean;
}

export interface RefusedDimension {
  code: string;
  reason: DimensionRefusalReason;
  message: string;
}

export interface DimensionApplyResult {
  applied: AppliedDimension[];
  refused: RefusedDimension[];
  appliedCount: number;
  refusedCount: number;
}

export interface FlyerSeedInput {
  /** Re-seed an existing brochure as a NEW version. Exclusive with name+slug. */
  pageId?: string;
  name?: string;
  slug?: string;
  /** Which promotion prices the brochure. Omitted on a re-seed means "leave it alone". */
  promotionId?: string | null;
  commitMessage?: string;
}

export interface FlyerSeedResult {
  pageId: string;
  name: string;
  slug: string;
  publicPath: string | null;
  versionId: string;
  version: number;
  sectionCount: number;
  collectionCount: number;
  seededProductCount: number;
  /** Printed codes that reached no tile. The same shape the report uses. */
  skipped: UnmatchedCode[];
}

/** An absent list is an empty one; an absent report would hide the whole answer. */
function toReport(wire: Partial<MatchReport> | undefined): MatchReport {
  return {
    matched: wire?.matched ?? [],
    unmatched: wire?.unmatched ?? [],
    notPromoted: wire?.notPromoted ?? [],
    dimensionCandidates: wire?.dimensionCandidates ?? [],
    duplicates: wire?.duplicates ?? {},
    promotionId: wire?.promotionId ?? null,
  };
}

/**
 * The fields a ROW carries, and only those.
 *
 * Split out from `toReading` so the list cannot grow detail fields by accident.
 * It used to build a whole reading and destructure `report` back off, which
 * meant every field added to the detail response had to be remembered and
 * stripped here too - and the first one that was not (`headings`) put an empty
 * list on every row of a screen whose endpoint never sends one.
 */
function toSummary(wire: Partial<FlyerReadingSummary>): FlyerReadingSummary {
  return {
    id: String(wire.id ?? ''),
    filename: wire.filename ?? 'Untitled flyer',
    byteSize: wire.byteSize ?? 0,
    pageCount: wire.pageCount ?? 0,
    codeCount: wire.codeCount ?? 0,
    uploadedAt: wire.uploadedAt ?? '',
  };
}

function toReading(wire: Partial<FlyerReading>): FlyerReading {
  return {
    ...toSummary(wire),
    report: toReport(wire.report),
    // Absent means the reader found no pages, not that headings are unknown -
    // so an empty list, and the section renders its own empty state rather than
    // every caller guarding the same field.
    headings: wire.headings ?? [],
  };
}

/** `?promotionId=` only when there is one: an empty value is not a filter. */
function withPromotion(path: string, promotionId?: string | null): string {
  if (!promotionId) return path;
  const search = new URLSearchParams({ promotionId });
  return `${path}?${search.toString()}`;
}

export async function listFlyerReadings(): Promise<FlyerReadingSummary[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load the flyers read so far'));
  }

  const rows = (await response.json()) as Partial<FlyerReadingSummary>[];
  return (Array.isArray(rows) ? rows : []).map(toSummary);
}

export async function getFlyerReading(
  readingId: string,
  promotionId?: string | null,
): Promise<FlyerReading> {
  const response = await apiFetch(
    withPromotion(`${BASE}/${encodeURIComponent(readingId)}`, promotionId),
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not open this flyer reading'));
  }
  return toReading(await response.json());
}

/**
 * Send the PDF and get the report back in the same call.
 *
 * No `Content-Type` header on purpose: the browser sets it with the multipart
 * boundary, and naming it by hand produces a body FastAPI cannot parse.
 */
export async function uploadFlyerReading(
  file: File,
  promotionId?: string | null,
): Promise<FlyerReading> {
  const body = new FormData();
  body.append('file', file);

  const response = await apiFetch(withPromotion(BASE, promotionId), { method: 'POST', body });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read that flyer'));
  }
  return toReading(await response.json());
}

/**
 * Read a flyer the system is already holding.
 *
 * The same reading, by the same code path, from a file nobody had to download
 * and upload back again: only the id travels, and the server takes the
 * filename, the size and the bytes off the attachment itself. Marketing files
 * the season's flyer in Resource Management long before anybody opens the Kit,
 * so this is the common case rather than the exotic one.
 *
 * Refusals read exactly as the upload's do - not a PDF, over 50 MB, password
 * protected - because they come from the same checks. `promotionId` is only
 * sent when there is one, for the same reason `withPromotion` exists.
 */
export async function createFlyerReadingFromAttachment(
  attachmentId: string,
  promotionId?: string | null,
): Promise<FlyerReading> {
  const body: Record<string, unknown> = { attachmentId };
  if (promotionId) body.promotionId = promotionId;

  const response = await apiFetch(`${BASE}/from-attachment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read that flyer'));
  }
  return toReading(await response.json());
}

export async function deleteFlyerReading(readingId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(readingId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this flyer reading'));
  }
}

/**
 * Write the flyer's printed sizes onto the products it names.
 *
 * The request carries CODES and never millimetres: the figures are read off the
 * stored flyer on the server, so nothing on this path can put a number of its
 * own into the product master.
 *
 * 200 with a body, not 207. A refusal is an answer rather than an error - the
 * master already agreeing, or a conflict nobody confirmed - so the caller must
 * read `refused`, and the counts are on the wire so a screen cannot report a
 * different total from the one the server wrote.
 */
export async function applyDimensions(
  readingId: string,
  input: DimensionApplyInput,
): Promise<DimensionApplyResult> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(readingId)}/dimensions/apply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        codes: input.codes,
        overwriteConflicts: Boolean(input.overwriteConflicts),
      }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not apply these sizes to the product master'),
    );
  }

  const wire = (await response.json()) as Partial<DimensionApplyResult>;
  const applied = wire.applied ?? [];
  // Never defaulted away: an absent `refused` read as "nothing was refused" is
  // exactly the silence this endpoint exists to break.
  const refused = wire.refused ?? [];
  return {
    applied,
    refused,
    appliedCount: wire.appliedCount ?? applied.length,
    refusedCount: wire.refusedCount ?? refused.length,
  };
}

export async function seedFromFlyerReading(
  readingId: string,
  input: FlyerSeedInput,
): Promise<FlyerSeedResult> {
  // Only what was answered is sent. A `name: null` alongside a `pageId` is two
  // targets as far as the validator is concerned, and the 422 that comes back
  // reads like a bug in the form rather than in the payload.
  const body: Record<string, unknown> = {};
  if (input.pageId) body.pageId = input.pageId;
  if (input.name) body.name = input.name;
  if (input.slug) body.slug = input.slug;
  if (input.promotionId) body.promotionId = input.promotionId;
  if (input.commitMessage) body.commitMessage = input.commitMessage;

  const response = await apiFetch(`${BASE}/${encodeURIComponent(readingId)}/seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not create the draft brochure'));
  }

  const wire = (await response.json()) as Partial<FlyerSeedResult>;
  return {
    pageId: String(wire.pageId ?? ''),
    name: wire.name ?? '',
    slug: wire.slug ?? '',
    publicPath: wire.publicPath ?? null,
    versionId: String(wire.versionId ?? ''),
    version: wire.version ?? 0,
    sectionCount: wire.sectionCount ?? 0,
    collectionCount: wire.collectionCount ?? 0,
    seededProductCount: wire.seededProductCount ?? 0,
    // Never defaulted away: an absent list here would read as "nothing was
    // dropped", which is the one thing the seed must not be able to imply.
    skipped: wire.skipped ?? [],
  };
}
