/**
 * Line-level pricing - MOCK (Phase 1 only).
 *
 * ===========================================================================
 * PLAN-price-tag-line-promo-combo-subject.md D1-D4 - Phase 1 slices S1/S2/S5
 * ===========================================================================
 * A promotion (or a hand-typed price) now lives on the LINE, not the header
 * (D1); one pricing call answers every line on a request at once (D4). No
 * backend route exists yet (that is S7, Phase 2) - the portal's and the
 * CRM's own service files both call the pure functions here, which produce
 * the SAME shape the real route will, so swapping the mock for a real
 * `POST .../lookups/line-pricing` call at S12 touches only the one `fetch`
 * line in each service file, not this computation or any caller of it.
 *
 * Deterministic and product-id-keyed (no network, no state) so the same
 * product always prices the same across the portal form, the CRM detail
 * page and a re-render, without a real catalogue behind either yet.
 * ===========================================================================
 */

export type MockPriceMode = 'list' | 'selling';
export type SellPriceBasis = 'manual' | 'promotion' | 'list';

export interface LinePricingPromotionOption {
  id: string;
  description: string;
  sell_price: number;
}

export interface LinePricingCandidate {
  product_id: string;
  list_price: number;
  sell_price: number;
}

export interface LinePricingResult {
  key: string;
  list_price: number;
  promotion_options: LinePricingPromotionOption[];
  auto_promotion_id: string | null;
  sell_price: number | null;
  sell_price_basis: SellPriceBasis;
  parts_at_list: string[];
  candidates: LinePricingCandidate[];
}

export interface LinePricingLineInput {
  key: string;
  product_id: string | null;
  part_product_ids: string[];
  candidate_product_ids: string[];
  promotion_id?: string | null;
}

/** The two mock promotions every mock line-pricing call covers products
 *  with. */
const MOCK_PROMOTIONS: { id: string; description: string; discount: number }[] = [
  { id: 'mock-promo-august', description: 'August Promo', discount: 0.15 },
  { id: 'mock-promo-clearance', description: 'September Clearance', discount: 0.1 },
];

/** Deterministic RM 50-949 from a product id, so the same product always
 *  prices the same across every call without a real catalogue behind it. */
function mockListPrice(productId: string): number {
  let hash = 0;
  for (let i = 0; i < productId.length; i += 1) {
    hash = (hash * 31 + productId.charCodeAt(i)) >>> 0;
  }
  return 50 + (hash % 90) * 10;
}

/** Deterministic coverage: each mock promotion "covers" roughly a third of
 *  products, so a line demonstrably lands in all three journey states (auto
 *  pick, choose-among-several, no covering promotion). */
function mockPromotionCovers(promotionId: string, productId: string): boolean {
  const bucket = Math.floor(mockListPrice(productId) / 10) % 3;
  if (promotionId === 'mock-promo-august') return bucket !== 2;
  if (promotionId === 'mock-promo-clearance') return bucket === 0;
  return false;
}

function mockOfferPrice(promotionId: string, productId: string): number {
  const promo = MOCK_PROMOTIONS.find((p) => p.id === promotionId);
  if (!promo || !mockPromotionCovers(promotionId, productId)) {
    return mockListPrice(productId);
  }
  return Math.round(mockListPrice(productId) * (1 - promo.discount));
}

/**
 * One pricing call for every line (D4). MOCK ONLY (Phase 1) - resolves
 * synchronously, no network call, no persistence. `priceMode: 'list'`
 * still answers `list_price`/`candidates` (the List price column and part
 * row prices need them), just leaves `sell_price` null.
 */
export function computeLinePricing(
  priceMode: MockPriceMode,
  lines: LinePricingLineInput[],
): LinePricingResult[] {
  return lines.map((line) => {
    const resolvedIds = [line.product_id, ...line.part_product_ids].filter(
      (id): id is string => !!id,
    );
    const listPrice = resolvedIds.reduce((sum, id) => sum + mockListPrice(id), 0);

    const promotionOptions: LinePricingPromotionOption[] = MOCK_PROMOTIONS.filter(
      (promo) => resolvedIds.some((id) => mockPromotionCovers(promo.id, id)),
    )
      .map((promo) => ({
        id: promo.id,
        description: promo.description,
        sell_price: resolvedIds.reduce(
          (sum, id) => sum + mockOfferPrice(promo.id, id),
          0,
        ),
      }))
      .sort((a, b) => a.sell_price - b.sell_price);

    const autoPromotionId = promotionOptions[0]?.id ?? null;
    const chosenPromotionId = line.promotion_id ?? null;
    const chosen = chosenPromotionId
      ? promotionOptions.find((p) => p.id === chosenPromotionId)
      : promotionOptions.find((p) => p.id === autoPromotionId);

    const sellPrice = priceMode === 'selling' && chosen ? chosen.sell_price : null;
    const sellPriceBasis: SellPriceBasis =
      priceMode === 'selling' && chosen ? 'promotion' : 'list';
    const partsAtList = chosenPromotionId
      ? resolvedIds.filter((id) => !mockPromotionCovers(chosenPromotionId, id))
      : [];

    const candidates: LinePricingCandidate[] = line.candidate_product_ids.map(
      (id) => ({
        product_id: id,
        list_price: mockListPrice(id),
        sell_price:
          priceMode === 'selling' && chosenPromotionId
            ? mockOfferPrice(chosenPromotionId, id)
            : mockListPrice(id),
      }),
    );

    return {
      key: line.key,
      list_price: listPrice,
      promotion_options: promotionOptions,
      auto_promotion_id: autoPromotionId,
      sell_price: sellPrice,
      sell_price_basis: sellPriceBasis,
      parts_at_list: partsAtList,
      candidates,
    };
  });
}
