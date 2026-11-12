/**
 * PRICETAG-UPGRADE-VARIANTS S1: the combo's upgrades on offer, as the items an Upgrades box lists.
 *
 * One source of truth: the combo's own upgrade parts (product page > Combos). An upgrade is a
 * catalogue product, so its picture, list price and specs come from its slot row; the top-up from
 * the combo. A picked upgrade is part of the package (priced into SP), so it leaves the list.
 *
 * Kept apart from `product-block.ts` (which imports `accessory-box.ts`) so `accessoriesOf` can
 * branch here without an import cycle; it reads the binding directly for the same reason.
 */
import type { TagAccessory, TagBindingData, TagCombo, TagImage, TagSlots } from './tag-template-types';

function comboAndSlots(data: TagBindingData | null | undefined): { combo: TagCombo | null; slots: TagSlots | null } {
  if (data?.kind === 'line') return { combo: data.line.combo ?? null, slots: data.line.slots ?? null };
  if (data?.kind === 'product') return { combo: data.product.combo ?? null, slots: data.product.slots ?? null };
  return { combo: null, slots: null };
}

/** The tag's own SP: the figure `priceBadgeInput` reads as `offerPrice` for the whole binding. */
function tagOfferPrice(data: TagBindingData | null | undefined): number | null {
  if (data?.kind === 'line') return data.line.show_promo_price ? data.line.sell_price : null;
  if (data?.kind === 'product') return data.product.offer_price;
  return null;
}

/** The tag SP plus a top-up; null when either is missing (nothing to add, or nothing to add to). */
export function priceWithUpgrade(data: TagBindingData | null | undefined, topup: number | null | undefined): number | null {
  const offer = tagOfferPrice(data);
  return offer == null || topup == null ? null : offer + topup;
}

function primaryFirst(images: readonly TagImage[] | undefined): TagImage[] {
  const list = images ?? [];
  return [...list.filter((image) => image.is_primary), ...list.filter((image) => !image.is_primary)];
}

/** The combo's upgrades on offer, in combo order; [] with no combo or once one is picked. */
export function upgradesOf(data: TagBindingData | null | undefined): TagAccessory[] {
  const { combo, slots } = comboAndSlots(data);
  if (!combo) return [];
  const rows = slots?.upgrades ?? [];
  return combo.upgrades
    .filter((upgrade) => !upgrade.picked)
    .map((upgrade) => {
      const row = rows.find((candidate) => candidate.product_id === upgrade.product_id);
      const images = primaryFirst(row?.images);
      const topup = upgrade.topup_amount ?? null;
      return {
        kind: 'upgrade',
        id: upgrade.product_id,
        code: upgrade.code,
        name: upgrade.description,
        spec: null,
        list_price: row?.list_price ?? null,
        // TAG-ACC-CARD-RESIZE (owner 22:35): what a card's `{{product.*}}` fields read for this upgrade.
        sell_price: row?.sell_price ?? null,
        spec_lines: row?.spec_lines,
        price_tag_description: row?.price_tag_description ?? null,
        image: images[0] ? { attachment_id: images[0].attachment_id, url: images[0].url } : null,
        images: images.map((image) => ({
          attachment_id: image.attachment_id,
          url: image.url,
          colour_name: null,
          colour_hex: null,
        })),
        specs: row?.specs ?? [],
        topup_amount: topup,
        price_with_upgrade: priceWithUpgrade(data, topup),
      };
    });
}
