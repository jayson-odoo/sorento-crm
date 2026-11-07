/** Accessories library (PRICETAG-ACCESSORIES). Mirrors `app/schemas/accessory.py`. */

export interface AccessoryImage {
  attachment_id: string;
  url: string;
}

/** One of an accessory's ordered pictures, with its optional colour. */
export interface AccessoryPicture extends AccessoryImage {
  id: string;
  colour_name: string | null;
  colour_hex: string | null;
}

/** The overrides stored on one list row (nulls = the accessory's own). */
export interface AccessoryEntryOverrides {
  image_id: string | null;
  name: string | null;
  spec: string | null;
  remark: string | null;
}

export interface Accessory {
  id: string;
  name: string;
  /** Plain text or sanitised rich HTML. Null = none. */
  spec: string | null;
  remark?: string | null;
  /** The first picture (old callers); `images` is the whole ordered set. */
  image: AccessoryImage | null;
  images?: AccessoryPicture[];
  product_count: number;
  combo_count: number;
}

export interface AccessoryWrite {
  name: string;
  spec?: string | null;
  remark?: string | null;
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
  /** Only in a list: the overrides stored on this row. */
  entry?: AccessoryEntryOverrides;
}

/** What the PUT takes per entry; the overrides are sent only when set. */
export type AccessoryItemRef = (
  | { accessory_id: string; image_id?: string }
  | { product_id: string }
) & { name?: string; spec?: string; remark?: string };

export const hasOverrides = (e: Pick<AccessoryEntry, 'entry'>): boolean =>
  Boolean(e.entry && (e.entry.image_id || e.entry.name || e.entry.spec || e.entry.remark));

export const entryKey = (e: Pick<AccessoryEntry, 'kind' | 'id'>) => `${e.kind}:${e.id}`;

export const entryRef = (e: Pick<AccessoryEntry, 'kind' | 'id' | 'entry'>): AccessoryItemRef => {
  const own = e.entry;
  const text = {
    ...(own?.name ? { name: own.name } : {}),
    ...(own?.spec ? { spec: own.spec } : {}),
    ...(own?.remark ? { remark: own.remark } : {}),
  };
  return e.kind === 'product'
    ? { product_id: e.id, ...text }
    : { accessory_id: e.id, ...(own?.image_id ? { image_id: own.image_id } : {}), ...text };
};

/** Which record owns an ordered accessory list. */
export type AccessoryOwnerKind = 'product' | 'combo';

/** An owner's list: the entries, with the box style the owner names (a saved accessories template id). */
export type OwnerAccessories = AccessoryEntry[] & { box_style_id?: string | null };

export const withBoxStyle = (items: AccessoryEntry[], boxStyleId: string | null | undefined): OwnerAccessories =>
  Object.assign([...items], { box_style_id: boxStyleId ?? null });
