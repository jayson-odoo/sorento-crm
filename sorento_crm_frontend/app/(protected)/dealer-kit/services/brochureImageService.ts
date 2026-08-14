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
 *   shown: number,              // size of the pageable set (NOT this page)
 *   choosable: number           // of those, the ones with a photo to pick from
 * }
 *
 * PUT /api/v1/master-data/product-attachments/brochure-images/{productId}
 *   { attachment_id: string }
 * 200 { productId, chosenAttachmentId }
 * 404 when the product is not in the caller's company scope, or the attachment
 *     is not linked to it. Never 403: a non-owner must not learn the row exists.
 *
 * DELETE /api/v1/master-data/product-attachments/brochure-images/{productId}
 * 204. Puts the product back to having no chosen image.
 * ```
 *
 * The two writes live in
 * `master-data-management/products/services/productBrochureImageService`, the
 * single home for them, and this module only lists. Nothing on this screen
 * clears: clicking a candidate is idempotent rather than a toggle, so a product
 * can never be left with nothing chosen by accident.
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

import { getPromotions } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';

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
  /**
   * Products in this filter with a photo somebody could pick. Zero means the
   * screen has nothing to offer at all - a different answer from "you have
   * finished", and the reason the picker has two empty states.
   */
  choosable: number;
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

  // buildDataGridParams takes a 0-based pageIndex and emits 1-based `page`,
  // matching this route's contract. `searchQuery` is only written when
  // truthy, which is what leaves an empty `query=` off the request - an
  // empty value is a filter matching nothing on some backends; absent means
  // "no filter".
  const search = buildDataGridParams(
    { pageIndex: page - 1, pageSize: limit, searchQuery: query.trim() },
    {
      only_unset: String(onlyUnset),
      promotion_id: promotionId || undefined,
    },
  );

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
    // Falls back to what we can see. `shown` is the size of the whole
    // pageable set, so items.length is only right on a single page - which
    // is the correct guess when the server did not send one at all.
    shown: body.shown ?? items.length,
    // Falls back to what THIS page can prove rather than to 0. A backend that
    // does not send the field would otherwise put every screen into the "no
    // photos anywhere" state, including catalogues full of them.
    choosable: body.choosable ?? items.filter((row) => row.candidates.length > 0).length,
  };
}

/** Page size for the promotion filter. Matches SearchableSelect's default. */
/**
 * Take the only photo a product has, for every product named here.
 *
 * A POST rather than something the list does on its way past: a read must not
 * write. One request per page of the worklist, so 509 products with a single
 * candidate cost one call instead of 509 clicks.
 *
 * Returns the products it actually answered - ones with no candidate, or with a
 * choice to make, come back absent.
 */
export async function adoptSingleBrochureImages(productIds: string[]): Promise<string[]> {
  if (productIds.length === 0) return [];

  const response = await apiFetch(`${BASE}/adopt-single`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_ids: productIds }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not take the single photos'));
  }

  const wire = (await response.json()) as { productIds?: string[] };
  return wire.productIds ?? [];
}


export const PROMOTION_PAGE_SIZE = 50;

/**
 * Promotions for the filter above the list, searched on the SERVER.
 *
 * There are hundreds of them, so a static option list would cap the filter at
 * whatever one page happened to return and quietly hide the rest.
 *
 * Delegates to the promotions service instead of composing the same
 * page/limit/query string a second time: a duplicate is a place for the two to
 * disagree about what "search" means.
 */
export async function listBrochureImagePromotionOptions(
  query = '',
  pageIndex = 0,
): Promise<SearchableSelectOption[]> {
  const response = await getPromotions({
    pageIndex,
    pageSize: PROMOTION_PAGE_SIZE,
    sorting: [],
    searchQuery: query.trim(),
  });

  return (response.data ?? []).map((row) => ({
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
