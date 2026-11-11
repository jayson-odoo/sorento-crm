/**
 * Tag template document model types.
 *
 * Matches the JSONB schema stored in `dealer_kit.tag_templates.doc` and used
 * by both the tag template editor (S3) and the tag sheet designer (S4).
 * Positions and sizes are always in millimetres; the canvas converts to
 * pixels via a zoom-dependent scale factor.
 */

import type { TemplateNeeds } from './combo-slots';

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
  | 'group'
  | 'feature_icons'
  | 'accessories';

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
  // PRICETAG-LPSP: the figure the line shows (SP when it shows SP, else LP) and its label.
  | 'price'
  | 'price_label'
  | 'badges'
  | 'alternatives'
  | 'accessories'
  | 'set_members'
  | 'barcode'
  | 'price_tag_description'
  | 'combo_image'
  | 'combo_name'
  | 'combo_description'
  | 'combo_choices'
  | 'combo_topups'
  // PS-SPEC-SHEET: an image slot showing the subject's technical drawing (the quotation line's
  // frozen drawing, or a part's first "Technical Specifications" file). Empty when it has none.
  | 'drawing'
  // PRICETAG-UPGRADE-VARIANTS S2: on an "Upgrade N" position, its top-up and the tag SP plus it.
  | 'upgrade_topup'
  | 'sell_price_with_upgrade'
  | null;

export type ShapeType = 'rect' | 'rounded_rect' | 'ellipse' | 'line' | 'polygon';

/**
 * A polygon corner, normalized to [0, 1] against the layer's own box (S4).
 *
 * Normalized so the Transformer keeps resizing a polygon exactly as it
 * resizes a rectangle, and so a document saved before S4 needs no migration:
 * a shape with no `points` is the box's four corners.
 */
export interface PolygonPoint {
  x: number;
  y: number;
}

export type ImageFit = 'cover' | 'contain' | 'stretch';

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
  /** Mirror left-right / top-bottom about the layer box (`image-flip.ts`). Absent = not flipped. */
  flipX?: boolean;
  flipY?: boolean;
  /**
   * Where the picture came from before S3b gave image layers a source
   * discriminator. Read by `imageSourceOf`, never written: a template saved by
   * the first version of the editor still opens.
   */
  assetId?: string | null;
  /** D7 - see `TextLayerProps.subjectPart`. An `image` layer bound to
   *  `slot_binding: 'product_image'` reads product data exactly like a
   *  `product_slot` layer does (browser finding: the designer's own photo
   *  slots are `image` layers, not `product_slot`), so it needs the same
   *  per-layer subject. */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
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

/**
 * A layer's own internal margin, in millimetres (S3). Absent means zero on
 * every side, so a document saved before S3 draws exactly as it did -
 * `paddedBox` in `text-reflow.ts` is the one place that resolves it.
 */
export interface LayerPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** PRICETAG-COMBO-RENDER K1: where a layer reads on a combo line. 0-based. */
export type SubjectSlot =
  | { kind: 'main' }
  | { kind: 'fixed'; index: number }
  | { kind: 'pick'; group: number; index: number }
  | { kind: 'upgrade'; index: number }
  /** PRICETAG-UPGRADE-VARIANTS S3: a feature icons layer on "All variants" (the subject and the
   *  live members of its variant tree). The main product for anything else; never a combo position. */
  | { kind: 'variants' };

/** K2: where each product of a tag sits. */
export interface TagSlots {
  /** The main product's own data; absent on a payload that predates it. */
  main?: TagPartData | null;
  fixed: TagPartData[];
  groups: { role: string; size: number; picks: TagPartData[] }[];
  upgrades: TagPartData[];
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
  /** Internal margin (S3). Absent = 0 on every side. */
  padding?: LayerPadding;
  /** D7: which of a combo tag's products this layer reads, when it reads
   *  product data at all (a `{{product.*}}` / `{{spec.*}}` token). Absent =
   *  the parent, matching every document saved before this field existed
   *  (AC-S4-4). See `subjectOf` in `product-block.ts`. */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
  /** Same meaning as `PriceBadgeLayerProps.showCurrency`, for a text layer bound to a price slot.
   *  Absent = the bare figure; true = `RM 849`, and nothing at all when there is no amount. */
  showCurrency?: boolean;
  /** PRICETAG-UPGRADE-VARIANTS S2: printed before an `upgrade_topup` / `sell_price_with_upgrade`
   *  figure ("TOPUP "), never when the figure is empty. Unused by every other slot. */
  prefix?: string;
}

export interface ShapeLayerProps {
  kind: 'shape';
  shape: ShapeType;
  fill: string;
  stroke: string;
  strokeWidth: number;
  cornerRadius: number;
  /**
   * The polygon's own corners (S4), absent for every other shape and for a
   * polygon nobody has moved a corner on yet. `polygonPoints()` in
   * `polygon-path.ts` is the one place that resolves absent to the box.
   */
  points?: PolygonPoint[];
}

export interface ProductSlotLayerProps {
  kind: 'product_slot';
  fieldKey: string;
  /** D7 - see `TextLayerProps.subjectPart`. */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
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
  /**
   * Print `RM` before the figure (S3c, AC-13/14/15). Absent = true, so a
   * badge saved before this flag existed still reads `RM 760`. Off drops the
   * prefix on the figure AND, for the promo variant, both the struck `LP:`
   * line and the `SP` line - `priceBadgeParts` in `price-badge.ts` is the
   * one place that reads this, so the two renderers cannot disagree.
   */
  showCurrency?: boolean;
  /**
   * Draw the box behind a LIST-ONLY badge (r4b, AC-S6-1).
   *
   * Absent means no box, so every badge saved before this prints exactly as
   * it did. Promo is always boxed and ignores this - the struck price above a
   * filled block is what a promotional badge IS (D26).
   */
  showBox?: boolean;
  /**
   * The box's own corners, same normalization as a polygon shape's (r4b,
   * AC-S6-2): the flyer's price callout has a slanted left edge, and the
   * badge itself is that callout rather than a shape parked behind it.
   * Absent = the four corners.
   */
  points?: PolygonPoint[];
  /**
   * The figure's typography (r4b, AC-S6-4). Every field is optional and every
   * absent one means "what this badge already looked like" - the canvas sizes
   * the figure from the box, the print page uses a fixed point size - so a
   * saved badge renders unchanged (AC-S6-5). `priceBadgeTypography` in
   * `price-badge.ts` is the one place that resolves them.
   */
  fontFamily?: string;
  fontSize?: number;
  fontWeight?: number;
  italic?: boolean;
  underline?: boolean;
  strikethrough?: boolean;
  align?: 'left' | 'center' | 'right';
  lineHeight?: number;
  letterSpacing?: number;
  /**
   * The figure's own inset from the callout's edge (S3b). Absent = 0 on
   * every side. Independent of `margin` below: this one never moves the
   * callout, only the figure inside it. `priceBadgeInsets` in
   * `price-badge.ts` is the one place that resolves the two together,
   * including the legacy rule that keeps a badge saved before `margin`
   * existed pixel-identical.
   */
  padding?: LayerPadding;
  /**
   * The callout's own inset from the layer box (S3b). Absent means this
   * badge was saved before `margin` existed, in which case `padding` above
   * used to do both jobs at once - inset the callout AND leave the figure
   * flush inside it - and `priceBadgeInsets` reads that as `margin: padding,
   * padding: 0` so the badge draws exactly as it always did.
   */
  margin?: LayerPadding;
  /**
   * D7: which product's price this badge draws, on a combo tag. Unlike the
   * other subject-aware layers, absent here is NOT "the parent" - it is
   * **Tag total**, the parent + parts roll-up this badge always printed
   * before this field existed (AC-S4-4), and stays the default so an
   * existing design still prints the same figure. `-1` is the parent's own
   * price alone; `0..n` is that part's own price. See `subjectOf` in
   * `product-block.ts`.
   */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
}

/**
 * A barcode, drawn like the barcode staff already print (D18,
 * PRICETAG-BARCODE-MATCH): white background, the product code above the bars
 * in black serif (per-layer `show_code`), the bars, and the digits beneath,
 * split around the EAN-13 guards. One SVG (`barcodeSvg`) for the canvas, the
 * preview and the PDF. Always bound to slot `barcode` - a tag has one
 * product, so there is nothing else for it to draw.
 */
export interface BarcodeLayerProps {
  kind: 'barcode';
  show_code: boolean;
  /** D7 - see `TextLayerProps.subjectPart`. */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
}

/**
 * PRICETAG-DESIGNER-GAPS item 3: one packed row of the icons the subject's spec values carry
 * (`featureIconsFor`), in the spec registry's one sequence (spec Icon order, then the value's own
 * list). The layer has no order of its own (owner, 5 Nov 21:0x).
 */
export interface FeatureIconsLayerProps {
  kind: 'feature_icons';
  iconSize_mm: number;
  gap_mm: number;
  align: 'left' | 'center' | 'right';
  /** D7 - see `TextLayerProps.subjectPart`. */
  subjectPart?: number;
  /** PRICETAG-COMBO-RENDER K1: a position in the combo; wins over `subjectPart`. */
  subjectSlot?: SubjectSlot;
}

/**
 * PRICETAG-ACCESSORIES: one styled box that repeats a mini-card (picture, name, spec) per
 * accessory on the bound list, in order (card rules A4-A8). Laid out by `accessoryBoxLayout`
 * (`lib/dealer-kit/accessory-box.ts`), the one function the canvas, the preview and print share.
 * Header text and the "+" badge are the box's own (owner, 6 Nov: "FREE" on one tag,
 * "ACCESSORIES INCLUDED" on another).
 */
/**
 * One text role of an Accessories box (header, name, spec), set with the same TypographyControls
 * every text layer uses. Size lives in the box's own `*FontSize` prop; everything here is optional
 * and falls back to the box's defaults, so a box saved before these existed draws unchanged.
 */
export interface AccessoryTextStyle {
  fontFamily?: string | null;
  fontWeight?: number;
  italic?: boolean;
  underline?: boolean;
  strikethrough?: boolean;
  align?: 'left' | 'center' | 'right';
  letterSpacing?: number;
  color?: string;
  /** PRICETAG-HEADER-DRAG round 2: line height of a resized (wrapping) header. Absent = 1. */
  lineHeight?: number;
}

export interface AccessoriesLayerProps {
  kind: 'accessories';
  /** PRICETAG-UPGRADE-VARIANTS S1: what the box lists. `upgrades` = the combo's upgrades on offer
   *  (`upgradesOf`); absent / `free` = the free items, as every box saved before. */
  list?: 'free' | 'upgrades';
  direction: 'vertical' | 'horizontal';
  /**
   * Owner hand test (6 Nov ~15:00): each card is a picture ABOVE its text (stacked, centred, the
   * printed Dealer Kit box) or LEFT of it. Absent on a box saved before: vertical drew side,
   * horizontal drew stacked (`itemLayoutOf`).
   */
  itemLayout?: 'stacked' | 'side';
  /** Absent = shown (a box saved before hid its header only by clearing the text). */
  showHeader?: boolean;
  /** Absent = shown. */
  showFrame?: boolean;
  /** The header sits ON the top border (legend style), the border broken behind it. Absent = no. */
  headerOnBorder?: boolean;
  /** What shows behind a header on the border (the tag's own background). */
  headerBackground?: string;
  /** PRICETAG-HEADER-DRAG: where the header was dragged to, its top-left in mm from the box's
   *  top-left. Absent / null = today's computed spot. A moved header is plain text (never on the
   *  border) and moves nothing else in the box. Part of the linked design (owner Q5, 9 Nov). */
  headerPos?: { x_mm: number; y_mm: number } | null;
  /** Round 2 (owner 9 Nov ~17:00, "resize it like a normal design component"): the header band's
   *  size once resized; with it the text wraps inside the band at its set size. Only read with
   *  `headerPos` (a resized header is a placed one). Absent / null = as wide as its text. */
  headerSize?: { width_mm: number; height_mm: number } | null;
  /** The header band's background; 'transparent' = none. Absent = today's rule (the "behind the
   *  header" colour on the border, none elsewhere). */
  headerFill?: string | null;
  /** The header band's corner radius (mm). Absent = square. */
  headerRadius_mm?: number;
  /** Inner margin between the header band and its text (mm). Absent = 0. */
  headerPadding?: LayerPadding;
  headerStyle?: AccessoryTextStyle;
  nameStyle?: AccessoryTextStyle;
  specStyle?: AccessoryTextStyle;
  headerText: string;
  headerFontSize: number;
  headerColor: string;
  /** The round "+" badge on the box's top-left corner. */
  showBadge: boolean;
  badgeColor: string;
  fill: string;
  stroke: string;
  strokeWidth_mm: number;
  cornerRadius_mm: number;
  cardFill: string;
  textColor: string;
  imageSize_mm: number;
  nameFontSize: number;
  specFontSize: number;
  gap_mm: number;
  /** Horizontal boxes: every card is this wide (card Q-M2 (a)). */
  cardWidth_mm: number;
  fontFamily?: string;
  /** PRICETAG-COMBO-RENDER K1: a combo position whose OWN list to read; absent = the tag's list. */
  subjectSlot?: SubjectSlot;
  /** D7: a request line's part (index into `parts`; -1 the main product) whose OWN list to read. */
  subjectPart?: number;
  /**
   * PRICETAG-ACCESSORY-DESIGNER: a designed card. Set = the box draws `card` for every accessory
   * (`cardBoxLayout`); absent = the legacy card (`accessoryBoxLayout`), untouched.
   */
  card?: CardLayout;
  /** The area under the cards (a note, colour dots). Absent = none. */
  footer?: FooterLayout;
  /**
   * PRICETAG-ACCESSORY-DESIGNER S6 (card path only): a grid of this many columns, wrapping to rows;
   * `auto` = as many as fit the box at full size. Absent = today's single column (vertical) or row.
   */
  columns?: 'auto' | 1 | 2 | 3 | 4;
  /** Smallest scale the cards shrink to before whole cards are dropped. Absent = 0.7. */
  shrinkMin?: number;
  /** The saved accessories template this box follows (live link); absent = its own design. */
  presetId?: string | null;
}

/** What a text or picture element of a designed card reads from the accessory. */
export type CardField =
  | 'picture'
  | 'name'
  | 'code'
  | 'spec'
  | 'remark'
  | 'price'
  | 'colours'
  // PRICETAG-UPGRADE-VARIANTS S1: an upgrade's top-up, and the tag SP plus it.
  | 'topup'
  | 'price_with_upgrade'
  // SPEC-SHEET-DESIGNER-PARITY B2: a catalogue product's own fields on a spec sheet page.
  | 'brand'
  | 'description'
  | 'spec_sheet_description'
  | 'dimensions';

export interface CardElement {
  id: string;
  kind: 'picture' | 'text' | 'colour_dots' | 'shape' | 'feature_icons';
  /** Inside the card (or footer), millimetres. */
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  hidden?: boolean;
  /** text: name|code|spec|remark|price, null = fixed `text`; picture: 'picture'; colour_dots: 'colours'. */
  field?: CardField | null;
  /** Fixed text, plain or rich (`lib/dealer-kit/rich-text.ts`). */
  text?: string;
  fontFamily?: string | null;
  fontSize?: number;
  fontWeight?: number;
  italic?: boolean;
  underline?: boolean;
  color?: string;
  align?: 'left' | 'center' | 'right';
  lineHeight?: number;
  fit?: 'contain' | 'cover';
  dotSize_mm?: number;
  dotGap_mm?: number;
  dotDirection?: 'row' | 'column';
  dotOutline?: string;
  /** Hand-picked hex colours; null or absent = from the data. */
  colours?: string[] | null;
  shape?: 'rect' | 'rounded_rect' | 'ellipse' | 'line';
  fill?: string;
  stroke?: string;
  strokeWidth_mm?: number;
  cornerRadius_mm?: number;
  /** text with a field: printed before the value when there is one ("TOPUP "). */
  prefix?: string;
  /** text (owner 9 Nov ~22:30): space around the text inside its element, like the box header's.
   *  A text element's `fill` is its background and `cornerRadius_mm` that background's corners. */
  padding?: LayerPadding;
  /** feature_icons: the icon size and the space between icons (defaults 4.6 / 0.8). */
  iconSize_mm?: number;
  gap_mm?: number;
}

export interface CardLayout {
  width_mm: number;
  height_mm: number;
  elements: CardElement[];
}

export interface FooterLayout {
  show: boolean;
  height_mm: number;
  elements: CardElement[];
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
  | GroupLayerProps
  | FeatureIconsLayerProps
  | AccessoriesLayerProps;

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
  /**
   * PS-SPEC-SHEET: print this layer only when the bound data says so. `spec`: the subject's
   * spec with that key reads Yes (a Rimless or Accessible badge). `part`: the line has a part
   * at that index (an accessory row). Absent = always drawn, exactly as before. The editor
   * canvas always draws the layer so the designer can see it.
   */
  show_when?: LayerShowWhen | null;
}

export interface LayerShowWhen {
  spec?: string | null;
  part?: number | null;
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
  | 'furniture_set'
  // PS-SPEC-SHEET: project spec sheet pages, not price tags (`SPEC_SHEET_FAMILIES`).
  | 'spec_cover'
  | 'spec_page';

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

/**
 * PS-SPEC-SHEET: the project spec sheet's page templates. Designed in the same editor and
 * printed by the same renderer, but they are pages, not price tags: never offered to a price
 * tag request (`listPublishedTemplates`) or as a product's tag template (#2100,
 * `NON_PRICE_TAG_FAMILY_PREFIX` server side).
 */
export const SPEC_SHEET_FAMILIES: { value: TagTemplateFamily; label: string }[] = [
  { value: 'spec_cover', label: 'Spec sheet cover' },
  { value: 'spec_page', label: 'Spec sheet page' },
];

/** Every family the template editor can give a template. */
export const ALL_TEMPLATE_FAMILIES: { value: TagTemplateFamily; label: string }[] = [
  ...TAG_TEMPLATE_FAMILIES,
  ...SPEC_SHEET_FAMILIES,
];

export function isSpecSheetFamily(family: string | null | undefined): boolean {
  return Boolean(family && family.startsWith('spec_'));
}

export function familyLabel(family: string): string {
  return ALL_TEMPLATE_FAMILIES.find((f) => f.value === family)?.label ?? family;
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

/** A per-A4-sheet grid a template or a saved size preset may carry (S7,
 *  AC-S7-11/12/15): arrange uses it in place of the derived best fit for any
 *  size group that matches. Absent = arrange derives. */
export interface TagSheetGrid {
  cols: number;
  rows: number;
  turn: boolean;
}

export interface TagTemplate {
  id: string;
  name: string;
  family: TagTemplateFamily;
  doc: TagTemplateDoc;
  print_size: { width_mm: number; height_mm: number; sheet?: TagSheetGrid };
  created_at: string;
  updated_at: string;
  /** The live pointer (PLAN D7). Absent = never published. */
  published_version_id?: string | null;
  published_version_no?: number | null;
  /** What the published layers read from a combo (PRICETAG-COMBO-RENDER K4). */
  needs?: TemplateNeeds | null;
  /** Hand-picked LP / SP / both; null or absent = not set (offered on both kinds of line). */
  price_type?: 'list' | 'selling' | 'both' | null;
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
  /**
   * The REQUEST TAG this placement prints (D3, S3).
   *
   * Was `request_line_id` until one line could carry several tags: a line with
   * an open choice group is split into one tag per candidate, and each of those
   * has its own design, geometry and price. The line is still what the
   * salesperson asked for; the tag is what gets printed, so the document keys
   * on the tag. A doc written before S3 is rewritten by the S3 migration, which
   * points each `request_line_id` at that line's single tag.
   */
  request_tag_id: string;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
  layers: TagLayer[];
  /**
   * Turned 90deg at print time (S7): `width_mm`/`height_mm` above stay the
   * tag's own NATURAL (unrotated) size - what its layers are laid out
   * against - while `x_mm`/`y_mm` are the top-left of the PLACED (rotated)
   * box the renderers draw. Absent/0 = drawn as designed. A doc saved before
   * S7 (or before this field, on a copy nobody rotated) has none, which reads
   * as 0 - unrotated, exactly as it always printed.
   */
  rotation?: 0 | 90;
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
  /** The stored value as text (`mixer`, `true`). Feature icons match on this, never on `value`. */
  raw?: string;
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
  /** Staff-authored tag copy (r10 S4). Absent/null renders nothing - no
   *  fallback to `spec_lines` or a description. */
  price_tag_description?: string | null;
  /** `products.description`, the plain catalogue description ({{product.description}}).
   *  Optional: a row frozen before it existed reads as empty. */
  description?: string | null;
  /** `products.spec_sheet_description`, else `description` ({{product.spec_sheet_description}}). */
  spec_sheet_description?: string | null;
  /** `products.currency` (AC-A5). Optional so an older pinned/cached row
   *  (frozen before this field existed) still renders - `resolvePath` falls
   *  back to `MYR` when absent (AC-A7). */
  currency?: string;
  /** The combo being previewed in the template editor (PRICETAG-COMBO AC-5.3). */
  combo?: TagCombo | null;
  /** Positions of the previewed combo (PRICETAG-COMBO-RENDER K2). */
  slots?: TagSlots | null;
  /** PS-SPEC-SHEET: brand name and technical drawing, when the source carries them. */
  brand?: string;
  drawing?: TagImage | null;
  /** PRICETAG-ACCESSORIES: the product's own list. Absent on an older payload. */
  accessories?: TagAccessory[];
  /** PRICETAG-ACCESSORY-DESIGNER S6: the box style this owner names; absent / null = the template's own box. */
  accessory_box_style?: TagAccessoryBoxStyle | null;
  /** PRICETAG-UPGRADE-VARIANTS S3: the live members of its variant tree. Absent = none. */
  variants?: TagVariant[];
}

/** PRICETAG-UPGRADE-VARIANTS S3: one live member of the tag product's variant tree. */
export interface TagVariant {
  product_id: string;
  code: string;
  specs: TagSpecValue[];
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
  /** The first member's currency (AC-A11). Optional, see `ProductTagData.currency`. */
  currency?: string;
}

/**
 * Display data for one price tag request LINE.
 *
 * The tag sheet designer resolves per line rather than per product, because a
 * line can carry a marketing price override with a logged reason (D9) and that
 * override has to win on the tag the designer is looking at. Same shape the
 * print payload sends, so the proof and the PDF agree.
 */
/** One choice group still undecided on a tag (D3): the salesperson left it open. */
export interface TagOpenGroup {
  role: string;
  /**
   * The group's candidates, in combo order.
   *
   * D3 wrote this as codes alone. It carries the id beside the code because
   * "Pick one" has to NAME the chosen candidate to
   * `PATCH .../tags/{tag_id}` , whose `choices` is `{role: product_id}` - a
   * code cannot express that, and looking one up would be a second round trip
   * for something this call already knows. Only the `code` is ever rendered
   * (AC-X-2), and D4's printed `ROLE: CODE / CODE` text still reads it.
   */
  candidates: { product_id: string; code: string }[];
}

/** One option of a combo choice group, as the tag shows it (PRICETAG-COMBO AC-2.1). */
export interface TagComboOption {
  product_id: string;
  code: string;
  description: string;
  list_price: number | null;
  /** The option's own selling price, null when blank. */
  sell_price: number | null;
  picked: boolean;
}

export interface TagComboUpgrade {
  product_id: string;
  code: string;
  description: string;
  topup_amount: number | null;
  picked: boolean;
}

/**
 * PRICETAG-ACCESSORIES: one entry of an accessory list as a tag carries it. A library accessory
 * (`kind` 'accessory' or absent): name + spec. A catalogue product listed as a free item (`kind`
 * 'product', owner 6 Nov ~10:45): `code`, its description as `name`, `list_price`, read live.
 */
export interface TagAccessory {
  /** `upgrade` (PRICETAG-UPGRADE-VARIANTS S1): a combo upgrade on offer, built by `upgradesOf`. */
  kind?: 'accessory' | 'product' | 'upgrade';
  id: string;
  name: string;
  spec: string | null;
  /** PRICETAG-ACCESSORY-DESIGNER: absent on a row pinned before it. */
  remark?: string | null;
  /** The chosen picture, else the first. */
  image: { attachment_id: string; url: string } | null;
  /** Every picture, in order, each with its optional colour. */
  images?: { attachment_id: string; url: string; colour_name: string | null; colour_hex: string | null }[];
  /** Distinct colours of the pictures, in picture order. */
  colours?: { name: string | null; hex: string }[];
  code?: string | null;
  list_price?: number | null;
  /** TAG-ACC-CARD-RESIZE Q4, a catalogue product only: its offer for this viewer (null = none), its
   *  spec lines and its own price tag description, read live. Absent on a library accessory and on
   *  a row pinned before them. */
  sell_price?: number | null;
  spec_lines?: string[];
  price_tag_description?: string | null;
  /** SPEC-SHEET-DESIGNER-PARITY B2, a catalogue product on a spec sheet page. */
  brand?: string | null;
  description?: string | null;
  spec_sheet_description?: string | null;
  dimensions?: string | null;
  /** An upgrade's top-up, and the tag's SP plus it (null when either is missing). */
  topup_amount?: number | null;
  price_with_upgrade?: number | null;
  /** An upgrade's own specs, for its feature icons. */
  specs?: TagSpecValue[];
}

/** A saved accessories template a product or combo names as its own "Accessories included" box style. */
export interface TagAccessoryBoxStyle {
  id: string;
  name: string;
  /** The box design (`accessoryDesign` shape); applied with `applyAccessoryDesign`. */
  design: Record<string, unknown>;
}

/** The combo a tag's line names. Null on a line with no combo and on an older pin. */
export interface TagCombo {
  id: string;
  name: string;
  description: string | null;
  free_items: string | null;
  /** PRICETAG-ACCESSORIES: the combo's own list; `free_items` is its names joined. */
  accessories?: TagAccessory[];
  /** PRICETAG-ACCESSORY-DESIGNER S6: the box style this owner names; absent / null = the template's own box. */
  accessory_box_style?: TagAccessoryBoxStyle | null;
  choices: { role: string; options: TagComboOption[] }[];
  upgrades: TagComboUpgrade[];
  /** COMBO-SETTINGS-UX: the main product's own label ("CABINET"); absent on an older payload. */
  main_label?: string | null;
  /** COMBO-SETTINGS-UX: "Each part prints as", a rich line of `{{part.*}}` fields; null = the default. */
  parts_line?: string | null;
  /** COMBO-SETTINGS-UX: each part's label, by part product id (only the parts that have one). */
  part_labels?: Record<string, string>;
}

/**
 * One part printed under the host on a tag (D3/D4).
 *
 * D7 (built, S9): the full product surface a subject picker can point a
 * layer at - `spec_lines`/`specs`/`images`/`barcode`/`list_price`/
 * `sell_price`, resolved server-side per part. Still declared optional so
 * an OLDER pinned row (frozen before D7 landed) fails soft:
 * `subjectOf` reads an absent field as "this part has none" - an empty
 * placeholder, not the parent's (AC-S4-5) - rather than throwing.
 */
export interface TagPartData {
  /** Carried so a caller can match a part back to the choice that produced it.
   *  Never rendered - the code is what a reader sees (AC-X-2). */
  product_id?: string | null;
  code: string;
  name: string;
  dimensions: string;
  /** COMBO-SETTINGS-UX: the same measurement as `L780xW480xH400mm`; '' with none, absent on an older payload. */
  dimensions_lwh?: string;
  spec_lines?: string[];
  specs?: TagSpecValue[];
  images?: TagImage[];
  barcode?: string | null;
  list_price?: number | null;
  /** Offer under the LINE's promotion (D3: parts share the line's promotion),
   *  else null. */
  sell_price?: number | null;
  /** This part's OWN product's currency (AC-A11), not the host's. Optional,
   *  see `ProductTagData.currency`. */
  currency?: string;
  /** r10 S6: the choice group this row belongs to ("Kitchen Tap"), so the
   *  subject picker can group the candidates under it. Absent on a fixed
   *  part and on every row written before r10. */
  role?: string | null;
  /** r10 S6: true on the candidate THIS tag's own choices name - the one
   *  `own_parts` and Tag total count. Absent on a fixed part. */
  chosen?: boolean;
  /** This part's OWN product's tag copy (r10 S4), not the host's. */
  price_tag_description?: string | null;
  /** `products.description`, the plain catalogue description ({{product.description}}).
   *  Optional: a row frozen before it existed reads as empty. */
  description?: string | null;
  /** `products.spec_sheet_description`, else `description` ({{product.spec_sheet_description}}). */
  spec_sheet_description?: string | null;
  /** PS-SPEC-SHEET: the part's brand name and technical drawing. */
  brand?: string;
  drawing?: TagImage | null;
  /** PRICETAG-ACCESSORIES: this position's own product's list. */
  accessories?: TagAccessory[];
  /** PRICETAG-ACCESSORY-DESIGNER S6: the box style this owner names; absent / null = the template's own box. */
  accessory_box_style?: TagAccessoryBoxStyle | null;
  /** PRICETAG-UPGRADE-VARIANTS S1: an upgrade position's top-up. Absent elsewhere and on older rows. */
  topup_amount?: number | null;
}

/** PS-SPEC-SHEET: the quotation and project facts every spec sheet page can print. */
export interface SpecSheetDocFields {
  project_title: string;
  ref: string;
  your_ref: string;
  quotation_no: string;
  prepared_by: string;
  prepared_by_phone: string;
  date: string;
}

/**
 * What one TAG draws with (D3, S3).
 *
 * One row per tag rather than per line since S3: `line_id` still says which
 * line asked for it, and `tag_id` is what the document, the rail and the
 * resolved-data map key on.
 */
export interface LineTagData {
  tag_id: string;
  line_id: string;
  /** "1a", "1b" - line index plus a letter. Never an id (AC-X-2). */
  tag_label: string;
  /** Groups this tag has NOT resolved. Empty once marketing splits or picks. */
  open_groups: TagOpenGroup[];
  /** Every product a slot on this tag may point at, in part order (r10 S6):
   *  the line's fixed parts plus EVERY candidate of every choice group, not
   *  only the one this tag chose. Empty for a bare product. */
  parts: TagPartData[];
  /** The parts this tag itself prints - fixed parts plus its own chosen
   *  candidate - which is what `set_members` and Tag total add up (r10 S6).
   *  Absent on a row pinned before r10, where `parts` was already this list,
   *  so readers fall back to `parts` (AC-S6-11). */
  own_parts?: TagPartData[];
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
  /** The parent host's OWN price, alone - never the roll-up. Read by
   *  `subjectPart: -1` (D7, AC-S4-4): the parent alone is a different figure
   *  from `list_price`/`sell_price` below the moment a combo has priced
   *  parts. Optional so an older pinned/cached row (pre-D7) still renders -
   *  `productFromLineParent` falls back to subtracting `parts[]` from the
   *  roll-up when absent. */
  parent_list_price?: number | null;
  /** Offer under the line's promotion, or null with none - the parent's own
   *  half of `parent_list_price` above. */
  parent_sell_price?: number | null;
  list_price: number | null;
  sell_price: number | null;
  show_promo_price: boolean;
  included_accessories: string;
  /** PRICETAG-ACCESSORIES: the combo's list on a combo line, else the product's. Absent on a
   *  row pinned before the list existed. */
  accessories?: TagAccessory[];
  /** PRICETAG-ACCESSORY-DESIGNER S6: the box style this owner names; absent / null = the template's own box. */
  accessory_box_style?: TagAccessoryBoxStyle | null;
  quantity: number;
  /** Null for a set line - a set has no barcode of its own (S7). */
  barcode: string | null;
  /** The line's own currency (AC-A11). Optional, see `ProductTagData.currency`. */
  currency?: string;
  /** Staff-authored tag copy (r10 S4). Null for a set line - a set has no
   *  description of its own, same rule as barcode above. */
  price_tag_description?: string | null;
  /** `products.description`, the plain catalogue description ({{product.description}}).
   *  Optional: a row frozen before it existed reads as empty. */
  description?: string | null;
  /** `products.spec_sheet_description`, else `description` ({{product.spec_sheet_description}}). */
  spec_sheet_description?: string | null;
  /** The line's combo (PRICETAG-COMBO). Absent on an older payload. */
  combo?: TagCombo | null;
  /** Where each product of this tag sits (PRICETAG-COMBO-RENDER K2). */
  slots?: TagSlots | null;
  /** PRICETAG-UPGRADE-VARIANTS S3: the line product's live, ticked variant members. Absent = none. */
  variants?: TagVariant[];
  /** PS-SPEC-SHEET: present only on a spec sheet page's row. */
  brand?: string;
  drawing?: TagImage | null;
  area?: string;
  comment?: string;
  marker?: string;
  doc?: SpecSheetDocFields;
  /** A layer pointed at a part this line does not have reads as an empty product rather
   *  than falling back to the parent (which would print the main item twice). */
  strict_parts?: boolean;
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
    // D22/B1 (security review): list_only prints its amount straight onto
    // the tag's own background, which is what '#000000' has always drawn
    // for it - white would be invisible there. promo is white-on-red, so
    // its own default stays white.
    textColor: variant === 'promo' ? '#ffffff' : '#000000',
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

export function defaultFeatureIconsProps(): FeatureIconsLayerProps {
  return { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'left' };
}

export function defaultAccessoriesProps(): AccessoriesLayerProps {
  return {
    kind: 'accessories',
    direction: 'vertical',
    // Owner hand test (6 Nov ~15:00): the printed Dealer Kit box. A frame with the header on its
    // top border, each item a picture above a centred bold name and spec; no "+" badge.
    itemLayout: 'stacked',
    showHeader: true,
    showFrame: true,
    headerOnBorder: true,
    headerBackground: '#ffffff',
    nameStyle: { fontWeight: 700 },
    specStyle: { fontWeight: 400 },
    headerText: 'ACCESSORIES INCLUDED',
    headerFontSize: 9,
    headerColor: '#1f4d36',
    showBadge: false,
    badgeColor: '#c2410c',
    fill: '#f3f7f4',
    stroke: '#1f4d36',
    strokeWidth_mm: 0.4,
    cornerRadius_mm: 3,
    cardFill: '#ffffff',
    textColor: '#111827',
    imageSize_mm: 10,
    nameFontSize: 8,
    specFontSize: 6.5,
    gap_mm: 1.5,
    cardWidth_mm: 26,
  };
}

export function defaultBarcodeProps(): BarcodeLayerProps {
  return {
    kind: 'barcode',
    show_code: true,
  };
}

/**
 * A layer read the way the PDF renderer reads it. The renderer shows a layer unless `visible` is
 * false, while the designer hides it unless `visible` is truthy, so a layer saved without the key
 * draws in the PDF and vanishes on a live canvas. Normalising at the boundary closes the gap
 * without changing how Tag Templates read their own saved documents.
 */
export function normalizeLayer(layer: TagLayer, index: number): TagLayer {
  const raw = layer as unknown as Record<string, unknown>;
  const rotation = layer.rotation_deg ?? (raw.rotation as number | undefined) ?? 0;
  return {
    ...layer,
    visible: layer.visible !== false,
    locked: layer.locked === true,
    rotation_deg: rotation,
    z_index: layer.z_index ?? index,
    slot_binding: layer.slot_binding ?? null,
    text_override: layer.text_override ?? null,
  };
}

export function normalizeLayers(layers: TagLayer[]): TagLayer[] {
  return layers.map(normalizeLayer);
}
