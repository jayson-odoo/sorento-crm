/**
 * The brochure image: which photo of a product a catalogue tile shows (S7.0).
 *
 * ## API contract
 *
 * The endpoints live under master-data rather than dealer-kit, because the flag
 * they set is `product_attachments.is_primary` - a master-data fact that the
 * catalogue only happens to read. Phase 1 documented them under
 * `/api/v1/dealer-kit/`; the move is recorded here so both sides agree.
 *
 * ```
 * GET /api/v1/master-data/product-attachments/brochure-images
 *   ?promotion_id=<uuid>      optional. Narrows to the products in one promotion,
 *                             so "everything in the A3 flyer" is one sitting.
 *   &only_unset=true|false    default true
 *   &query=<text>             optional, matches product code or name
 *   &page=<n>&limit=<n>       default 1 / 25
 *
 * 200 {
 *   items: [{
 *     productId: string,
 *     productCode: string,
 *     productName: string,
 *     chosenAttachmentId: string | null,
 *     candidates: [{
 *       attachmentId: string,
 *       filename: string,       // the ONLY thing distinguishing two thumbnails
 *                               // when one is a different product entirely
 *       url: string | null,     // signed thumbnail; null when none can be made
 *       accessLevels: string[] | null
 *     }]
 *   }],
 *   total: number,              // products matching the filter
 *   remaining: number,          // of those, the ones still without an image
 *   shown: number               // items on this page
 * }
 *
 * PUT /api/v1/master-data/product-attachments/brochure-images/{productId}
 *   { attachment_id: string }
 * 200 { productId, chosenAttachmentId }
 * 404 when the product is not in the caller's company scope, or the attachment
 *     is not linked to it. Never 403: a non-owner must not learn the row exists.
 *
 * DELETE /api/v1/master-data/product-attachments/brochure-images/{productId}
 * 204. Puts the product back to having no chosen image. Nothing in this screen
 *      calls it, deliberately: clicking a candidate is idempotent rather than a
 *      toggle, so a product can never be left with nothing chosen by accident.
 * ```
 *
 * ## Invariants the backend owns
 *
 * - **Exactly one chosen image per product, per company.** Setting a new one
 *   clears the previous in the same transaction. Two rows flagged at once would
 *   make the tile's photo depend on row order again, which is the defect this
 *   whole slice exists to remove.
 * - **The flag is `product_attachments.is_primary`**, not a new column.
 *   `product_images.py` already orders by it, so tiles start showing the right
 *   photo the moment it is set, with no renderer change.
 * - **Nothing is ever chosen automatically.** A filename matching the product
 *   code would identify the right image for 509 of 535 products; inferring from
 *   it is rejected, because a wrong photo is a wrong product in front of a
 *   customer and the same wrong photo fed to a mesh generator is that plus a
 *   bill. A product with one candidate still takes a click.
 * - **Candidates are images only.** `product_attachments` links whatever is
 *   attached to a product, including 532 PDFs in the live data, and a spec sheet
 *   offered as a brochure photo is noise in a list whose whole job is to be
 *   scanned quickly.
 */

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/master-data/product-attachments/brochure-images';

export interface BrochureImageCandidate {
  attachmentId: string;
  filename: string;
  /** Signed thumbnail URL. Null while a preview cannot be produced. */
  url: string | null;
  /** Who this image is for. Trade imagery is tagged `dealer` and must not reach a consumer. */
  accessLevels: string[] | null;
}

export interface BrochureImageRow {
  productId: string;
  productCode: string;
  productName: string;
  /** Null until a human has chosen. Every row starts null in the real data. */
  chosenAttachmentId: string | null;
  candidates: BrochureImageCandidate[];
}

export interface BrochureImagePage {
  items: BrochureImageRow[];
  total: number;
  remaining: number;
  shown: number;
}

export interface BrochureImageListParams {
  promotionId?: string;
  onlyUnset?: boolean;
  query?: string;
  /** One-based, matching the endpoint. */
  page?: number;
  limit?: number;
}

export const BROCHURE_IMAGE_PAGE_SIZE = 25;

export async function listBrochureImages(
  params: BrochureImageListParams = {},
): Promise<BrochureImagePage> {
  const { promotionId = '', onlyUnset = true, query = '', page = 1, limit = BROCHURE_IMAGE_PAGE_SIZE } =
    params;

  const search = new URLSearchParams({
    only_unset: String(onlyUnset),
    page: String(page),
    limit: String(limit),
  });
  if (promotionId) search.set('promotion_id', promotionId);
  // An empty `query=` is a filter matching nothing on some backends; absent
  // means "no filter".
  if (query.trim()) search.set('query', query.trim());

  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load brochure images'));
  }

  const body = (await response.json()) as Partial<BrochureImagePage>;
  const items = (body.items ?? []).map((row) => ({
    ...row,
    // A product with no linked photo is a row that must still appear, so an
    // absent candidate list is an empty one, never a reason to drop the row.
    candidates: row.candidates ?? [],
  }));

  return {
    items,
    total: body.total ?? items.length,
    remaining: body.remaining ?? items.filter((row) => !row.chosenAttachmentId).length,
    shown: body.shown ?? items.length,
  };
}

export interface BrochureImageChoice {
  productId: string;
  chosenAttachmentId: string | null;
}

export async function setBrochureImage(
  productId: string,
  attachmentId: string,
): Promise<BrochureImageChoice> {
  const response = await apiFetch(`${BASE}/${productId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_id: attachmentId }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save the brochure image'));
  }
  return (await response.json()) as BrochureImageChoice;
}

export async function clearBrochureImage(productId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${productId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not clear the brochure image'));
  }
}

interface PromotionSelectRow {
  id: string;
  description?: string | null;
  products_count?: number | null;
}

/** Page size for the promotion filter. Matches SearchableSelect's default. */
export const PROMOTION_PAGE_SIZE = 50;

/**
 * Promotions for the filter above the list, searched on the SERVER.
 *
 * There are hundreds of them, so a static option list would cap the filter at
 * whatever one page happened to return and quietly hide the rest.
 */
export async function listBrochureImagePromotionOptions(
  query = '',
  pageIndex = 0,
): Promise<SearchableSelectOption[]> {
  const search = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(PROMOTION_PAGE_SIZE),
  });
  if (query.trim()) search.set('query', query.trim());

  const response = await apiFetch(`/api/v1/marketing/promotions?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load promotions'));
  }

  const body = (await response.json()) as { data?: PromotionSelectRow[] } | PromotionSelectRow[];
  const rows = Array.isArray(body) ? body : (body.data ?? []);

  return rows.map((row) => ({
    value: row.id,
    // Never the id: a promotion without a description reads as "Untitled
    // promotion" rather than exposing a uuid in the trigger.
    label: row.description?.trim() || 'Untitled promotion',
    description:
      row.products_count == null
        ? undefined
        : `${row.products_count} product${row.products_count === 1 ? '' : 's'}`,
  }));
}
