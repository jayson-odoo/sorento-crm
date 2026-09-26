/**
 * Product combos - the catalogue package a product is sold as
 * (`documentation/plans/dealer-kit/PLAN-price-tag-combos.md`, D1).
 *
 * A combo lives on the REAL host product (a cabinet), is named the way the
 * catalogue names it ("3 in 1", "4 in 1"), and lists the parts that come with
 * it. A part with no choice group is fixed - it is always in the package. Parts
 * sharing a choice group are the options the customer picks ONE of (the four
 * basin colours). A combo carries no code and no price: the price is summed per
 * tag from the products on it.
 *
 * This is deliberately NOT a product set. A set is a synthetic code the system
 * never sold, and the chatbot searches sets; combos are invisible to it.
 */

/** One part on a combo, as the reader sees it - never a bare id. */
export interface ProductComboPartRow {
  id: string;
  combo_id: string;
  product_id: string;
  /** The part's own product code, e.g. `SRTMR502-BL`. */
  code: string;
  product_name: string;
  /** `800 x 500 x 220 mm`, or null when the product records no measurement. */
  dimensions: string | null;
  /** Null = fixed part. A label = one of the options for that label. */
  choice_group: string | null;
  sort_order: number;
}

/** The combo's own cover picture (S5), null with none uploaded yet. */
export interface ProductComboImage {
  attachment_id: string;
  url: string;
}

export interface ProductComboRow {
  id: string;
  host_product_id: string;
  /** The catalogue's own wording, e.g. "3 in 1". Unique per host product. */
  name: string;
  sort_order: number;
  parts: ProductComboPartRow[];
  /** Optional so an older fixture/mock omitting it still type-checks;
   *  the backend always sends the key (null with no picture). */
  image?: ProductComboImage | null;
  created_at: string;
  updated_at: string;
}

/** One line of a part's read-only "Sold with" list, on the PART's own page. */
export interface ProductSoldWithRow {
  host_product_id: string;
  host_code: string;
  host_name: string;
  combo_id: string;
  combo_name: string;
}

export interface ProductComboCreate {
  name: string;
}

export interface ProductComboPartCreate {
  part_product_id: string;
  choice_group?: string | null;
}

export interface ProductComboPartUpdate {
  choice_group?: string | null;
  sort_order?: number;
}
