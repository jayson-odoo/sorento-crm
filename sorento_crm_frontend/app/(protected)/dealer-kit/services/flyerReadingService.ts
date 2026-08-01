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
 *          Read INSIDE the request: the real 36 page flyer takes about a
 *          second, so there is no job, no queue and nothing to poll.
 *          400 when the file is not a PDF, 413 over 50 MB, and both say so in
 *          words - a designer who uploaded the wrong file must be told.
 * GET    /flyer-readings                     -> FlyerReadingSummary[], newest
 *          first, WITHOUT reports: one report per row is one match run per row.
 * GET    /flyer-readings/{id}?promotionId=   -> FlyerReading
 * POST   /flyer-readings/{id}/seed  {pageId | name+slug, promotionId?,
 *          commitMessage?}                   -> 201 FlyerSeedResult
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
 * **`dimensionCandidates` are reported and never written** (PLAN D9). Nothing
 * on this screen touches `products`; applying one is S7.6's job and needs the
 * master-data permission.
 *
 * ## What the API does NOT carry, and the screen therefore cannot show
 *
 * The section HEADINGS the extractor read are stored on the reading but are not
 * on `FlyerReadingOut`. Heading detection is a heuristic - it reads
 * "Transforming Your" where the paper says "BATHTUB COLLECTION" - so the review
 * screen can only say headings need checking, not show which ones are wrong.
 * Surfacing them would be an additive field on the detail response.
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

export interface FlyerReading extends FlyerReadingSummary {
  report: MatchReport;
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

function toReading(wire: Partial<FlyerReading>): FlyerReading {
  return {
    id: String(wire.id ?? ''),
    filename: wire.filename ?? 'Untitled flyer',
    byteSize: wire.byteSize ?? 0,
    pageCount: wire.pageCount ?? 0,
    codeCount: wire.codeCount ?? 0,
    uploadedAt: wire.uploadedAt ?? '',
    report: toReport(wire.report),
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
  return (Array.isArray(rows) ? rows : []).map((row) => {
    const { report, ...summary } = toReading(row);
    void report;
    return summary;
  });
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

export async function deleteFlyerReading(readingId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(readingId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this flyer reading'));
  }
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
