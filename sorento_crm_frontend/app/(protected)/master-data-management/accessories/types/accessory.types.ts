/** Accessories library (PRICETAG-ACCESSORIES). Mirrors `app/schemas/accessory.py`. */

export interface AccessoryImage {
  attachment_id: string;
  url: string;
}

export interface Accessory {
  id: string;
  name: string;
  /** One short line, printed as typed. Null = none. */
  spec: string | null;
  image: AccessoryImage | null;
  product_count: number;
  combo_count: number;
}

export interface AccessoryWrite {
  name: string;
  spec?: string | null;
}

/**
 * One entry on a product's or combo's ordered list: a library accessory OR a real
 * catalogue product. For kind 'product': id = the product id, name = its description,
 * spec null, counts 0, image = its primary photo.
 */
export interface AccessoryEntry extends Accessory {
  kind: 'accessory' | 'product';
  code: string | null;
  list_price: number | null;
}

/** What the PUT takes per entry. */
export type AccessoryItemRef = { accessory_id: string } | { product_id: string };

export const entryKey = (e: Pick<AccessoryEntry, 'kind' | 'id'>) => `${e.kind}:${e.id}`;

export const entryRef = (e: Pick<AccessoryEntry, 'kind' | 'id'>): AccessoryItemRef =>
  e.kind === 'product' ? { product_id: e.id } : { accessory_id: e.id };

/** Which record owns an ordered accessory list. */
export type AccessoryOwnerKind = 'product' | 'combo';
