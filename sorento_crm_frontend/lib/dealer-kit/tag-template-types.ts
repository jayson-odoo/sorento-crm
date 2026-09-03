/**
 * Tag template document model types.
 *
 * Matches the JSONB schema stored in `dealer_kit.tag_templates.doc` and used
 * by both the tag template editor (S3) and the tag sheet designer (S4).
 * Positions and sizes are always in millimetres; the canvas converts to
 * pixels via a zoom-dependent scale factor.
 */

// ---------------------------------------------------------------------------
// Layer types
// ---------------------------------------------------------------------------

export type TagLayerType =
  | 'image'
  | 'text'
  | 'shape'
  | 'product_slot'
  | 'price_badge'
  | 'badge'
  | 'barcode'
  | 'group';

/** Named slots that bind a layer to a product data field at render time. */
export type SlotBinding =
  | 'product_image'
  | 'code'
  | 'name'
  | 'dimensions'
  | 'spec_lines'
  | 'included_accessories'
  | 'list_price'
  | 'sell_price'
  | 'badges'
  | 'alternatives'
  | 'accessories'
  | 'set_members'
  | 'barcode'
  | null;

export type ShapeType = 'rect' | 'rounded_rect' | 'ellipse' | 'line';

export type ImageFit = 'cover' | 'contain';

/** How an image layer is masked. `circle` is the round product cut-out on the flyer. */
export type ImageMaskShape = 'none' | 'circle';

/**
 * Where an image layer's picture comes from.
 *
 * Two sources, kept apart on purpose: a library asset is artwork somebody
 * uploaded to the Kit, a product attachment is one of the product's own photos
 * and carries the access gate that decides who may see it. Collapsing them into
 * one id column would lose that distinction the first time a tag was printed
 * for a consumer.
 */
export type ImageSource =
  | { type: 'asset'; assetId: string }
  | { type: 'product_attachment'; attachmentId: string };

/** How a product block binds to the data behind it. */
export interface GroupBinding {
  product_id?: string;
  product_set_id?: string;
}

/** The two shapes a price badge takes. See `lib/dealer-kit/price-badge.ts`. */
export type PriceBadgeVariant = 'list_only' | 'promo';

// ---------------------------------------------------------------------------
// Layer props (discriminated union on `kind`)
// ---------------------------------------------------------------------------

export interface ImageLayerProps {
  kind: 'image';
  source: ImageSource | null;
  fit: ImageFit;
  cropRect?: { x: number; y: number; width: number; height: number };
  maskShape?: ImageMaskShape;
  /**
   * Where the picture came from before S3b gave image layers a source
   * discriminator. Read by `imageSourceOf`, never written: a template saved by
   * the first version of the editor still opens.
   */
  assetId?: string | null;
}

/**
 * The source of an image layer, tolerating a document saved before S3b.
 *
 * A missing `source` is null rather than an error - `assetId` was the whole
 * story until price badges arrived, and a template nobody has reopened since
 * must not throw when they do.
 */
export function imageSourceOf(props: ImageLayerProps): ImageSource | null {
  if (props.source) return props.source;
  if (props.assetId) return { type: 'asset', assetId: props.assetId };
  return null;
}

export interface TextLayerProps {
  kind: 'text';
  text: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  align: 'left' | 'center' | 'right';
  lineHeight: number;
  letterSpacing: number;
  /**
   * Whole-layer B/I/U/S flags (S2, D4). Absent on a document saved before
   * S2 - `text-format.ts` and the renderers treat a missing flag as false,
   * so an old tag still opens and prints unchanged.
   */
  italic?: boolean;
  underline?: boolean;
  strikethrough?: boolean;
}

export interface ShapeLayerProps {
  kind: 'shape';
  shape: ShapeType;
  fill: string;
  stroke: string;
  strokeWidth: number;
  cornerRadius: number;
}

export interface ProductSlotLayerProps {
  kind: 'product_slot';
  fieldKey: string;
}

export interface BadgeLayerProps {
  kind: 'badge';
  assetId: string;
}

/**
 * A price, drawn the way a price tag draws one.
 *
 * A dedicated layer type rather than free text (D26), because the composition -
 * struck list price above a filled box holding `SP`, the figure and `NETT` - is
 * the same on every tag and a designer retyping it per tag would eventually
 * type it differently. Colours, radius and size stay editable; what the badge
 * is MADE of does not.
 */
export interface PriceBadgeLayerProps {
  kind: 'price_badge';
  variant: PriceBadgeVariant;
  fill: string;
  textColor: string;
  cornerRadius: number;
  showNett: boolean;
}

/**
 * A barcode, drawn as a label plate matching the printed sample (D18): white
 * backing with rounded corners, an optional black product-code strip on top
 * (per-layer `show_code`), the bars, and the guard-split human-readable
 * digits beneath. Always bound to slot `barcode` - a tag has one product, so
 * there is nothing else for it to draw.
 */
export interface BarcodeLayerProps {
  kind: 'barcode';
  show_code: boolean;
}

export interface GroupLayerProps {
  kind: 'group';
  children: string[];
  /**
   * Which product or set the whole block is about. Carried on the GROUP so a
   * block can be re-bound or relinked in one action instead of layer by layer.
   * Optional: a group made by selecting two shapes and pressing Ctrl+G binds to
   * nothing, and a document saved before S3b has no bindings at all.
   */
  binding?: GroupBinding;
}

export type TagLayerProps =
  | ImageLayerProps
  | TextLayerProps
  | ShapeLayerProps
  | ProductSlotLayerProps
  | PriceBadgeLayerProps
  | BadgeLayerProps
  | BarcodeLayerProps
  | GroupLayerProps;

// ---------------------------------------------------------------------------
// Layer
// ---------------------------------------------------------------------------

export interface TagLayer {
  id: string;
  type: TagLayerType;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  rotation_deg: number;
  z_index: number;
  locked: boolean;
  visible: boolean;
  slot_binding: SlotBinding;
  text_override: string | null;
  props: TagLayerProps;
}

// ---------------------------------------------------------------------------
// Template families
// ---------------------------------------------------------------------------

export type TagTemplateFamily =
  | 'sink_combo'
  | 'ala_carte'
  | 'art_basin'
  | 'wc'
  | 'urinal'
  | 'shower'
  | 'mirror'
  | 'mirror_cabinet'
  | 'furniture_set';

/**
 * The families a tag can belong to, in catalogue order.
 *
 * `art_basin` and `urinal` joined the list when the eight starter templates
 * were seeded from `Sorento Pricetag Template.pdf` (D32): the PDF prints a tag
 * for each and neither fits any of the others - an art basin carries no
 * warranty badges at all, and a urinal's spec line is an inlet position rather
 * than a trap. Without them both seeded templates would show their raw family
 * key in the listing and neither could be picked in the dialog.
 */
export const TAG_TEMPLATE_FAMILIES: { value: TagTemplateFamily; label: string }[] = [
  { value: 'sink_combo', label: 'Sink Combo' },
  { value: 'ala_carte', label: 'Ala Carte' },
  { value: 'art_basin', label: 'Art Basin' },
  { value: 'wc', label: 'WC' },
  { value: 'urinal', label: 'Urinal' },
  { value: 'shower', label: 'Shower' },
  { value: 'mirror', label: 'Mirror' },
  { value: 'mirror_cabinet', label: 'Mirror Cabinet' },
  { value: 'furniture_set', label: 'Furniture Set' },
];

export function familyLabel(family: string): string {
  return TAG_TEMPLATE_FAMILIES.find((f) => f.value === family)?.label ?? family;
}

// ---------------------------------------------------------------------------
// Template document (stored in tag_templates.doc JSONB)
// ---------------------------------------------------------------------------

export interface TagTemplateDoc {
  layers: TagLayer[];
  width_mm: number;
  height_mm: number;
}

// ---------------------------------------------------------------------------
// Template entity
// ---------------------------------------------------------------------------

export interface TagTemplate {
  id: string;
  name: string;
  family: TagTemplateFamily;
  doc: TagTemplateDoc;
  print_size: { width_mm: number; height_mm: number };
  created_at: string;
  updated_at: string;
  /** The live pointer (PLAN D7). Absent = never published. */
  published_version_id?: string | null;
  published_version_no?: number | null;
}

// ---------------------------------------------------------------------------
// Template versions (S5)
// ---------------------------------------------------------------------------

/** One row of the Versions sheet. No `doc` - fetched only on View. */
export interface TagTemplateVersion {
  id: string;
  template_id: string;
  version_no: number;
  note: string | null;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
}

/** A past version's full document, for View (D16). */
export interface TagTemplateVersionDetail extends TagTemplateVersion {
  doc: TagTemplateDoc;
  print_size: { width_mm: number; height_mm: number };
}

// ---------------------------------------------------------------------------
// Imposition (used in S4; auto-fit replaces the fixed presets in S6)
// ---------------------------------------------------------------------------

/**
 * `'a4_3up'` / `'a4_2x2'` are read-only history: a doc saved before S6 may
 * still carry one, and `impositionSlots` treats every value the same (the
 * auto-fit grid) so an old doc loads unchanged (AC-S6-4). `'auto'` is what
 * every new save writes; `'custom'` marks "the designer edited a page field
 * by hand" - it no longer selects a different layout algorithm.
 */
export type ImpositionPreset = 'auto' | 'custom' | 'a4_3up' | 'a4_2x2';

export interface ImpositionConfig {
  preset: ImpositionPreset;
  page_width_mm: number;
  page_height_mm: number;
  bleed_mm: number;
  gap_mm: number;
}

export const IMPOSITION_PRESETS: Record<'auto' | 'custom', Omit<ImpositionConfig, 'preset'>> = {
  auto: { page_width_mm: 210, page_height_mm: 297, bleed_mm: 3, gap_mm: 2 },
  custom: { page_width_mm: 210, page_height_mm: 297, bleed_mm: 3, gap_mm: 2 },
};

// ---------------------------------------------------------------------------
// Tag sheet document (stored in page_version.doc when page.kind = 'tag_sheet')
// ---------------------------------------------------------------------------

export interface TagSheetDoc {
  kind: 'tag_sheet';
  imposition: ImpositionConfig;
  sheets: TagSheet[];
  /**
   * The size "Apply to all lines" (D24, S9) set, applied to every line's tag
   * AND remembered for a line that has not been opened yet - without this a
   * line opened after the fact would clone at its template's own print size
   * instead of the size the designer just chose for the whole request.
   * Absent/null means no request-level default has been set (a document
   * saved before this field, or one where nobody has used Apply to all yet).
   */
  default_tag_size?: { width_mm: number; height_mm: number } | null;
}

export interface TagSheet {
  id: string;
  tags: PlacedTag[];
}

export interface PlacedTag {
  id: string;
  template_id: string;
  request_line_id: string;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  layers: TagLayer[];
  /**
   * This copy was DRAGGED to where it sits, so re-arranging must leave it there.
   *
   * Every placed tag carries a position - arrangement is what the document is -
   * so the position alone cannot say which of them somebody chose. Without this
   * flag, one save and reopen pinned the entire sheet: switching the imposition
   * preset re-imposed nothing and a quantity bump dropped the new copy on top of
   * copy 0. Absent means auto-placed, which is what a document written before
   * the flag reads as.
   */
  pinned?: boolean;
}

// ---------------------------------------------------------------------------
// Live product data behind a binding (never stored in doc - ADR 0008)
// ---------------------------------------------------------------------------

/** One photo a bound product may show, already signed for this viewer. */
export interface TagImage {
  attachment_id: string;
  url: string;
  is_primary: boolean;
}

/**
 * One reviewed spec of the bound product, as `{{spec.<key>}}` draws it (D58).
 *
 * `value` arrives already displayable and `unit` comes from the registry rather
 * than from the stored value, so a tag prints `407 mm` without the canvas
 * deciding what a millimetre is called.
 */
export interface TagSpecValue {
  key: string;
  label: string;
  value: string;
  unit: string | null;
}

/**
 * Everything a product block draws, resolved by the backend at the moment the
 * block is dropped or re-bound.
 *
 * Held in editor state only. A saved document carries the binding and any text
 * overrides, never these values: prices resolve at render time (ADR 0008), and
 * a name or a photo that was baked into the doc would go stale the first time
 * somebody fixed the product master.
 */
export interface ProductTagData {
  id: string;
  code: string;
  name: string;
  dimensions: string;
  spec_lines: string[];
  /** The same specs key by key, for merge fields (D58). */
  specs: TagSpecValue[];
  images: TagImage[];
  list_price: number | null;
  offer_price: number | null;
  promotion_id: string | null;
  /** `products.barcode` (D14/S7). Null renders a placeholder in the editor
   * and nothing on print. */
  barcode: string | null;
}

export interface ProductSetMemberTagData {
  product_id: string;
  code: string;
  name: string;
  dimensions: string;
  quantity: number;
}

export interface ProductSetTagData {
  id: string;
  set_code: string;
  name: string;
  members: ProductSetMemberTagData[];
  list_price: number | null;
  offer_price: number | null;
  promotion_id: string | null;
}

/**
 * Display data for one price tag request LINE.
 *
 * The tag sheet designer resolves per line rather than per product, because a
 * line can carry a marketing price override with a logged reason (D9) and that
 * override has to win on the tag the designer is looking at. Same shape the
 * print payload sends, so the proof and the PDF agree.
 */
export interface LineTagData {
  line_id: string;
  code: string;
  name: string;
  dimensions: string;
  /** Already joined with newlines, as the backend resolved it. */
  spec_lines: string;
  /** The same specs key by key, for merge fields (D58). Empty for a set line. */
  specs: TagSpecValue[];
  /** One line per set member, already formatted. Empty for a product line. */
  set_members: string;
  images: TagImage[];
  list_price: number | null;
  sell_price: number | null;
  show_promo_price: boolean;
  included_accessories: string;
  quantity: number;
  /** Null for a set line - a set has no barcode of its own (S7). */
  barcode: string | null;
}

/** A binding's resolved data, whichever kind of thing it points at. */
export type TagBindingData =
  | { kind: 'product'; product: ProductTagData }
  | { kind: 'set'; set: ProductSetTagData }
  | { kind: 'line'; line: LineTagData };

/**
 * The key a resolved-data map is held under.
 *
 * A string rather than the binding object, because a Map keyed on an object
 * compares by identity and every re-render would miss.
 */
export function bindingKey(binding: GroupBinding | undefined): string | null {
  if (!binding) return null;
  if (binding.product_id) return `product:${binding.product_id}`;
  if (binding.product_set_id) return `set:${binding.product_set_id}`;
  return null;
}

// ---------------------------------------------------------------------------
// Resolved product data for rendering (never stored in doc - ADR 0008)
// ---------------------------------------------------------------------------

export interface ResolvedTagData {
  product_image_url: string | null;
  code: string;
  name: string;
  dimensions: string;
  spec_lines: string;
  list_price: string | null;
  sell_price: string | null;
  show_promo_price: boolean;
  included_accessories: string;
  alternatives: Array<{ code: string; name: string; list_price: string | null }>;
  set_members: Array<{ code: string; name: string; quantity: number }>;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

export const DEFAULT_TAG_SIZE = { width_mm: 95, height_mm: 130 };

export function defaultTextProps(): TextLayerProps {
  return {
    kind: 'text',
    text: 'Text',
    fontFamily: 'DM Sans',
    fontSize: 12,
    fontWeight: 400,
    color: '#000000',
    align: 'left',
    lineHeight: 1.2,
    letterSpacing: 0,
  };
}

export function defaultShapeProps(): ShapeLayerProps {
  return {
    kind: 'shape',
    shape: 'rect',
    fill: '#e0e0e0',
    stroke: '#999999',
    strokeWidth: 0.5,
    cornerRadius: 0,
  };
}

export function defaultImageProps(): ImageLayerProps {
  return {
    kind: 'image',
    source: null,
    fit: 'contain',
    maskShape: 'none',
  };
}

export function defaultProductSlotProps(): ProductSlotLayerProps {
  return {
    kind: 'product_slot',
    fieldKey: 'product_image',
  };
}

export function defaultPriceBadgeProps(
  variant: PriceBadgeVariant = 'list_only',
): PriceBadgeLayerProps {
  return {
    kind: 'price_badge',
    variant,
    // The flyer's promotional block is white on red. A list-only badge paints
    // no box, so the fill only shows once somebody switches it to promo.
    fill: '#d32f2f',
    textColor: '#ffffff',
    cornerRadius: 2,
    showNett: true,
  };
}

export function defaultBadgeProps(): BadgeLayerProps {
  return {
    kind: 'badge',
    assetId: '',
  };
}

export function defaultBarcodeProps(): BarcodeLayerProps {
  return {
    kind: 'barcode',
    show_code: true,
  };
}
